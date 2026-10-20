#!/usr/bin/env python3
"""回測資料：證交所加權指數每日收盤 ＋ FRED 美元指數（DTWEXAFEGS、DTWEXBGS）。

用法：python3 build_taiex_usd_dataset.py <輸出資料夾> [起始年=2006]
- 加權指數：TWSE MI_5MINS_HIST（每次一個月），每次請求間隔 4 秒；原始回應全部存檔。
- 美元指數：FRED 官方 CSV（DTWEXAFEGS＝先進經濟體美元指數，幣別組成最接近 DXY；DTWEXBGS＝廣義美元指數）。
- 輸出 taiex_usd.csv：date, taiex_close, dtwexafegs, dtwexbgs（美元指數沒有值的日子留空，不補值）。
"""
import csv
import datetime as dt
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (gate-probe research)"}


def get(url, tries=3):
    for n in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            print(f"retry {n+1} {url}: {e}", flush=True)
            time.sleep(60 * (n + 1))
    raise SystemExit(f"FAILED {url}")


def main(out, start_year):
    out = Path(out); raw = out / "raw"; raw.mkdir(parents=True, exist_ok=True)
    manifest = []
    taiex = {}
    today = dt.date.today()
    y, m = start_year, 1
    while (y, m) <= (today.year, today.month):
        url = f"https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date={y}{m:02d}01&response=json"
        body = get(url)
        name = f"MI_5MINS_HIST_{y}{m:02d}.json"; (raw / name).write_bytes(body)
        manifest.append({"url": url, "file": name, "sha256": hashlib.sha256(body).hexdigest()})
        d = json.loads(body)
        if d.get("stat") != "OK":
            print(f"no data {y}-{m:02d}: {d.get('stat')}", flush=True)
        for row in d.get("data") or []:
            roc = row[0].strip().split("/")
            date = dt.date(int(roc[0]) + 1911, int(roc[1]), int(roc[2])).isoformat()
            taiex[date] = float(row[4].replace(",", ""))
        m += 1
        if m == 13:
            y, m = y + 1, 1
        time.sleep(4)
    usd = {}
    for sid in ("DTWEXAFEGS", "DTWEXBGS"):
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}"
        body = get(url); (raw / f"{sid}.csv").write_bytes(body)
        manifest.append({"url": url, "file": f"{sid}.csv", "sha256": hashlib.sha256(body).hexdigest()})
        for r in csv.DictReader(body.decode().splitlines()):
            v = r.get(sid) or ""
            date = r.get("observation_date") or r.get("DATE")
            if v not in ("", "."):
                usd.setdefault(date, {})[sid] = v
    dates = sorted(set(taiex) | set(usd))
    with open(out / "taiex_usd.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["date", "taiex_close", "dtwexafegs", "dtwexbgs"])
        for d in dates:
            if d < f"{start_year}-01-01":
                continue
            w.writerow([d, taiex.get(d, ""), usd.get(d, {}).get("DTWEXAFEGS", ""), usd.get(d, {}).get("DTWEXBGS", "")])
    (out / "manifest.json").write_text(json.dumps({"generated_at": dt.datetime.utcnow().isoformat() + "Z",
        "taiex_days": len(taiex), "taiex_first": min(taiex), "taiex_last": max(taiex), "files": manifest}, indent=1))
    print(f"done: taiex {len(taiex)} days {min(taiex)}..{max(taiex)}; usd dates {len(usd)}", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2006)
