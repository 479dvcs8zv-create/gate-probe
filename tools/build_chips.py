#!/usr/bin/env python3
"""個股回測用：每日全部普通股的籌碼資料（法人買賣超、融券與借券賣出餘額）。只用證交所／櫃買中心官方網頁 JSON，不用金鑰。

用法：python3 -I build_chips.py <kind> <輸出資料夾> <起日> <迄日> <可用分鐘數> [交易日快取資料夾]
kind：
- twse_insti：證交所 T86（selectType=ALLBUT0999），2012-05-02 起。
- tpex_insti：櫃買 www/zh-tw/insti/dailyTrade（sect=EW），舊表 16 欄、新表 24 欄，依欄名與欄數對位。
- twse_lending：證交所 TWT93U（融券、借券賣出餘額），2012-03-19（借券新公式）起。
- tpex_lending：櫃買 www/zh-tw/margin/sbl（同 TWT93U 欄位）。
保留（股數）：法人＝外資（不含外資自營商）、投信、自營商合計、三大法人合計；借券＝融券今日餘額、借券賣出當日賣出、當日還券、當日餘額。
- 只留 4 碼、第一碼不是 0 的代號（普通股）。不自行計算或補值；官方當天沒有資料（假日、該表尚未開始提供）記為 empty。
- 每次請求間隔 4 秒；連續 5 次錯誤就停；依年份存 <kind>-<年>.csv.gz，可重跑接續；每 150 天先寫一次檔。
- 原始回應只記 SHA-256 與位元組數（<kind>-days.csv）。
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
FIRST = {"twse_insti": "2012-05-02", "tpex_insti": "2013-01-02", "twse_lending": "2012-03-19", "tpex_lending": "2013-01-02"}
HEAD = {"insti": ["date", "code", "foreign", "trust", "dealer", "total"],
        "lending": ["date", "code", "short_balance", "sbl_sold", "sbl_returned", "sbl_balance"]}


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
        return r.read()


def num(s):
    t = re.sub(r"<[^>]+>", "", str(s)).replace(",", "").strip()
    if not re.fullmatch(r"-?\d+(\.\d+)?", t):
        raise ValueError(f"非數字欄位 {s!r}")
    return t


def code_of(s):
    return re.sub(r"<[^>]+>", "", str(s)).strip()


def url_for(kind, d):
    ymd, slash = d.strftime("%Y%m%d"), f"{d.year}/{d.month:02d}/{d.day:02d}"
    return {"twse_insti": f"https://www.twse.com.tw/rwd/zh/fund/T86?date={ymd}&selectType=ALLBUT0999&response=json",
            "tpex_insti": f"https://www.tpex.org.tw/www/zh-tw/insti/dailyTrade?type=Daily&sect=EW&date={slash}&response=json",
            "twse_lending": f"https://www.twse.com.tw/rwd/zh/marginTrading/TWT93U?date={ymd}&response=json",
            "tpex_lending": f"https://www.tpex.org.tw/www/zh-tw/margin/sbl?date={slash}&response=json"}[kind]


def pick(fields, *names):
    for n in names:
        if n in fields:
            return fields.index(n)
    raise ValueError(f"缺欄位 {names[0]}")


def parse_twse_insti(j, ymd):
    if j.get("stat") != "OK":
        if "沒有符合條件" in str(j.get("stat")):
            return None
        raise ValueError(f"stat={j.get('stat')!r}")
    if j.get("date") != ymd:
        raise ValueError(f"date={j.get('date')!r}")
    f = [x.strip() for x in j.get("fields") or []]
    ix = [pick(f, "證券代號"), pick(f, "外陸資買賣超股數(不含外資自營商)", "外資買賣超股數"), pick(f, "投信買賣超股數"),
          pick(f, "自營商買賣超股數"), pick(f, "三大法人買賣超股數")]
    return [[code_of(r[ix[0]])] + [num(r[i]) for i in ix[1:]] for r in j.get("data") or [] if CODE.match(code_of(r[ix[0]]))]


def parse_tpex_insti(j, ymd):
    if str(j.get("stat")).lower() != "ok" or j.get("date") != ymd:
        raise ValueError(f"stat={j.get('stat')!r} date={j.get('date')!r}")
    roc = f"{int(ymd[:4]) - 1911}/{ymd[4:6]}/{ymd[6:]}"
    tables = [t for t in j.get("tables") or [] if t.get("data")]
    if not tables:
        return None
    t = tables[0]
    if t.get("date") not in (None, roc) and roc.replace("/", "") not in str(t.get("subtitle", "")).replace("年", "").replace("月", "").replace("日", ""):
        raise ValueError(f"table date {t.get('date')!r}")
    f = [x.strip() for x in t.get("fields") or []]
    if len(f) == 24 and f[23] == "三大法人買賣超股數合計":
        ix = [0, 4, 13, 22, 23]  # 外資及陸資(不含外資自營商)淨、投信淨、自營商合計淨、三大法人合計
    elif len(f) == 16:
        ix = [pick(f, "代號"), pick(f, "外資及陸資淨買股數"), pick(f, "投信淨買股數"), pick(f, "自營淨買股數"), pick(f, "三大法人買賣超股數")]
    else:
        raise ValueError(f"欄位數 {len(f)} 不認得")
    return [[code_of(r[ix[0]])] + [num(r[i]) for i in ix[1:]] for r in t["data"] if CODE.match(code_of(r[ix[0]]))]


def parse_lending(j, ymd, tpex):
    ok = str(j.get("stat")).lower() == "ok"
    if not ok:
        if "沒有符合條件" in str(j.get("stat")):
            return None
        raise ValueError(f"stat={j.get('stat')!r}")
    if j.get("date") != ymd:
        raise ValueError(f"date={j.get('date')!r}")
    if tpex:
        tables = [t for t in j.get("tables") or [] if t.get("data")]
        if not tables:
            return None
        f, data = [x.strip() for x in tables[0].get("fields") or []], tables[0]["data"]
    else:
        f, data = [x.strip() for x in j.get("fields") or []], j.get("data") or []
    if len(f) != 15 or f[0] not in ("代號", "股票代號") or "當日還券" not in f[10]:
        raise ValueError(f"欄位不符 {f[:3]}…（{len(f)} 欄）")
    # 0 代號｜2–7 融券（前日、賣出、買進、現券、今日餘額、限額）｜8–13 借券賣出（前日、當日賣出、當日還券、當日調整、當日餘額、可借限額）
    return [[code_of(r[0]), num(r[6]), num(r[9]), num(r[10]), num(r[12])] for r in data if CODE.match(code_of(r[0]))]


def parse(kind, body, ymd):
    j = json.loads(body)
    if kind == "twse_insti":
        return parse_twse_insti(j, ymd)
    if kind == "tpex_insti":
        return parse_tpex_insti(j, ymd)
    return parse_lending(j, ymd, kind == "tpex_lending")


def trading_days(cache):
    days = set()
    for p in Path(cache).glob("MI_5MINS_HIST_*.json"):
        for r in json.loads(p.read_text()).get("data", []):
            y, m, d = r[0].strip().split("/")
            days.add(dt.date(int(y) + 1911, int(m), int(d)))
    return sorted(days)


def load_year(path):
    rows = {}
    if path.exists():
        with gzip.open(path, "rt", newline="") as f:
            for r in csv.reader(f):
                if r and r[0] != "date":
                    rows.setdefault(r[0], []).append(r[1:])
    return rows


def save_year(path, kind, rows):
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(HEAD[kind.split("_")[1]])
    for d in sorted(rows):
        for r in rows[d]:
            w.writerow([d] + r)
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as g:
        g.write(buf.getvalue().encode())


def main(kind, out, start, end, minutes, cache="results/backtest-data/twse-cache"):
    assert kind in FIRST
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + float(minutes) * 60
    days = [d for d in trading_days(cache) if max(start, FIRST[kind]) <= d.isoformat() <= end]
    log = out / f"{kind}-days.csv"
    done = set()
    if log.exists():
        with open(log) as f:
            done = {r["date"] for r in csv.DictReader(f) if r["status"] in ("ok", "empty")}
    newlog = not log.exists()
    lf = open(log, "a", newline="")
    lw = csv.DictWriter(lf, fieldnames=["date", "rows", "sha256", "bytes", "status"])
    if newlog:
        lw.writeheader()
    years, dirty, streak, n = {}, set(), 0, 0
    for d in days:
        if time.time() > deadline or streak >= 5:
            break
        if d.isoformat() in done:
            continue
        y = d.year
        if y not in years:
            years[y] = load_year(out / f"{kind}-{y}.csv.gz")
        try:
            body = fetch(url_for(kind, d))
            rows = parse(kind, body, d.strftime("%Y%m%d"))
            if rows is None or not rows:
                lw.writerow({"date": d.isoformat(), "rows": 0, "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "status": "empty"})
            else:
                years[y][d.isoformat()] = rows
                dirty.add(y)
                lw.writerow({"date": d.isoformat(), "rows": len(rows), "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "status": "ok"})
            streak, n = 0, n + 1
        except Exception as e:  # noqa: BLE001
            streak += 1
            lw.writerow({"date": d.isoformat(), "rows": 0, "sha256": "", "bytes": 0, "status": repr(e)[:200]})
            print(f"fail {d}: {e!r}", flush=True)
            time.sleep(60 if streak > 1 else 8)
        lf.flush()
        time.sleep(4)
        if n and n % 150 == 0 and dirty:
            for yy in dirty:
                save_year(out / f"{kind}-{yy}.csv.gz", kind, years[yy])
            dirty.clear()
            print(f"progress {n} days (last {d})", flush=True)
    for yy in dirty:
        save_year(out / f"{kind}-{yy}.csv.gz", kind, years[yy])
    lf.close()
    print(f"done {n} requests this run", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
