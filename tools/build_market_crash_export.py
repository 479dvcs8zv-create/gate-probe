#!/usr/bin/env python3
"""大盤股災日匯出（網站 v252「股災本益比參考價」用）。擁有者 2026-11-03 07:20「好」。

規則（與第 38 輪回測相同）：加權指數收盤 ≤ 前 250 個交易日（含當天）最高收盤 × 85% 的交易日＝股災日。

用法：python3 -I tools/build_market_crash_export.py <exports/market-crash 資料夾> [啟動用 taiex_usd.csv]
- 歷史收盤存在 <資料夾>/taiex.csv（date,close）。第一次用 taiex_usd.csv 的 taiex_close 啟動（同為證交所 MI_5MINS_HIST）。
- 每次向證交所 MI_5MINS_HIST 補抓「最後一筆所在月份到本月」（官方、免金鑰，每次間隔 4 秒）；同一天以新抓的官方值為準。
- 抓不到不補值：沿用已存收盤，failures 照實寫；through＝最後一筆收盤日。
- 輸出 latest.json：schema gate-probe/market-crash/v1、rule、source、through、crash_days（2015 起）、periods、current（當天收盤、前一年最高、回檔幅度、是否股災）。
- 內容沒變（除 generated_at 外）就不改寫，避免無意義的提交。
"""
import csv
import datetime as dt
import json
import sys
import time
import urllib.request
from pathlib import Path

SCHEMA = "gate-probe/market-crash/v1"
URL = "https://www.twse.com.tw/rwd/zh/TAIEX/MI_5MINS_HIST?date={y}{m:02d}01&response=json"
UA = {"User-Agent": "Mozilla/5.0 (gate-probe research)"}
THRESHOLD, WINDOW, SINCE = 0.85, 250, "2015-01-01"


def fetch_month(y, m):
    url = URL.format(y=y, m=m)
    last = None
    for n in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=30) as r:
                d = json.loads(r.read())
            if d.get("stat") != "OK" or not d.get("data"):
                raise ValueError(f"stat={d.get('stat')!r}")
            out = {}
            for row in d["data"]:
                roc = row[0].strip().split("/")
                out[dt.date(int(roc[0]) + 1911, int(roc[1]), int(roc[2])).isoformat()] = float(row[4].replace(",", ""))
            return out, None
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(10 * (n + 1))
    return {}, {"month": f"{y}-{m:02d}", "url": url, "error": str(last)[:200]}


def compute(closes, through=None):
    dates = sorted(closes)
    vals = [closes[d] for d in dates]
    flags, maxes = [], []
    for i, v in enumerate(vals):
        lo = max(0, i - WINDOW)
        j = max(range(lo, i + 1), key=lambda k: vals[k])
        maxes.append((vals[j], dates[j]))
        flags.append(v <= vals[j] * THRESHOLD)
    crash_days = [d for d, f in zip(dates, flags) if f and d >= SINCE]
    periods, cur = [], None
    for i, (d, f) in enumerate(zip(dates, flags)):
        if d < SINCE:
            continue
        if f:
            dd = vals[i] / maxes[i][0] - 1
            if cur is None:
                cur = {"from": d, "to": d, "low_date": d, "low_drawdown": round(dd, 4)}
            else:
                cur["to"] = d
                if dd < cur["low_drawdown"]:
                    cur["low_date"], cur["low_drawdown"] = d, round(dd, 4)
        elif cur:
            periods.append(cur); cur = None
    if cur:
        periods.append(cur)
    i = len(dates) - 1
    current = {"date": dates[i], "close": vals[i], "max250": maxes[i][0], "max250_date": maxes[i][1],
               "drawdown": round(vals[i] / maxes[i][0] - 1, 4), "in_crash": flags[i]}
    return crash_days, periods, current


def main(folder, bootstrap=None):
    folder = Path(folder); folder.mkdir(parents=True, exist_ok=True)
    hist = folder / "taiex.csv"
    closes = {}
    if hist.exists():
        with open(hist, newline="") as f:
            closes = {r["date"]: float(r["close"]) for r in csv.DictReader(f)}
    elif bootstrap:
        with open(bootstrap, newline="") as f:
            closes = {r["date"]: float(r["taiex_close"]) for r in csv.DictReader(f) if r.get("taiex_close")}
    if not closes:
        raise SystemExit("沒有歷史收盤可用（需要 taiex.csv 或啟動用 taiex_usd.csv）")
    last = dt.date.fromisoformat(max(closes))
    today = dt.date.today()
    failures = []
    y, m = last.year, last.month
    while (y, m) <= (today.year, today.month):
        got, fail = fetch_month(y, m)
        closes.update(got)
        if fail:
            failures.append(fail)
        time.sleep(4)
        m += 1
        if m == 13:
            y, m = y + 1, 1
    with open(hist, "w", newline="") as f:
        w = csv.writer(f); w.writerow(["date", "close"])
        for d in sorted(closes):
            w.writerow([d, closes[d]])
    crash_days, periods, current = compute(closes)
    body = {"schema": SCHEMA, "url": "https://raw.githubusercontent.com/479dvcs8zv-create/gate-probe/main/exports/market-crash/latest.json",
            "use": "網站 v252 股災本益比參考價：只作左側交易參考，不影響評級。股災日＝加權指數收盤 ≤ 前 250 個交易日（含當天）最高收盤 × 85%。",
            "rule": {"threshold": THRESHOLD, "window": WINDOW, "since": SINCE},
            "source": "臺灣證券交易所 MI_5MINS_HIST（發行量加權股價指數歷史資料，每月一檔）", "source_url_pattern": URL,
            "through": current["date"], "history_from": min(closes), "crash_days": crash_days, "periods": periods, "current": current,
            "failures": failures}
    target = folder / "latest.json"
    if target.exists():
        old = json.loads(target.read_text(encoding="utf-8"))
        if {k: v for k, v in old.items() if k != "generated_at"} == body:
            print("unchanged", current)
            return
    body = {"generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), **body}
    target.write_text(json.dumps(body, ensure_ascii=False, indent=1), encoding="utf-8")
    print("written", current, "crash_days", len(crash_days), "periods", len(periods), "failures", failures)


if __name__ == "__main__":
    main(*sys.argv[1:3])
