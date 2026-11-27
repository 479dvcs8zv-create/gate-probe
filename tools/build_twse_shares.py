#!/usr/bin/env python3
"""投本比回測用：證交所上市普通股的發行股數，每月第一個交易日一份。
來源：證交所 MI_QFIIS「外資及陸資投資持股統計」的「發行股數」欄（官方網頁 JSON，不用金鑰）。

用法：python3 -I tools/build_twse_shares.py <輸出資料夾> <起月 YYYY-MM> <迄月 YYYY-MM> <可用分鐘數> [交易日快取資料夾]
- 交易日取自 MI_5MINS_HIST 快取；每月只抓第一個交易日。
- 只留 4 碼、第一碼不是 0 的代號（普通股）。欄位名稱或日期不符就記錯誤、不存；不自行補值。
- 每次請求間隔 4 秒；連續 5 次錯誤就停；已存過的日期跳過，可重跑接續。
- 存 twse-shares.csv.gz（date, code, shares）；原始回應只記 SHA-256 與位元組數（twse-shares-days.csv）。
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
URL = "https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?date={ymd}&selectType=ALLBUT0999&response=json"


def parse(body, ymd):
    j = json.loads(body)
    if j.get("stat") != "OK":
        raise ValueError(f"stat={j.get('stat')!r}")
    if j.get("date") != ymd:
        raise ValueError(f"date={j.get('date')!r}")
    f = [x.strip() for x in j.get("fields") or []]
    if "證券代號" not in f or "發行股數" not in f:
        raise ValueError(f"欄位不符 {f[:5]}")
    ic, isx = f.index("證券代號"), f.index("發行股數")
    out = []
    for r in j.get("data") or []:
        code = str(r[ic]).strip()
        if not CODE.match(code):
            continue
        s = str(r[isx]).replace(",", "").strip()
        if not s.isdigit() or int(s) <= 0:
            raise ValueError(f"{code} 發行股數 {r[isx]!r}")
        out.append((code, int(s)))
    if not out:
        raise ValueError("沒有普通股資料")
    return out


def first_days(cache, start, end):
    days = set()
    for p in Path(cache).glob("MI_5MINS_HIST_*.json"):
        for r in json.loads(p.read_text()).get("data", []):
            y, m, d = r[0].strip().split("/")
            days.add(dt.date(int(y) + 1911, int(m), int(d)))
    firsts = {}
    for d in sorted(days):
        firsts.setdefault(d.strftime("%Y-%m"), d)
    return [d for k, d in sorted(firsts.items()) if start <= k <= end]


def main(out, start, end, minutes, cache="results/backtest-data/twse-cache"):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    deadline = time.time() + float(minutes) * 60
    data_path, log_path = out / "twse-shares.csv.gz", out / "twse-shares-days.csv"
    rows = {}
    if data_path.exists():
        with gzip.open(data_path, "rt", newline="") as f:
            for r in csv.DictReader(f):
                rows.setdefault(r["date"], []).append((r["code"], int(r["shares"])))
    newlog = not log_path.exists()
    lf = open(log_path, "a", newline="")
    lw = csv.DictWriter(lf, fieldnames=["date", "rows", "sha256", "bytes", "status"])
    if newlog:
        lw.writeheader()
    streak = n = 0
    for d in first_days(cache, start, end):
        if time.time() > deadline or streak >= 5:
            break
        if d.isoformat() in rows:
            continue
        ymd = d.strftime("%Y%m%d")
        try:
            with urllib.request.urlopen(urllib.request.Request(URL.format(ymd=ymd), headers=UA), timeout=90) as r:
                body = r.read()
            got = parse(body, ymd)
            rows[d.isoformat()] = got
            lw.writerow({"date": d.isoformat(), "rows": len(got), "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body), "status": "ok"})
            streak, n = 0, n + 1
        except Exception as e:  # noqa: BLE001
            streak += 1
            lw.writerow({"date": d.isoformat(), "rows": 0, "sha256": "", "bytes": 0, "status": repr(e)[:200]})
            print(f"fail {d}: {e!r}", flush=True)
            time.sleep(60 if streak > 1 else 8)
        lf.flush()
        time.sleep(4)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["date", "code", "shares"])
    for d in sorted(rows):
        for code, s in sorted(rows[d]):
            w.writerow([d, code, s])
    with open(data_path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as g:
        g.write(buf.getvalue().encode())
    lf.close()
    print(f"done {n} requests this run; {len(rows)} months stored", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
