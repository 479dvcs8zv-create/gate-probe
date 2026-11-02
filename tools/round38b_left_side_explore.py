#!/usr/bin/env python3
"""第 38 輪補充（探索，非事先登記）：擁有者 2026-11-03 07:17——股災本益比 × 今年獲利＝參考價，當「左側交易」（逢低承接）依據。

問題：現價跌到「今年 EPS × 股災時本益比」參考價以下時買進，之後 1 年（250 個交易日）表現如何？
- 參考價：低＝今年 EPS × 股災本益比 P20、中＝× 中位數（今年 EPS 用網站現行 S_cap 的中位數；另列擁有者 G）。
- 分組：現價 ≤ 低參考價、低～中之間、高於中參考價；再分「買進當時大盤是否在股災中」與「近四季 EPS 是否 > 7 年中位數 2 倍（景氣高峰）」。
- 指標：250 日還原報酬減同日全部合格股票平均（超額）、250 日內最大跌幅 ≥ 30% 比例、250 日後仍虧損的比例。
- 合格條件、資料與時間點規則同 tools/round38_owner_valuation_backtest.py。這是探索，結果只供擁有者參考，不改網站規則。

用法：python3 -I tools/round38b_left_side_explore.py <股價資料夾> <eps.csv.gz> <revenue.csv.gz> <taiex_usd.csv> <輸出資料夾>
"""
import csv
import datetime as dt
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from stock_signal_backtest import load  # noqa: E402
from round38_owner_valuation_backtest import load_eps, load_revenue, eps_estimates, ttm_events, pct  # noqa: E402

D = dt.date
H = 250


def main(price_folder, eps_path, rev_path, taiex_path, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    series, _ = load(price_folder)
    ytd, revenue = load_eps(eps_path), load_revenue(rev_path)
    tx = [(D.fromisoformat(r["date"]), float(r["taiex_close"])) for r in csv.DictReader(open(taiex_path)) if r["taiex_close"]]
    crash = {d: c <= 0.85 * max(x for _, x in tx[max(0, i - 250):i + 1]) for i, (d, c) in enumerate(tx)}
    cal = sorted({d for rows in series.values() for d, *_ in rows})
    evals = set(d for d in cal[::20] if d >= D(2019, 1, 1))
    recs = []
    for (market, code), rows in series.items():
        q = ytd.get(code)
        ev = ttm_events(q) if q else []
        if not ev:
            continue
        n = len(rows); dates = [r[0] for r in rows]
        close = np.array([r[1] for r in rows], float); value = np.array([r[3] for r in rows], float)
        adj = np.cumprod(1 + np.array([r[2] if r[2] is not None else 0.0 for r in rows], float))
        pe = np.full(n, np.nan); ttm = np.full(n, np.nan); j = -1
        for i, d in enumerate(dates):
            while j + 1 < len(ev) and ev[j + 1][0] < d:
                j += 1
            if j >= 0:
                ttm[i] = ev[j][1]
                if ev[j][1] > 0 and close[i] > 0:
                    pe[i] = close[i] / ev[j][1]
        cmask = np.array([crash.get(d, False) for d in dates])
        for i, d in enumerate(dates):
            if d not in evals or i < 60 or i + H >= n or close[i] < 10 or value[i - 20:i].mean() < 1e7 or not ttm[i] > 0:
                continue
            cpe = pe[:i + 1][cmask[:i + 1]]; cpe = cpe[~np.isnan(cpe)]
            if len(cpe) < 20:
                continue
            eps, fy = eps_estimates(q, revenue.get(code, {}), d)
            years = sorted(fy)[-7:]
            med7 = statistics.median(fy[y] for y in years) if len(years) >= 5 else None
            path = adj[i + 1:i + H + 1] / adj[i]
            rec = {"date": d.isoformat(), "code": code, "r": float(path[-1] - 1), "low": float(path.min() - 1), "market_crash": bool(crash.get(d, False)),
                   "peak": bool(med7 and med7 > 0 and ttm[i] / med7 > 2)}
            lo, mid = pct(cpe, .2), pct(cpe, .5)
            for key, e in (("site", eps.get("S_cap")), ("owner", eps.get("G"))):
                if e and e[1] > 0:
                    rec[key] = "below_low" if close[i] <= e[1] * lo else "low_to_mid" if close[i] <= e[1] * mid else "above_mid"
                else:
                    rec[key] = None
            recs.append(rec)
    by = defaultdict(list)
    for r in recs:
        by[r["date"]].append(r)
    for rows in by.values():
        m = sum(r["r"] for r in rows) / len(rows)
        for r in rows:
            r["x"] = r["r"] - m

    def summ(rows):
        if not rows:
            return {"obs": 0}
        per = defaultdict(list)
        for r in rows:
            per[r["date"]].append(r["x"])
        means = [sum(v) / len(v) for v in per.values()]
        se = statistics.stdev(means) / math.sqrt(len(means)) * math.sqrt(H / 20) if len(means) > 2 else None
        return {"obs": len(rows), "dates": len(means), "x250%": round(100 * sum(means) / len(means), 2), "se%": round(100 * se, 2) if se else None,
                "loss%": round(100 * sum(r["r"] < 0 for r in rows) / len(rows), 1), "drop30%": round(100 * sum(r["low"] <= -0.3 for r in rows) / len(rows), 1)}

    res = {"records": len(recs), "all": summ(recs), "groups": {}}
    for key in ("site", "owner"):
        for zone in ("below_low", "low_to_mid", "above_mid"):
            base = [r for r in recs if r[key] == zone]
            res["groups"][f"{key}|{zone}"] = {"all": summ(base), "in_crash": summ([r for r in base if r["market_crash"]]), "not_crash": summ([r for r in base if not r["market_crash"]]),
                                               "cycle_peak": summ([r for r in base if r["peak"]]), "not_peak": summ([r for r in base if not r["peak"]])}
    json.dump(res, open(out / "left_side.json", "w"), ensure_ascii=False, indent=1)
    print("records", len(recs), "all", res["all"])
    for k, v in res["groups"].items():
        print(k, {kk: (vv.get("obs"), vv.get("x250%"), vv.get("se%"), vv.get("loss%"), vv.get("drop30%")) for kk, vv in v.items()})


if __name__ == "__main__":
    main(*sys.argv[1:6])
