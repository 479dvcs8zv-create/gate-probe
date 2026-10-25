#!/usr/bin/env python3
"""個股回測用：每日全部上市（TWSE）或上櫃（TPEx）普通股的收盤資料。含日後下市的股票（當天有掛牌就在），沒有存活者偏差。

用法：python3 -I build_stock_prices.py <twse|tpex> <輸出資料夾> <起日> <迄日> <可用分鐘數> [交易日快取資料夾]
- TWSE：MI_INDEX?type=ALLBUT0999（逐日）。保留 代號、收盤、漲跌符號、漲跌價差、成交股數、成交金額。
- TPEx：www/zh-tw/afterTrading/dailyQuotes（逐日，2007-07-02 起）。保留 代號、收盤、漲跌文字、次日參考價、成交股數、成交金額。
- 只留 4 碼、第一碼不是 0 的代號（普通股；排除 ETF、權證、債券、TDR）。
- 除權息還原：不另抓除權息表。TWSE 當日報酬＝收盤 ÷（收盤 − 漲跌價差）− 1（漲跌價差以當日參考價計）；
  TPEx 當日報酬＝收盤 ÷ 前一交易日的「次日參考價」− 1。回測程式負責計算，這裡只存原始欄位。
- 每次請求間隔 4 秒；連續 5 次失敗就停；依年份存成 <market>-<年>.csv.gz（可重跑接續，已完成的日子跳過）。
- 每完成 150 天先寫一次檔，避免逾時全失。原始回應只記 SHA-256 與位元組數（days.csv）。
"""
import csv
import datetime as dt
import gzip
import hashlib
import io
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (gate-probe research)", "Accept": "application/json"}
CODE = re.compile(r"^[1-9]\d{3}$")


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
        return r.read()


def strip(s):
    return re.sub(r"<[^>]+>", "", str(s)).strip()


def trading_days(cache):
    days = set()
    for p in Path(cache).glob("MI_5MINS_HIST_*.json"):
        for r in json.loads(p.read_text()).get("data", []):
            y, m, d = r[0].strip().split("/")
            days.add(dt.date(int(y) + 1911, int(m), int(d)))
    return sorted(days)


def parse_twse(body, ymd):
    j = json.loads(body)
    if j.get("stat") != "OK" or j.get("date") != ymd:
        raise ValueError(f"stat={j.get('stat')!r} date={j.get('date')!r}")
    for t in j.get("tables", []):
        f = t.get("fields") or []
        if "證券代號" in f and "漲跌(+/-)" in f:
            ix = {k: f.index(k) for k in ("證券代號", "收盤價", "漲跌(+/-)", "漲跌價差", "成交股數", "成交金額")}
            out = []
            for r in t.get("data") or []:
                code = strip(r[ix["證券代號"]])
                if CODE.match(code):
                    out.append([code, strip(r[ix["收盤價"]]).replace(",", ""), strip(r[ix["漲跌(+/-)"]]) or "0",
                                strip(r[ix["漲跌價差"]]).replace(",", ""), strip(r[ix["成交股數"]]).replace(",", ""), strip(r[ix["成交金額"]]).replace(",", "")])
            return out
    raise ValueError("沒有逐檔收盤表")


def parse_tpex(body, ymd):
    j = json.loads(body)
    roc = f"{int(ymd[:4]) - 1911}/{ymd[4:6]}/{ymd[6:]}"
    if str(j.get("stat")).lower() != "ok" or j.get("date") != ymd:
        raise ValueError(f"stat={j.get('stat')!r} date={j.get('date')!r}")
    t = j["tables"][0]
    if t.get("date") not in (None, roc):
        raise ValueError(f"table date {t.get('date')!r}")
    f = [x.strip() for x in t["fields"]]
    need = {"代號": "代號", "收盤": "收盤", "漲跌": "漲跌", "次日 參考價": "次日 參考價", "成交股數": "成交股數", "成交金額(元)": "成交金額(元)"}
    ix = {k: f.index(v) for k, v in need.items()}
    out = []
    for r in t.get("data") or []:
        code = strip(r[ix["代號"]])
        if CODE.match(code):
            out.append([code, strip(r[ix["收盤"]]).replace(",", ""), strip(r[ix["漲跌"]]), strip(r[ix["次日 參考價"]]).replace(",", ""),
                        strip(r[ix["成交股數"]]).replace(",", ""), strip(r[ix["成交金額(元)"]]).replace(",", "")])
    if not out:
        raise ValueError("沒有普通股資料")
    return out


HEAD = {"twse": ["date", "code", "close", "sign", "change", "volume", "value"],
        "tpex": ["date", "code", "close", "change_text", "next_ref", "volume", "value"]}


def load_year(path):
    rows = {}
    if path.exists():
        with gzip.open(path, "rt", newline="") as f:
            for r in csv.reader(f):
                if r and r[0] != "date":
                    rows.setdefault(r[0], []).append(r[1:])
    return rows


def save_year(path, market, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEAD[market])
    for d in sorted(rows):
        for r in rows[d]:
            w.writerow([d] + r)
    # mtime=0 讓同內容的檔案位元組相同，重跑不會產生無意義的差異
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as g:
        g.write(buf.getvalue().encode())


def main(market, out, start, end, minutes, cache="results/backtest-data/twse-cache"):
    assert market in ("twse", "tpex")
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + float(minutes) * 60
    first = "2007-07-02" if market == "tpex" else "2004-02-11"
    days = [d for d in trading_days(cache) if max(start, first) <= d.isoformat() <= end]
    years, dirty, log = {}, set(), out / f"{market}-days.csv"
    seen = set()
    if log.exists():
        with open(log) as f:
            seen = {r["date"] for r in csv.DictReader(f)}
    newlog = not log.exists()
    lf = open(log, "a", newline="")
    lw = csv.DictWriter(lf, fieldnames=["date", "rows", "sha256", "bytes", "status"])
    if newlog:
        lw.writeheader()
    streak, done_now = 0, 0
    for d in days:
        if time.time() > deadline or streak >= 5:
            break
        y = d.year
        if y not in years:
            years[y] = load_year(out / f"{market}-{y}.csv.gz")
        if d.isoformat() in years[y]:
            continue
        ymd = d.strftime("%Y%m%d")
        url = (f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={ymd}&type=ALLBUT0999&response=json" if market == "twse"
               else f"https://www.tpex.org.tw/www/zh-tw/afterTrading/dailyQuotes?date={d.year}/{d.month:02d}/{d.day:02d}&response=json")
        try:
            body = fetch(url)
            rows = (parse_twse if market == "twse" else parse_tpex)(body, ymd)
            years[y][d.isoformat()] = rows
            dirty.add(y)
            lw.writerow({"date": d.isoformat(), "rows": len(rows), "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "status": "ok"})
            streak, done_now = 0, done_now + 1
        except Exception as e:  # noqa: BLE001
            streak += 1
            lw.writerow({"date": d.isoformat(), "rows": 0, "sha256": "", "bytes": 0, "status": repr(e)[:200]})
            print(f"fail {d}: {e!r}", flush=True)
            time.sleep(60 if streak > 1 else 8)
        lf.flush()
        time.sleep(4)
        if done_now and done_now % 150 == 0:
            for yy in dirty:
                save_year(out / f"{market}-{yy}.csv.gz", market, years[yy])
            dirty.clear()
            print(f"progress {done_now} days (last {d})", flush=True)
    for yy in dirty:
        save_year(out / f"{market}-{yy}.csv.gz", market, years[yy])
    lf.close()
    print(f"{market}: fetched {done_now} days this run; stopped early={streak >= 5}", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
