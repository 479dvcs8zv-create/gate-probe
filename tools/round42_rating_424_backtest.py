#!/usr/bin/env python3
"""第 42 輪：先用估值評級挑股票（A、B+），再用 424 分批買。擁有者 2026-11-11 16:13「好」。規則在看結果前寫定（2026-11-11 16:30）。

用法：python3 -I tools/round42_rating_424_backtest.py <股價資料夾> <第 38 輪 records.csv.gz> <輸出資料夾>

一、評級（沿用第 38 輪每 20 個交易日一次的評級紀錄，2019-01 起）
- 主：CUR_ma（網站現行估值＋均線降級）；次：G_CRASH_ma（擁有者的 EPS 算法＋股災本益比＋均線降級）。
- 「估值分歧」（divergent=yes，網站本來就不評）不列入。
- 便宜組＝A、B+；貴組＝C、D。

二、每個評估日、每檔股票各自模擬一筆（同一檔不同評估日可能重疊，誤差用月份平均粗估）：
- HOLD120：評估日收盤一次買 10 單位，抱 120 個交易日（＝第 38 輪的看法，接近「評級好就買、放著」）。
- 以下三種都等「評估日起 20 個交易日內第一次收盤站上 20 日線」才開始（沒有訊號＝沒交易，報酬 0）；停損：比平均成本低 8% 全出；
  最多抱 250 個交易日，到期用收盤計值：
  - P424：第 41b 輪修正版 424（4→2→4 分批買；賺 5% 賣 4、破 5 日線賣 2、之後失守下彎月線或近 20 日低點賣光）。
  - P424H：424 分批買，但不先賣：曾到 +5% 之後，失守下彎月線或近 20 日低點才一次全賣（Claude 2026-11-11 的建議）。
  - ALLH：訊號那天一次買 10，賣法同 P424H。
- 成本：買 0.1425%；賣 0.1425%＋證交稅 0.3%。報酬都以 10 單位為本金。

三、分段：2019-01～2021-12、2022-01～最後（同第 38 輪）。先算每個評估日的平均，再對評估日平均；標準誤 × √(持有天數 ÷ 20) 粗估重疊（取 6）。

四、事先寫定的判斷（主＝CUR_ma）
1. 評級有沒有用：P424H 的「便宜組平均 − 貴組平均」兩段都 ≥ +1 個百分點。
2. 分批買適不適合評級好的股票：便宜組裡，P424H 的最差 10% 比 ALLH 少賠 ≥ 1 點，而且平均不少於 ALLH 0.5 點以上，兩段都成立。
3. 拿掉「賺 5% 先賣 4 成」：便宜組裡，P424H 平均 ≥ P424 平均，兩段都成立。
4. 和「評級好就買、放 120 天」比：只列數字（期間不同、資金占用不同，不做判斷）。
結果只寫進 gate-probe；網站規則要擁有者看過回測、同意後才改。
"""
import csv
import datetime as dt
import gzip
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import round41_424_backtest as base  # noqa: E402
from stock_signal_backtest import load  # noqa: E402

SPLIT = "2022-01-01"
CHEAP, DEAR = {"A", "B+"}, {"C", "D"}


def trade(t0, adj, ma5, ma20, ma60, low20, style, n, cap=250):
    b = base.Book()
    b.buy(4 if style in ("P424", "P424H") else 10, adj[t0])
    added2 = added4 = sold1 = sold2 = reached5 = broke = False
    pull_low = None
    end = min(n - 1, t0 + cap)
    for t in range(t0 + 1, end + 1):
        price = adj[t]
        trend_exit = (price < ma20[t] and ma20[t] < ma20[t - 1]) or price < low20[t]
        if b.units and price <= b.cost * 0.92:
            b.sell(b.units, price)
        elif style in ("P424H", "ALLH"):
            reached5 = reached5 or price >= b.cost * 1.05
            if reached5 and trend_exit:
                b.sell(b.units, price)
        else:
            if sold1 and sold2 and trend_exit:
                b.sell(b.units, price)
            elif not sold1 and b.units and price >= b.cost * 1.05:
                b.sell(4, price)
                sold1 = True
            elif sold1 and not sold2 and price < ma5[t]:
                b.sell(2, price)
                sold2 = True
        can_add = b.units and not reached5 and (style == "P424H" or (style == "P424" and not sold1))
        if can_add:
            if not added2 and (price <= ma20[t] * 1.01 or price <= ma60[t] * 1.01):
                pull_low = float(np.min(adj[t0:t + 1]))
                b.buy(2, price)
                added2 = True
            elif added2 and not added4 and not broke:
                if price < pull_low:
                    broke = True
                elif price > ma20[t] and adj[t - 1] <= ma20[t - 1]:
                    b.buy(4, price)
                    added4 = True
        if b.units == 0:
            return b.cash_pnl / 10, t - t0
    return b.mark(adj[end]) / 10, end - t0


def stats(rows, key="ret", hold=6):
    by = defaultdict(list)
    for r in rows:
        by[r["date"]].append(r[key])
    means = [statistics.fmean(v) for v in by.values()]
    allv = [r[key] for r in rows]
    if not means:
        return None
    return {"mean": statistics.fmean(means), "se": statistics.stdev(means) / math.sqrt(len(means)) * math.sqrt(hold) if len(means) > 1 else None,
            "median": statistics.median(allv), "p10": float(np.percentile(allv, 10)), "lose": sum(1 for x in allv if x < 0) / len(allv),
            "n": len(allv), "days": statistics.fmean(r["days"] for r in rows)}


def main(price_folder, records_path, out_folder):
    out = Path(out_folder)
    out.mkdir(parents=True, exist_ok=True)
    recs = defaultdict(list)
    with gzip.open(records_path, "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r["divergent"] == "yes":
                continue
            recs[r["code"]].append((dt.date.fromisoformat(r["date"]), r["CUR_ma"], r["G_CRASH_ma"]))
    series, _ = load(price_folder)
    rows_out = []
    for (market, code), rows in series.items():
        if code not in recs or len(rows) < 200:
            continue
        dates = [r[0] for r in rows]
        index = {d: i for i, d in enumerate(dates)}
        rets = np.array([r[2] if r[2] is not None else 0.0 for r in rows], dtype=float)
        adj = np.cumprod(1 + rets)
        ma5, ma20, ma60 = base.moving_average(adj, 5), base.moving_average(adj, 20), base.moving_average(adj, 60)
        low20 = np.full(len(adj), np.nan)
        for i in range(20, len(adj)):
            low20[i] = adj[i - 20:i].min()
        n = len(adj)
        for d, cur, gc in recs[code]:
            te = index.get(d)
            if te is None or te < 61 or te + 120 >= n:
                continue
            row = {"code": code, "date": d.isoformat(), "CUR": cur, "GC": gc}
            row["HOLD120"] = float(adj[te + 120] / adj[te] * (1 - base.SELL_COST) / (1 + base.BUY_COST) - 1)
            sig = next((t for t in range(max(te, 1), min(te + 20, n - 1) + 1) if adj[t] > ma20[t] and adj[t - 1] <= ma20[t - 1]), None)
            for style in ("P424", "P424H", "ALLH"):
                if sig is None:
                    row[style], row[style + "_days"] = 0.0, 0
                else:
                    row[style], row[style + "_days"] = trade(sig, adj, ma5, ma20, ma60, low20, style, n)
            row["signal"] = sig is not None
            rows_out.append(row)
    report = {}
    for rating in ("CUR", "GC"):
        report[rating] = {}
        for part, sel in (("2019-2021", [r for r in rows_out if r["date"] < SPLIT]), ("2022-", [r for r in rows_out if r["date"] >= SPLIT])):
            report[rating][part] = {}
            for grp, grades in (("cheap", CHEAP), ("dear", DEAR), ("all", None)):
                g = [r for r in sel if grades is None or r[rating] in grades]
                report[rating][part][grp] = {s: stats([{"date": r["date"], "ret": r[s], "days": r.get(s + "_days", 120)} for r in g]) for s in ("HOLD120", "P424", "P424H", "ALLH")}
                report[rating][part][grp]["signalRate"] = sum(r["signal"] for r in g) / len(g) if g else None
    checks = {}
    for part in ("2019-2021", "2022-"):
        c = report["CUR"][part]
        checks[part] = {
            "rating_useful": c["cheap"]["P424H"]["mean"] - c["dear"]["P424H"]["mean"] >= 0.01,
            "scale_in_fits": c["cheap"]["P424H"]["p10"] >= c["cheap"]["ALLH"]["p10"] + 0.01 and c["cheap"]["P424H"]["mean"] >= c["cheap"]["ALLH"]["mean"] - 0.005,
            "drop_early_sell": c["cheap"]["P424H"]["mean"] >= c["cheap"]["P424"]["mean"],
        }
    decision = {k: all(checks[p][k] for p in checks) for k in ("rating_useful", "scale_in_fits", "drop_early_sell")}
    (out / "summary.json").write_text(json.dumps({"report": report, "checks": checks, "decision": decision, "evaluations": len(rows_out)}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"evaluations": len(rows_out), "decision": decision, "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:4])
