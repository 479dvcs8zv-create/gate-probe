#!/usr/bin/env python3
"""第 40 輪補充（看過第 40 輪外資結果之後才加，**不是事先寫定的規則**，只當探索）：集保大戶變化 × 跌破季線，只看 60 日。

為什麼加：集保查詢頁只有約一年（2025-11～2026-11），第 40 輪要求之後要有 120 個交易日，可用的事件只到 2026-04；
這裡改成只要求之後 60 個交易日（事件可到約 2026-07），其他定義和第 40 輪相同。結果只列數字，不做任何判斷、不用來改網站。

用法：python3 -I tools/round40b_tdcc_60d.py <股價資料夾> <法人資料夾> <集保 history 資料夾> <輸出資料夾>
"""
import datetime as dt
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from round40_ma60_chips_backtest import BUY_COST, group_report, load_foreign, load_tdcc, moving_average  # noqa: E402
from stock_signal_backtest import load  # noqa: E402


def main(price_folder, chips_folder, tdcc_folder, out_folder):
    out = Path(out_folder)
    out.mkdir(parents=True, exist_ok=True)
    tdcc = load_tdcc(tdcc_folder)
    first_week = min(rows[0][0] for rows in tdcc.values())
    start = first_week + dt.timedelta(days=28)
    series, _ = load(price_folder)
    foreign = load_foreign(chips_folder)
    daily = defaultdict(list)
    prepared = {}
    for (market, code), rows in series.items():
        if len(rows) < 200:
            continue
        dates = [r[0] for r in rows]
        close = np.array([r[1] for r in rows], dtype=float)
        rets = np.array([r[2] if r[2] is not None else 0.0 for r in rows], dtype=float)
        value = np.array([r[3] for r in rows], dtype=float)
        adj = np.cumprod(1 + rets)
        ok = (close >= 10) & (moving_average(value, 20) >= 1e7)
        prepared[(market, code)] = (dates, close, adj, moving_average(adj, 60), ok, value)
        for i in range(1, len(rows)):
            if ok[i - 1] and dates[i] >= start and rows[i][2] is not None:
                daily[dates[i]].append(rows[i][2])
    mdates = sorted(daily)
    mlevel = dict(zip(mdates, np.cumprod([1 + statistics.fmean(daily[d]) for d in mdates])))
    events = []
    for (market, code), (dates, close, adj, ma60, ok, value) in prepared.items():
        hold_rows = tdcc.get(code)
        if not hold_rows:
            continue
        fx = foreign.get(code, {})
        above = 0
        for t in range(1, len(dates)):
            if np.isnan(ma60[t]) or np.isnan(ma60[t - 1]):
                above = 0
                continue
            if adj[t] < ma60[t] and adj[t - 1] >= ma60[t - 1] and above >= 20 and ok[t] and dates[t] >= start and t + 60 < len(dates):
                before = [x for x in hold_rows if x[0] <= dates[t]]
                if len(before) >= 5:
                    now, ago = before[-1], before[-5]
                    end = t + 60
                    m0, m1 = mlevel.get(dates[t]), mlevel.get(dates[end])
                    hold = float(adj[end] / adj[t] - 1)
                    r = next((i for i in range(t + 1, t + 6) if adj[i] >= ma60[i]), None)
                    win = range(t - 19, t + 1)
                    f20 = None
                    if all(dates[i] in fx for i in win):
                        vsum = sum(value[i] for i in win)
                        f20 = sum(fx[dates[i]] * close[i] for i in win) / vsum if vsum > 0 else None
                    events.append({"code": code, "date": dates[t].isoformat(), "month": dates[t].isoformat()[:7],
                                   "d_big": now[1] - ago[1], "d_holders": now[2] / ago[2] - 1 if ago[2] else None, "f20": f20,
                                   "reclaim5": r is not None, "hold60": hold, "hold_ex60": hold - (m1 / m0 - 1) if m0 and m1 else None,
                                   "r5h60": (1 - BUY_COST) * adj[end] / adj[r] - 1 if r is not None else 0.0})
            above = above + 1 if adj[t] >= ma60[t] else 0
    groups = {
        "all": events,
        "big_up": [e for e in events if e["d_big"] > 0], "big_down": [e for e in events if e["d_big"] <= 0],
        "big_up_1pt": [e for e in events if e["d_big"] >= 1.0], "big_down_1pt": [e for e in events if e["d_big"] <= -1.0],
        "holders_down": [e for e in events if e["d_holders"] is not None and e["d_holders"] < 0],
        "holders_up": [e for e in events if e["d_holders"] is not None and e["d_holders"] >= 0],
        "big_up_and_foreign_buy": [e for e in events if e["d_big"] > 0 and (e["f20"] or 0) > 0],
        "big_down_and_foreign_sell": [e for e in events if e["d_big"] <= 0 and e["f20"] is not None and e["f20"] < 0],
    }
    summary = {"note": "post-registration exploratory (added after round 40 foreign results); 60-day only; no decision",
               "events": len(events), "first": min((e["date"] for e in events), default=None), "last": max((e["date"] for e in events), default=None),
               "stocks": len({e["code"] for e in events}), "groups": {k: group_report(v) for k, v in groups.items() if v}}
    (out / "tdcc_60d_exploratory.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("events", "first", "last", "stocks")}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:5])
