#!/usr/bin/env python3
"""回測資料：證交所加權指數每日收盤 ＋ FRED 美元指數（DTWEXAFEGS、DTWEXBGS）。

用法：python3 build_taiex_usd_dataset.py <輸出資料夾> [起始年=2006] [快取資料夾]
- 加權指數：TWSE MI_5MINS_HIST（每次一個月），每次請求間隔 4 秒；原始回應全部存檔。
- 已完成的月份（非當月、stat=OK）存進快取資料夾，重跑時直接讀快取，不再向證交所要。
- 單一網址失敗不中止整批：記入 manifest 的 failures，繼續下一個；最後一律寫出 CSV、manifest、build.log。
- 美元指數：FRED 官方 CSV（DTWEXAFEGS＝先進經濟體美元指數，幣別組成最接近 DXY；DTWEXBGS＝廣義美元指數）。
- 輸出 taiex_usd.csv：date, taiex_close, dtwexafegs, dtwexbgs（沒有值的日子留空，不補值）。
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
LOG = None


def log(msg):
    print(msg, flush=True)
    if LOG:
        with open(LOG, "a", encoding="utf-8") as f:
            f.write(msg + "\n")


def get(url, tries=3, headers=None, timeout=30):
    last = None
    for n in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers or UA), timeout=timeout) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            log(f"retry {n+1} {url}: {e!r}")
            time.sleep(30 * (n + 1))
    log(f"FAILED {url}: {last!r}")
    return None


def main(out, start_year, cache):
    global LOG
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    cache = Path(cache); cache.mkdir(parents=True, exist_ok=True)
    LOG = out / "build.log"
    manifest, failures, taiex = [], [], {}
    today = dt.date.today()
    y, m = start_year, 1
    while (y, m) <= (today.year, today.month):
        name = f"MI_5MINS_HIST_{y}{m:02d}.json"
        url = f"https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date={y}{m:02d}01&response=json"
        current = (y, m) == (today.year, today.month)
        cached = cache / name
        if cached.exists() and not current:
            body, origin = cached.read_bytes(), "cache"
        else:
            body, origin = get(url), "fetched"
            time.sleep(4)
        d = None
        if body is not None:
            try:
                d = json.loads(body)
            except ValueError:
                log(f"not json {y}-{m:02d}: {body[:160]!r}")
        if not d or d.get("stat") != "OK" or not d.get("data"):
            reason = "fetch_failed" if body is None else ("not_json" if d is None else f"stat={d.get('stat')!r}")
            failures.append({"month": f"{y}-{m:02d}", "url": url, "reason": reason})
            log(f"missing {y}-{m:02d}: {reason}")
        else:
            target = (out / "raw" / name) if current else cached
            target.parent.mkdir(parents=True, exist_ok=True)
            if origin == "fetched":
                target.write_bytes(body)
            manifest.append({"url": url, "file": str(target), "origin": origin,
                             "sha256": hashlib.sha256(body).hexdigest()})
            for row in d["data"]:
                roc = row[0].strip().split("/")
                date = dt.date(int(roc[0]) + 1911, int(roc[1]), int(roc[2])).isoformat()
                taiex[date] = float(row[4].replace(",", ""))
            if origin == "fetched":
                log(f"ok {y}-{m:02d}: {len(d['data'])} days")
        m += 1
        if m == 13:
            y, m = y + 1, 1
    usd = {}
    fred_headers = {"User-Agent": "Mozilla/5.0 (gate-probe research)", "Accept": "text/csv"}
    for sid in ("DTWEXAFEGS", "DTWEXBGS"):
        # 先整段要（timeout 90 秒）；不行就每 4 年一段分開要，每段原始回應都存檔。
        spans = [(f"{start_year}-01-01", today.isoformat())]
        parts = []
        url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={spans[0][0]}&coed={spans[0][1]}"
        body = get(url, headers=fred_headers, timeout=90)
        if body is not None:
            parts.append((url, body))
        else:
            for y0 in range(start_year, today.year + 1, 4):
                a, b = f"{y0}-01-01", min(f"{y0 + 3}-12-31", today.isoformat())
                u = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={sid}&cosd={a}&coed={b}"
                bd = get(u, headers=fred_headers, timeout=90)
                time.sleep(3)
                if bd is None:
                    failures.append({"series": sid, "url": u, "reason": "fetch_failed"})
                else:
                    parts.append((u, bd))
        n = 0
        for i, (u, bd) in enumerate(parts):
            (out / "raw").mkdir(parents=True, exist_ok=True)
            f = out / "raw" / f"{sid}_{i}.csv"
            f.write_bytes(bd)
            manifest.append({"url": u, "file": str(f), "origin": "fetched", "sha256": hashlib.sha256(bd).hexdigest()})
            for r in csv.DictReader(bd.decode().splitlines()):
                v = r.get(sid) or ""
                date = r.get("observation_date") or r.get("DATE")
                if v not in ("", "."):
                    usd.setdefault(date, {})[sid] = v; n += 1
        log(f"{sid}: {n} values from {len(parts)} part(s)")
    dates = sorted(set(taiex) | set(usd))
    with open(out / "taiex_usd.csv", "w", newline="") as f:
        w = csv.writer(f); w.writerow(["date", "taiex_close", "dtwexafegs", "dtwexbgs"])
        for d in dates:
            if d < f"{start_year}-01-01":
                continue
            w.writerow([d, taiex.get(d, ""), usd.get(d, {}).get("DTWEXAFEGS", ""), usd.get(d, {}).get("DTWEXBGS", "")])
    (out / "manifest.json").write_text(json.dumps({
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "complete": not failures, "failures": failures,
        "taiex_days": len(taiex), "taiex_first": min(taiex) if taiex else None,
        "taiex_last": max(taiex) if taiex else None, "files": manifest}, indent=1, ensure_ascii=False))
    log(f"done: taiex {len(taiex)} days; usd dates {len(usd)}; failures {len(failures)}")


if __name__ == "__main__":
    main(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 2006,
         sys.argv[3] if len(sys.argv) > 3 else "results/backtest-data/twse-cache")
