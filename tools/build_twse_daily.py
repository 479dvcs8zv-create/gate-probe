#!/usr/bin/env python3
"""回測用證交所每日資料：上市漲跌家數、電子工業類指數漲跌%、當沖成交股數占比。可分多次執行、自動接續。

用法：python3 -I build_twse_daily.py <輸出資料夾> <起日 YYYY-MM-DD> <迄日> <可用分鐘數> [交易日快取資料夾]
- 交易日清單：讀加權指數月檔快取（MI_5MINS_HIST_*.json，已存在 repo），只請求真的有開盤的日子。
- 每日請求：MI_INDEX?type=ALLBUT0999（全部上市證券，不含權證、牛熊證）；2014-01-06 起另請求 TWTB4U（當沖）。
- 漲跌家數：逐檔看「漲跌(+/-)」欄，上漲＝+、下跌＝-，和網站用 STOCK_DAY_ALL 逐檔數的口徑相同（不含權證）。
- 電子類：「價格指數(臺灣證券交易所)」表中的電子工業類指數漲跌百分比；早年回應沒有這張表就留空，不補值。
- 每次請求間隔 4 秒；連續 5 次失敗就停（可能被擋），已完成的先存。原始回應不存（太大），只存 SHA-256 與位元組數。
- 輸出 daily.csv（依日期排序、可重跑接續）與 failures.jsonl。
"""
import csv
import datetime as dt
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (gate-probe research)", "Accept": "application/json"}
FIELDS = ["date", "adv", "dec", "unch", "rows", "breadth_pct", "elec_pct", "daytrade_share", "mi_sha256", "mi_bytes", "dt_sha256"]


def fetch(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def strip(s):
    return re.sub(r"<[^>]+>", "", str(s)).strip()


def num(s):
    t = strip(s).replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def parse_mi(body, ymd):
    j = json.loads(body)
    if j.get("stat") != "OK" or j.get("date") != ymd:
        raise ValueError(f"MI_INDEX stat={j.get('stat')!r} date={j.get('date')!r}")
    adv = dec = unch = rows = 0
    elec = None
    found = False
    for t in j.get("tables", []):
        f, data, title = t.get("fields") or [], t.get("data") or [], str(t.get("title") or "")
        if "證券代號" in f and "漲跌(+/-)" in f:
            found = True
            i = f.index("漲跌(+/-)")
            for r in data:
                sign = strip(r[i])
                rows += 1
                if sign == "+":
                    adv += 1
                elif sign == "-":
                    dec += 1
                else:
                    unch += 1
        if "價格指數(臺灣證券交易所)" in title and "漲跌百分比(%)" in f:
            k = f.index("漲跌百分比(%)")
            for r in data:
                if strip(r[0]) in ("電子工業類指數", "電子類指數"):
                    v = num(r[k])
                    if v is not None:
                        sign = strip(r[f.index("漲跌(+/-)")]) if "漲跌(+/-)" in f else ""
                        elec = -abs(v) if sign == "-" else abs(v) if sign == "+" else v
    if not found:
        raise ValueError("MI_INDEX 沒有逐檔收盤表")
    return adv, dec, unch, rows, elec


def parse_dt(body, ymd):
    j = json.loads(body)
    if j.get("stat") != "OK" or j.get("date") != ymd:
        raise ValueError(f"TWTB4U stat={j.get('stat')!r}")
    for t in j.get("tables", []):
        f = t.get("fields") or []
        key = next((x for x in f if "當日沖銷交易總成交股數占市場比重" in x), None)
        if key and t.get("data"):
            return num(t["data"][0][f.index(key)])
    raise ValueError("TWTB4U 沒有統計表")


def trading_days(cache):
    days = set()
    for p in Path(cache).glob("MI_5MINS_HIST_*.json"):
        d = json.loads(p.read_text())
        for r in d.get("data", []):
            y, m, dd = r[0].strip().split("/")
            days.add(dt.date(int(y) + 1911, int(m), int(dd)))
    return sorted(days)


def main(out, start, end, minutes, cache="results/backtest-data/twse-cache"):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    path, fails = out / "daily.csv", out / "failures.jsonl"
    done = {}
    if path.exists():
        with open(path) as f:
            done = {r["date"]: r for r in csv.DictReader(f)}
    deadline = time.time() + float(minutes) * 60
    todo = [d for d in trading_days(cache) if start <= d.isoformat() <= end and d.isoformat() not in done]
    print(f"todo {len(todo)} days, already {len(done)}", flush=True)
    streak = 0
    for d in todo:
        if time.time() > deadline or streak >= 5:
            break
        ymd = d.strftime("%Y%m%d")
        row = {"date": d.isoformat()}
        try:
            body = fetch(f"https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date={ymd}&type=ALLBUT0999&response=json")
            adv, dec, unch, rows, elec = parse_mi(body, ymd)
            row.update(adv=adv, dec=dec, unch=unch, rows=rows, breadth_pct=f"{adv / (adv + dec) * 100:.4f}" if adv + dec else "",
                       elec_pct="" if elec is None else elec, mi_sha256=hashlib.sha256(body).hexdigest(), mi_bytes=len(body))
            time.sleep(4)
            if d >= dt.date(2014, 1, 6):
                b2 = fetch(f"https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U?date={ymd}&selectType=All&response=json")
                row.update(daytrade_share=parse_dt(b2, ymd), dt_sha256=hashlib.sha256(b2).hexdigest())
                time.sleep(4)
            done[row["date"]] = row
            streak = 0
        except Exception as e:  # noqa: BLE001
            streak += 1
            with open(fails, "a") as f:
                f.write(json.dumps({"date": d.isoformat(), "error": repr(e)[:300], "at": dt.datetime.utcnow().isoformat()}, ensure_ascii=False) + "\n")
            print(f"fail {d}: {e!r}", flush=True)
            time.sleep(60 if streak > 1 else 8)
        if len(done) % 100 == 0:
            print(f"progress {len(done)} days (last {d})", flush=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        for k in sorted(done):
            w.writerow({x: done[k].get(x, "") for x in FIELDS})
    print(f"saved {len(done)} days; stopped early={streak >= 5}", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
