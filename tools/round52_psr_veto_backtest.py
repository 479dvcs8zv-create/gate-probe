#!/usr/bin/env python3
"""第 52 輪：否決紅線「PSR 超過五年高點 20%」會不會誤殺強勢股。
擁有者 2026-11-28 00:15「做完吧」（Gemini 2026-11-27 文件第三節第 4 題）。規則在看結果前寫定（REGISTERED_AT）。

用法：python3 -I tools/round52_psr_veto_backtest.py <股價資料夾> <營收 revenue.csv.gz> <股本資料夾> <輸出資料夾>

一、資料（只做上市：發行股數只有證交所 MI_QFIIS，2012-05 起每月一份）
- 市值＝收盤 × 發行股數（評估日當天或之前最近一份）。
- 近 12 個月營收＝評估日已公布的最近 12 個月營收合計（M 月營收在 M＋1 月 11 日起才算公布，同第 33 輪）；12 個月要連續、都有。
- PSR＝市值 ÷ 近 12 個月營收（營收單位千元，PSR 只和自己比，單位不影響）。
- 五年高點：每月最後一個交易日記一次 PSR；評估日以前 60 個月的最高值，至少要有 48 個月。
- 否決＝PSR > 五年高點 × 1.2（網站現行紅線）。
二、樣本：符合進場三條件（同第 48 輪）的評估日（每 5 個交易日）。2017-05 起（要先累積 48 個月 PSR）。
  結果：之後 20、60 個交易日超額（減同一天全部合格上市＋上櫃股票平均，同第 48 輪）。分 2017-05～2021、2022～最後。
三、事先寫定的判斷（20 日超額，否決組 − 放行組，同月配對）
- 每段否決組至少 30 筆，否則「樣本不足，不判斷」。
- 兩段都 ≤ −1.0 個百分點 → 紅線有用，保留。
- 兩段都 ≥ 0 → 紅線誤殺強勢股，建議移除。
- 其他 → 結果不一致，維持現狀並註明。
- 結果只寫進 gate-probe；網站規則要擁有者看過、同意後才改。
"""
import bisect
import csv
import datetime as dt
import gzip
import json
import math
import statistics
import sys
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from round33_backtest import revenue_index  # noqa: E402
from round45_trust_ratio_backtest import load_shares  # noqa: E402
from stock_signal_backtest import load, signals  # noqa: E402

REGISTERED_AT = "2026-11-28 00:18 台北"
D = dt.date
START = D(2017, 5, 1)
SPLIT = D(2022, 1, 1)


def load_revenue_amounts(path):
    """{code: {(年, 月): 營收}}，只取上市（sii）；同一月份多筆時後者為準（同 revenue_index）。"""
    out = defaultdict(dict)
    with gzip.open(path, "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r["market"] != "sii":
                continue
            try:
                out[r["code"]][(int(r["month"][:4]), int(r["month"][5:7]))] = float(r["revenue"])
            except ValueError:
                continue
    return out


def ttm_revenue(months, d):
    """評估日 d 已公布的最近 12 個月營收合計；不連續或缺月就回 None。"""
    y, m = d.year, d.month
    latest = (y, m - 1) if d.day >= 11 else (y, m - 2)
    ly, lm = latest
    while lm <= 0:
        ly, lm = ly - 1, lm + 12
    total = 0.0
    for k in range(12):
        yy, mm = ly, lm - k
        while mm <= 0:
            yy, mm = yy - 1, mm + 12
        v = months.get((yy, mm))
        if v is None:
            return None
        total += v
    return total if total > 0 else None


def main(price_folder, revenue_path, shares_folder, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    series, _ = load(price_folder)
    rev = revenue_index(revenue_path)
    amounts = load_revenue_amounts(revenue_path)
    shares = load_shares(shares_folder)
    cal = sorted({d for rows in series.values() for d, *_ in rows})
    eval_days = set(cal[::5])
    recs = []
    for (market, code), rows in series.items():
        if len(rows) < 130:
            continue
        dates, close, adj, score, tech, rsi, val20 = signals(rows)
        n = len(rows)
        cs = np.concatenate([[0.0], np.cumsum(adj)])
        ma = lambda k, i: (cs[i + 1] - cs[i + 1 - k]) / k  # noqa: E731
        rv = rev.get((market, code), [])
        rvd = [x[0] for x in rv]
        is_twse = market == "twse"
        sx = shares.get(code) if is_twse else None
        sdates = [x[0] for x in sx] if sx else []
        months = amounts.get(code, {}) if is_twse else {}
        psr_hist = []  # (月底日, PSR)
        for i in range(120, n - 1):
            d = dates[i]
            psr = None
            if sx and months:
                k = bisect.bisect_right(sdates, d) - 1
                ttm = ttm_revenue(months, d) if k >= 0 else None
                if ttm:
                    psr = close[i] * sx[k][1] / (ttm * 1000)
            if psr is not None and (i + 1 == n or dates[i + 1].month != d.month):
                psr_hist.append((d, psr))
            if d not in eval_days or d > cal[-1] - dt.timedelta(days=95):
                continue
            if close[i] < 10 or val20[i] < 1e7 or math.isnan(score[i]) or math.isnan(tech[i]):
                continue
            m5, m10, m20, m120 = ma(5, i), ma(10, i), ma(20, i), ma(120, i)
            j = bisect_right(rvd, d) - 1
            entry = (tech[i] == 0 and score[i] >= 3 and j >= 0 and (d - rv[j][0]).days <= 75 and rv[j][1] > 10
                     and m5 > m20 and m10 > m20 and m5 > m120 and m10 > m120)
            veto = None
            if entry and is_twse and d >= START and psr is not None:
                prior = [p for (pd_, p) in psr_hist if pd_ < d][-60:]
                if len(prior) >= 48:
                    veto = psr > 1.2 * max(prior)
            recs.append((d, entry and veto is not None, veto, adj[min(i + 20, n - 1)] / adj[i] - 1, adj[min(i + 60, n - 1)] / adj[i] - 1))
    by_day = defaultdict(list)
    for r in recs:
        by_day[r[0]].append(r)
    mean = {h: {d: statistics.fmean(x[h] for x in v) for d, v in by_day.items()} for h in (3, 4)}

    def paired(a, b, col, h):
        ma_, mb = defaultdict(list), defaultdict(list)
        for r in a:
            ma_[r[0].isoformat()[:7]].append(r[col] - mean[col][r[0]])
        for r in b:
            mb[r[0].isoformat()[:7]].append(r[col] - mean[col][r[0]])
        ds = [statistics.fmean(ma_[m]) - statistics.fmean(mb[m]) for m in ma_ if m in mb]
        if len(ds) < 2:
            return None
        return {"mean": statistics.fmean(ds), "se": statistics.stdev(ds) / math.sqrt(len(ds)) * math.sqrt(h / 20), "months": len(ds)}

    def group(rows):
        if not rows:
            return None
        return {"n": len(rows), "ex20": statistics.fmean(r[3] - mean[3][r[0]] for r in rows), "ex60": statistics.fmean(r[4] - mean[4][r[0]] for r in rows)}

    summary = {"registeredAt": REGISTERED_AT, "parts": {}}
    checks = {}
    for name, lo, hi in (("2017-2021", START, SPLIT), ("2022-", SPLIT, D(2100, 1, 1))):
        rows = [r for r in recs if r[1] and lo <= r[0] < hi]
        vetoed, kept = [r for r in rows if r[2]], [r for r in rows if not r[2]]
        d20, d60 = paired(vetoed, kept, 3, 20), paired(vetoed, kept, 4, 60)
        summary["parts"][name] = {"vetoed": group(vetoed), "kept": group(kept), "diff20": d20, "diff60": d60}
        if len(vetoed) < 30 or d20 is None:
            checks[name] = {"result": "insufficient", "vetoed": len(vetoed)}
        else:
            checks[name] = {"result": "veto_useful" if d20["mean"] <= -0.01 else "veto_harmful" if d20["mean"] >= 0 else "mixed", "diff20": d20["mean"], "vetoed": len(vetoed)}
    results = {c["result"] for c in checks.values()}
    summary["checks"] = checks
    summary["decision"] = "insufficient_sample" if "insufficient" in results else results.pop() if len(results) == 1 else "inconsistent"
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"decision": summary["decision"], "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:5])
