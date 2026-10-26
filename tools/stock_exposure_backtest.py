#!/usr/bin/env python3
"""第 32 輪（二）：個股持股水位——用「個股技術面」搭配「總經分數」決定每檔持股，是否比固定 65% 好。
擁有者 2026-10-26 09:25：持股以個股為主，持股水位應用技術分析搭配總經判斷，不能只看大盤。規則在看結果前寫定。

用法：python3 -I tools/stock_exposure_backtest.py <股價資料夾> <第31輪 score_history.csv> <輸出資料夾>

一、對象：上市＋上櫃全部 4 碼普通股（含下市），只看「當天合格」的日子：有 66 筆以上歷史、收盤 ≥ 10 元、前 20 日平均成交金額 ≥ 1,000 萬元。
   報酬用除權息還原（同 stock_signal_backtest.py）。收盤算訊號、隔天起生效；現金報酬 0；持股每變動 1 成扣 0.03%（約一買一賣成本的一半）。

二、每檔的持股規則（基準 65%、下限 25%，照擁有者 60～70%／20～30%）：
- A  固定 65%。
- T1 技術：均線強弱分數 ≤ −3 → 25%，否則 65%。
- T2 技術：三問「技術」不過（連續 >5 日在 60 日線下且 60 日線下彎）→ 25%，否則 65%。
- M  總經：第 31 輪 20 日平均總經分數低於自身歷史第 10 百分位（至少 3 年）→ 25%，否則 65%。
- TM 技術＋總經：三問技術不過「而且」20 日平均總經分數 < 55（網站橘燈以下）→ 25%，否則 65%。
- TM2 技術＋總經：三問技術不過「而且」20 日平均總經分數 < 70（網站非綠燈）→ 25%，否則 65%。

三、結果
- 每檔各自算年化報酬與最大跌幅（至少 3 年合格資料），看各規則相對 A 的中位數差距、勝過 A 的比例。
- 另做「全部合格股票等權」組合：每天把所有合格股票等權持有，每檔照規則決定持股，算組合年化與最大跌幅。
- 分 2006–2015、2016–2026；另看電子股為主的上櫃。
"""
import csv
import datetime as dt
import json
import math
import sys
from bisect import bisect_right
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from stock_signal_backtest import load, signals  # noqa: E402

D = dt.date
COST = 0.0003  # 每變動 0.1 持股的成本


def macro_series(path):
    rows = list(csv.DictReader(open(path)))
    dates = [D.fromisoformat(r["date"]) for r in rows]
    raw = [float(r["raw"]) for r in rows]
    ma = [sum(raw[max(0, i - 19):i + 1]) / len(raw[max(0, i - 19):i + 1]) for i in range(len(raw))]
    low = []
    hist = []
    for i, v in enumerate(ma):
        hist.append(v)
        enough = (dates[i] - dates[0]).days >= 3 * 365
        if enough:
            s = sorted(hist)
            low.append(v < s[int(0.1 * (len(s) - 1))])
        else:
            low.append(False)
    return dates, ma, low


def lookup(dates, values, d):
    i = bisect_right(dates, d) - 1
    return values[i] if i >= 0 else None


def run(series, macro, lo=None, hi=None, market=None):
    mdates, mma, mlow = macro
    rules = ["A", "T1", "T2", "M", "TM", "TM2"]
    per_stock = {r: [] for r in rules}
    port = {r: {} for r in rules}  # date -> list of (weight*ret) for equal-weight portfolio
    for (mk, code), rows in series.items():
        if market and mk != market:
            continue
        if len(rows) < 70:
            continue
        dates, close, adj, score, tech, rsi, val20 = signals(rows)
        n = len(rows)
        eq = {r: 1.0 for r in rules}; peak = {r: 1.0 for r in rules}; mdd = {r: 0.0 for r in rules}; prev_w = {r: None for r in rules}
        start = end = None; days = 0
        for i in range(65, n - 1):
            d = dates[i]
            if (lo and d < lo) or (hi and d > hi):
                continue
            ok = close[i] >= 10 and val20[i] >= 1e7 and not math.isnan(score[i]) and not math.isnan(tech[i])
            if not ok:
                prev_w = {r: None for r in rules}
                continue
            mm = lookup(mdates, mma, d); ml = lookup(mdates, mlow, d)
            if mm is None:
                continue
            w = {"A": 0.65,
                 "T1": 0.25 if score[i] <= -3 else 0.65,
                 "T2": 0.25 if tech[i] == 1 else 0.65,
                 "M": 0.25 if ml else 0.65,
                 "TM": 0.25 if tech[i] == 1 and mm < 55 else 0.65,
                 "TM2": 0.25 if tech[i] == 1 and mm < 70 else 0.65}
            r_next = adj[i + 1] / adj[i] - 1
            nd = dates[i + 1]
            for r in rules:
                c = COST * abs(w[r] - prev_w[r]) * 10 if prev_w[r] is not None else COST * w[r] * 10
                g = w[r] * r_next - c
                eq[r] *= 1 + g; peak[r] = max(peak[r], eq[r]); mdd[r] = min(mdd[r], eq[r] / peak[r] - 1)
                port[r].setdefault(nd, []).append(g)
                prev_w[r] = w[r]
            start = start or d; end = nd; days += 1
        if start and (end - start).days >= 3 * 365 and days >= 500:
            years = (end - start).days / 365.25
            for r in rules:
                per_stock[r].append((eq[r] ** (1 / years) - 1, mdd[r]))
    out = {}
    base = per_stock["A"]
    for r in rules:
        xs = per_stock[r]
        if not xs:
            continue
        dc = [x[0] - b[0] for x, b in zip(xs, base)]; dm = [x[1] - b[1] for x, b in zip(xs, base)]
        pdates = sorted(port[r]); peq = 1.0; ppeak = 1.0; pmdd = 0.0
        for d in pdates:
            peq *= 1 + float(np.mean(port[r][d])); ppeak = max(ppeak, peq); pmdd = min(pmdd, peq / ppeak - 1)
        yrs = (pdates[-1] - pdates[0]).days / 365.25 if len(pdates) > 1 else float("nan")
        out[r] = {"stocks": len(xs), "median_cagr": float(np.median([x[0] for x in xs])), "median_mdd": float(np.median([x[1] for x in xs])),
                  "median_cagr_vs_A": float(np.median(dc)), "median_mdd_vs_A": float(np.median(dm)),
                  "share_cagr_better": float(np.mean([v > 0 for v in dc])), "share_mdd_better": float(np.mean([v > 0 for v in dm])),
                  "portfolio_cagr": peq ** (1 / yrs) - 1 if yrs == yrs else None, "portfolio_mdd": pmdd}
    return out


def main(folder, score_csv, outdir):
    outdir = Path(outdir); outdir.mkdir(parents=True, exist_ok=True)
    series, stats = load(folder)
    macro = macro_series(score_csv)
    lines = []
    p = lines.append
    names = {"A": "A 固定 65%", "T1": "T1 均線 ≤ −3 → 25%", "T2": "T2 技術不過 → 25%", "M": "M 總經低於歷史第10百分位 → 25%",
             "TM": "TM 技術不過且總經 < 55 → 25%", "TM2": "TM2 技術不過且總經 < 70 → 25%"}
    result = {}
    for title, kw in (("全期，上市＋上櫃", {}), ("2006–2015", {"hi": D(2015, 12, 31)}), ("2016–2026", {"lo": D(2016, 1, 1)}),
                      ("全期，只看上櫃", {"market": "tpex"}), ("全期，只看上市", {"market": "twse"})):
        r = run(series, macro, **kw)
        result[title] = r
        p(f"\n## {title}")
        p("規則 | 檔數 | 每檔年化（中位數） | 每檔最大跌幅（中位數） | 年化比A（中位數） | 跌幅比A改善（中位數） | 年化勝A比例 | 跌幅勝A比例 | 等權組合年化 | 等權組合最大跌幅")
        for k in ("A", "T1", "T2", "M", "TM", "TM2"):
            x = r.get(k)
            if not x:
                continue
            p(f"{names[k]} | {x['stocks']} | {x['median_cagr']*100:+.2f}% | {x['median_mdd']*100:.1f}% | {x['median_cagr_vs_A']*100:+.2f} 點 | "
              f"{x['median_mdd_vs_A']*100:+.1f} 點 | {x['share_cagr_better']*100:.0f}% | {x['share_mdd_better']*100:.0f}% | "
              f"{(x['portfolio_cagr'] or 0)*100:+.2f}% | {x['portfolio_mdd']*100:.1f}%")
    (outdir / "exposure.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (outdir / "exposure.json").write_text(json.dumps(result, ensure_ascii=False, indent=1))
    print("\n".join(lines))


if __name__ == "__main__":
    main(*sys.argv[1:])
