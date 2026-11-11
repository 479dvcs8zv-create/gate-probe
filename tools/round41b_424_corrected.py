#!/usr/bin/env python3
"""第 41b 輪：修正第 41 輪的規則翻譯（看過第 41 輪結果之後才改，**不是事先寫定的版本**，報告時要分開說）。

第 41 輪的問題：把原文賣法第 3 步（失守下彎 20 日線／近一個月低點就全賣）設成「任何時候都適用」。
剛站上月線時 20 日線通常還在往下彎，一拉回就觸發全賣，結果平均只抱 7～13 天；
而且和原文買法第 2 步（拉回月線要加碼 2 單位）互相衝突——原文第 3 步是「最後的步驟來到處理剩下的 4 單位」，只在賣過前兩步之後才用。

這裡的改法（其他和第 41 輪相同）：
- 424c：賣法第 3 步只在賣法第 1、2 步都做完之後才用；之前只靠停損出場（主版本：收盤比平均成本低 8%；另列 60 日線、不停損）。
- ALL_SAME_c：一次買 10，賣法同 424c。
- ALL_SIMPLE_c：一次買 10；曾經到過 +5% 之後，收盤失守下彎 20 日線或近 20 日最低收盤就全賣；停損同上。
- HOLD120：同第 41 輪。
判斷標準沿用第 41 輪寫好的三條。沒到資料最後一天還沒賣完的，用最後一天收盤計值。

用法：python3 -I tools/round41b_424_corrected.py <股價資料夾> <輸出資料夾>
"""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import round41_424_backtest as base  # noqa: E402
from stock_signal_backtest import load  # noqa: E402


def run_trade(t0, adj, ma5, ma20, ma60, low20, style, stop, n):
    b = base.Book()
    b.buy(4 if style == "424c" else 10, adj[t0])
    added2 = added4 = sold1 = sold2 = reached5 = broke = False
    pull_low = None
    for t in range(t0 + 1, n):
        b.unit_days += b.units
        price = adj[t]
        if style == "HOLD120":
            if t - t0 >= 120:
                b.sell(10, price)
                return b.cash_pnl / 10, t - t0, b.unit_days / (t - t0) / 10, False
            continue
        trend_exit = (price < ma20[t] and ma20[t] < ma20[t - 1]) or price < low20[t]
        if b.units and ((stop == "pct8" and price <= b.cost * 0.92) or (stop == "ma60" and price < ma60[t])):
            b.sell(b.units, price)
        elif style == "ALL_SIMPLE_c":
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
            elif style == "424c" and not sold1 and b.units:
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
            days = t - t0
            return b.cash_pnl / 10, days, b.unit_days / days / 10 if days else 0, False
    days = n - 1 - t0
    return b.mark(adj[n - 1]) / 10, days, (b.unit_days / days / 10) if days else 0, True


def main(price_folder, out_folder):
    out = Path(out_folder)
    out.mkdir(parents=True, exist_ok=True)
    series, _ = load(price_folder)
    styles = [("424c", "pct8"), ("ALL_SAME_c", "pct8"), ("ALL_SIMPLE_c", "pct8"), ("HOLD120", None), ("424c", "ma60"), ("ALL_SAME_c", "ma60"), ("ALL_SIMPLE_c", "ma60"), ("424c", "none"), ("ALL_SAME_c", "none"), ("ALL_SIMPLE_c", "none")]
    trades = defaultdict(list)
    for (market, code), rows in series.items():
        if len(rows) < 200:
            continue
        dates = [r[0] for r in rows]
        close = np.array([r[1] for r in rows], dtype=float)
        rets = np.array([r[2] if r[2] is not None else 0.0 for r in rows], dtype=float)
        value = np.array([r[3] for r in rows], dtype=float)
        adj = np.cumprod(1 + rets)
        ma5, ma20, ma60 = base.moving_average(adj, 5), base.moving_average(adj, 20), base.moving_average(adj, 60)
        low20 = np.full(len(adj), np.nan)
        for i in range(20, len(adj)):
            low20[i] = adj[i - 20:i].min()
        ok = (close >= 10) & (base.moving_average(value, 20) >= 1e7)
        n = len(adj)
        for style, stop in styles:
            label = f"{style}|{stop}"
            t = 61
            while t < n - 1:
                if dates[t] >= base.START and ok[t] and not np.isnan(ma60[t]) and adj[t] > ma20[t] and adj[t - 1] <= ma20[t - 1]:
                    ret, days, avg_units, open_end = run_trade(t, adj, ma5, ma20, ma60, low20, style, stop, n)
                    trades[label].append({"code": code, "date": dates[t].isoformat(), "month": dates[t].isoformat()[:7], "ret": ret, "days": days,
                                          "units": avg_units, "eff": ret / (avg_units * days) * 100 if avg_units and days else 0.0, "open": open_end})
                    t += max(days, 1)
                else:
                    t += 1
    report = {}
    for label, rows in trades.items():
        report[label] = {}
        for part, sel in (("2010-2017", [r for r in rows if r["date"] < base.SPLIT]), ("2018-", [r for r in rows if r["date"] >= base.SPLIT]), ("all", rows)):
            report[label][part] = {"ret": base.summarize(sel, "ret"), "eff": base.summarize(sel, "eff"), "days": statistics.fmean(r["days"] for r in sel),
                                   "units": statistics.fmean(r["units"] for r in sel), "open": sum(r["open"] for r in sel)}
    checks = {}
    for stop in ("pct8", "ma60"):
        for part in ("2010-2017", "2018-"):
            a, s, m = (report[f"{x}|{stop}"][part]["ret"] for x in ("424c", "ALL_SAME_c", "ALL_SIMPLE_c"))
            checks[f"{stop}:{part}"] = {"scale_in_safer": a["p10"] >= s["p10"] + 0.01, "scale_in_not_worse": a["mean"] >= s["mean"] - 0.005,
                                        "scale_out_better": s["mean"] >= m["mean"] and s["p10"] >= m["p10"]}
    decision = {stop: {k: all(checks[f"{stop}:{p}"][k] for p in ("2010-2017", "2018-")) for k in ("scale_in_safer", "scale_in_not_worse", "scale_out_better")} for stop in ("pct8", "ma60")}
    examples = {c: [r for r in trades["424c|pct8"] if r["code"] == c and r["date"] >= "2025-09-01"] for c in ("6669", "2330", "8131")}
    (out / "summary_corrected.json").write_text(json.dumps({"note": "post-registration correction of round 41 rule translation", "report": report, "checks": checks, "decision": decision, "examples2025": examples}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"decision": decision}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:3])
