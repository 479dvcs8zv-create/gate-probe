#!/usr/bin/env python3
"""第 43 輪：組合做法回測。擁有者 2026-11-12 08:08「一起處理」。規則在看結果前寫定（2026-11-12 08:20）。

組合做法（Claude 2026-11-11 建議、還沒一起測過）：評級挑股票 → 424 分批買 → 不要賺 5% 先賣 → 跌破月線＋季線降級減碼。

用法：python3 -I tools/round43_combo_backtest.py <股價資料夾> <第 38 輪 records.csv.gz> <輸出資料夾>

一、樣本：同第 42 輪（第 38 輪評級紀錄，2019 起每 20 個交易日一次，估值分歧不列入；主評級 CUR_ma）。
二、做法（都從「評估日起 20 個交易日內第一次收盤站上 20 日線」那天開始；沒有訊號＝沒交易、報酬 0；最多 250 個交易日，到期用收盤計值）：
- P424H：同第 42 輪（424 分批買；比平均成本低 8% 全出；曾到 +5% 之後，失守下彎月線或近 20 日最低收盤才全賣）。
- COMBO：P424H ＋「降級減碼」：持有期間第一次收盤同時低於 20 日線與 60 日線 → 賣掉當時持股的一半（只做一次；之後不再加碼）。
- COMBO_FULL：同 COMBO，但降級時全部賣掉（＝收盤跌破月線和季線就出場）。
- HOLD120：評估日買、抱 120 天（參考）。
成本：買 0.1425%；賣 0.1425%＋證交稅 0.3%；報酬以 10 單位為本金。
三、分段：2019-01～2021-12、2022-01～最後；誤差算法同第 42 輪。
四、事先寫定的判斷（便宜組＝A、B+）
1. 降級減碼有沒有用：兩段都「COMBO 的最差 10% ≥ P424H ＋ 0.5 點」且「COMBO 平均 ≥ P424H − 0.3 點」。
2. 降級全出比減半好不好：兩段都「COMBO_FULL 平均 ≥ COMBO」且「最差 10% ≥ COMBO」→ 支持全出；否則維持減半（若判斷 1 成立）。
3. 評級挑股：兩段都「COMBO 便宜組平均 − 貴組平均 ≥ +1 點」。
4. 和抱 120 天比：只列數字。
結果只寫進 gate-probe；網站規則要擁有者看過回測、同意後才改。
"""
import csv
import datetime as dt
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
import round41_424_backtest as base  # noqa: E402
from round42_rating_424_backtest import CHEAP, DEAR, SPLIT, stats  # noqa: E402
from stock_signal_backtest import load  # noqa: E402


def trade(t0, adj, ma20, ma60, low20, style, n, cap=250):
    b = base.Book()
    b.buy(4, adj[t0])
    added2 = added4 = reached5 = broke = downgraded = False
    pull_low = None
    end = min(n - 1, t0 + cap)
    for t in range(t0 + 1, end + 1):
        price = adj[t]
        trend_exit = (price < ma20[t] and ma20[t] < ma20[t - 1]) or price < low20[t]
        reached5 = reached5 or (b.units and price >= b.cost * 1.05)
        if b.units and price <= b.cost * 0.92:
            b.sell(b.units, price)
        elif reached5 and trend_exit and b.units:
            b.sell(b.units, price)
        elif style in ("COMBO", "COMBO_FULL") and not downgraded and b.units and price < ma20[t] and price < ma60[t]:
            downgraded = True
            b.sell(b.units if style == "COMBO_FULL" else b.units / 2, price)
        elif b.units and not reached5 and not downgraded:
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
        if b.units <= 1e-9:
            return b.cash_pnl / 10, t - t0
    return b.mark(adj[end]) / 10, end - t0


def main(price_folder, records_path, out_folder):
    out = Path(out_folder)
    out.mkdir(parents=True, exist_ok=True)
    recs = defaultdict(list)
    with gzip.open(records_path, "rt", newline="") as f:
        for r in csv.DictReader(f):
            if r["divergent"] != "yes":
                recs[r["code"]].append((dt.date.fromisoformat(r["date"]), r["CUR_ma"]))
    series, _ = load(price_folder)
    rows_out = []
    for (market, code), rows in series.items():
        if code not in recs or len(rows) < 200:
            continue
        dates = [r[0] for r in rows]
        index = {d: i for i, d in enumerate(dates)}
        adj = np.cumprod(1 + np.array([r[2] if r[2] is not None else 0.0 for r in rows], dtype=float))
        ma20, ma60 = base.moving_average(adj, 20), base.moving_average(adj, 60)
        low20 = np.full(len(adj), np.nan)
        for i in range(20, len(adj)):
            low20[i] = adj[i - 20:i].min()
        n = len(adj)
        for d, cur in recs[code]:
            te = index.get(d)
            if te is None or te < 61 or te + 120 >= n:
                continue
            row = {"date": d.isoformat(), "CUR": cur, "HOLD120": float(adj[te + 120] / adj[te] * (1 - base.SELL_COST) / (1 + base.BUY_COST) - 1), "HOLD120_days": 120}
            sig = next((t for t in range(max(te, 1), min(te + 20, n - 1) + 1) if adj[t] > ma20[t] and adj[t - 1] <= ma20[t - 1]), None)
            for style in ("P424H", "COMBO", "COMBO_FULL"):
                row[style], row[style + "_days"] = (0.0, 0) if sig is None else trade(sig, adj, ma20, ma60, low20, style, n)
            rows_out.append(row)
    report = {}
    for part, sel in (("2019-2021", [r for r in rows_out if r["date"] < SPLIT]), ("2022-", [r for r in rows_out if r["date"] >= SPLIT])):
        report[part] = {}
        for grp, grades in (("cheap", CHEAP), ("dear", DEAR), ("all", None)):
            g = [r for r in sel if grades is None or r["CUR"] in grades]
            report[part][grp] = {s: stats([{"date": r["date"], "ret": r[s], "days": r[s + "_days"]} for r in g]) for s in ("HOLD120", "P424H", "COMBO", "COMBO_FULL")}
    checks = {}
    for part in report:
        c = report[part]["cheap"]
        checks[part] = {
            "downgrade_reduce_helps": c["COMBO"]["p10"] >= c["P424H"]["p10"] + 0.005 and c["COMBO"]["mean"] >= c["P424H"]["mean"] - 0.003,
            "full_exit_better": c["COMBO_FULL"]["mean"] >= c["COMBO"]["mean"] and c["COMBO_FULL"]["p10"] >= c["COMBO"]["p10"],
            "rating_selects": c["COMBO"]["mean"] - report[part]["dear"]["COMBO"]["mean"] >= 0.01,
        }
    decision = {k: all(checks[p][k] for p in checks) for k in ("downgrade_reduce_helps", "full_exit_better", "rating_selects")}
    (out / "summary.json").write_text(json.dumps({"report": report, "checks": checks, "decision": decision, "evaluations": len(rows_out)}, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"evaluations": len(rows_out), "decision": decision, "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:4])
