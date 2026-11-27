#!/usr/bin/env python3
"""第 50、51 輪：進場三條件的交易模擬（同第 34 輪的做法，但進場改用網站現行三條件，含均線排列強）。
擁有者 2026-11-28 00:15「做完吧」（Gemini 2026-11-27 文件第三節第 1、5 題）。規則在看結果前寫定（REGISTERED_AT）。

用法：python3 -I tools/round50_51_entry_exit_backtest.py <股價資料夾> <營收 revenue.csv.gz> <輸出資料夾>

共同設定
- 每 5 個交易日檢查；合格（121 筆以上歷史、收盤 ≥ 10、前 20 日均額 ≥ 1,000 萬）且符合進場三條件（同第 48 輪）→ 當天收盤買進。
- 同一檔持有中不重複進場。每筆扣一買一賣 0.585%（同第 34 輪）。還原價。分 2006–2015、2016–最後（依進場日）。
- 指標：每筆平均、中位數、最差 5%、虧損超過 10% 的比例、平均持有天數、每天平均、進場後 20 天內最低價跌 ≥ 20% 的比例。

第 50 輪：進場時離 20 日線太遠就不買（乖離上限）
- 乖離＝收盤 ÷ 20 日線 − 1。主判斷用上限 10%；8%、12% 只列數字。出場一律「收盤跌破 20 日線」，最長 60 個交易日。
- 比較：只買乖離 ≤ 10% 的 vs 全部（現行）。另列被排除的（乖離 > 10%）。
- 事先寫定的判斷：兩段都滿足「虧損 > 10% 的比例 ≤ 現行的 75%」且「每筆平均 ≥ 現行 − 0.1 個百分點」→ 支持加乖離上限。否則不支持。

第 51 輪：賺 15% 以上改用 10 日線出場（移動停利）
- 基準：收盤跌破 20 日線出場。
- 變化：進場後最高收盤達進場價 1.15 倍以後，收盤跌破 10 日線或 20 日線（先到者）就出場；之前照基準。
- 主判斷最長 60 個交易日；另列最長 120 個交易日（只列數字）。
- 事先寫定的判斷：兩段都滿足「每筆平均 ≥ 基準 ＋ 0.1 個百分點」且「每天平均 ≥ 基準」→ 支持。否則不支持。
- 結果只寫進 gate-probe；網站規則要擁有者看過、同意後才改。
"""
import datetime as dt
import json
import math
import sys
from bisect import bisect_right
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from round33_backtest import revenue_index  # noqa: E402
from stock_signal_backtest import load, signals  # noqa: E402

REGISTERED_AT = "2026-11-28 00:18 台北"
D = dt.date
COST = 0.00585
SPLIT = D(2016, 1, 1)


def simulate(adj, ma, entries, n, keep, rule, max_hold):
    trades, free_from = [], -1
    for i, bias in entries:
        if i <= free_from or not keep(bias):
            continue
        exit_i, peak, trailing = None, adj[i], False
        for k in range(i + 1, min(i + max_hold, n - 1) + 1):
            c = adj[k]
            peak = max(peak, c)
            if rule == "trail" and peak >= adj[i] * 1.15:
                trailing = True
            if c < ma(20, k) or (trailing and c < ma(10, k)):
                exit_i = k
                break
        if exit_i is None:
            exit_i = min(i + max_hold, n - 1)
        low20 = adj[i + 1:min(i + 21, n)].min() / adj[i] - 1
        trades.append((i, adj[exit_i] / adj[i] - 1 - COST, exit_i - i, low20))
        free_from = exit_i
    return trades


def report(rows):
    if not rows:
        return None
    rets = np.array([t[1] for t in rows])
    days = np.array([t[2] for t in rows])
    return {"n": len(rows), "mean": float(rets.mean()), "median": float(np.median(rets)), "p5": float(np.percentile(rets, 5)),
            "loss10": float((rets < -0.10).mean()), "days": float(days.mean()), "per_day": float(rets.mean() / days.mean()),
            "crash20": float(np.mean([t[3] <= -0.20 for t in rows]))}


def main(price_folder, revenue_path, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    series, _ = load(price_folder)
    rev = revenue_index(revenue_path)
    cal = sorted({d for rows in series.values() for d, *_ in rows})
    eval_days = set(cal[::5])
    setups = {
        "r50_all": (lambda b: True, "base", 60), "r50_cap10": (lambda b: b <= 0.10, "base", 60), "r50_excluded10": (lambda b: b > 0.10, "base", 60),
        "r50_cap8": (lambda b: b <= 0.08, "base", 60), "r50_cap12": (lambda b: b <= 0.12, "base", 60),
        "r51_base60": (lambda b: True, "base", 60), "r51_trail60": (lambda b: True, "trail", 60),
        "r51_base120": (lambda b: True, "base", 120), "r51_trail120": (lambda b: True, "trail", 120),
    }
    trades = {k: [] for k in setups}
    for (market, code), rows in series.items():
        if len(rows) < 130:
            continue
        dates, close, adj, score, tech, rsi, val20 = signals(rows)
        n = len(rows)
        cs = np.concatenate([[0.0], np.cumsum(adj)])
        ma = lambda k, i, cs=cs: (cs[i + 1] - cs[i + 1 - k]) / k  # noqa: E731
        rv = rev.get((market, code), [])
        rvd = [x[0] for x in rv]
        entries = []
        for i in range(120, n - 1):
            d = dates[i]
            if d not in eval_days or d > cal[-1] - dt.timedelta(days=95):
                continue
            if close[i] < 10 or val20[i] < 1e7 or math.isnan(score[i]) or math.isnan(tech[i]):
                continue
            m5, m10, m20, m120 = ma(5, i), ma(10, i), ma(20, i), ma(120, i)
            j = bisect_right(rvd, d) - 1
            if (tech[i] == 0 and score[i] >= 3 and j >= 0 and (d - rv[j][0]).days <= 75 and rv[j][1] > 10
                    and m5 > m20 and m10 > m20 and m5 > m120 and m10 > m120):
                entries.append((i, adj[i] / m20 - 1))
        for name, (keep, rule, hold) in setups.items():
            trades[name].extend((dates[t[0]],) + t[1:] for t in simulate(adj, ma, entries, n, keep, rule, hold))

    summary = {"registeredAt": REGISTERED_AT, "parts": {}}
    for pname, pf in (("2006-2015", lambda d: d < SPLIT), ("2016-", lambda d: d >= SPLIT), ("all", lambda d: True)):
        summary["parts"][pname] = {k: report([t for t in v if pf(t[0])]) for k, v in trades.items()}
    checks = {"r50": {}, "r51": {}}
    for pname in ("2006-2015", "2016-"):
        p = summary["parts"][pname]
        a, c = p["r50_all"], p["r50_cap10"]
        checks["r50"][pname] = {"loss10_ratio": c["loss10"] / a["loss10"] if a["loss10"] else None, "mean_diff": c["mean"] - a["mean"],
                                "pass": a["loss10"] > 0 and c["loss10"] <= 0.75 * a["loss10"] and c["mean"] >= a["mean"] - 0.001}
        b, t = p["r51_base60"], p["r51_trail60"]
        checks["r51"][pname] = {"mean_diff": t["mean"] - b["mean"], "per_day_diff": t["per_day"] - b["per_day"],
                                "pass": t["mean"] >= b["mean"] + 0.001 and t["per_day"] >= b["per_day"]}
    summary["checks"] = checks
    summary["decision"] = {k: "supported" if all(x["pass"] for x in v.values()) else "not_supported" for k, v in checks.items()}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"decision": summary["decision"], "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:4])
