#!/usr/bin/env python3
"""第 39 輪：跌破季線出場後，「站回季線就買回」有沒有比「賣了就不買回」好。
擁有者 2026-11-10 22:16「可以啊」（長榮航 8/14 跌破季線出場、8/17 站回沒買回，之後漲到 46.15）。規則在看結果前寫定（2026-11-10 22:30）。

用法：python3 -I tools/round39_ma60_reentry_backtest.py <股價資料夾> <輸出資料夾>

一、資料
- 股價：tools/stock_signal_backtest.load（上市＋上櫃收盤、還原日報酬、成交金額）。均線用還原報酬累積的價格算，避免除權息跳空。
- 期間：2010-01-01 起到資料最後一天。

二、出場事件（擁有者現行做法）
- 第 t 天收盤（還原）跌破 60 日均線，前一天還在均線上，而且之前已連續 20 天以上收在均線上（＝原本抱著、趨勢中跌破）。
- 當天收盤 ≥ 10 元、前 20 日平均成交金額 ≥ 1,000 萬元（同第 38 輪）；之後要有 120 個交易日資料。

三、比較的做法（報酬都從第 t 天收盤算起，算到 t＋60、t＋120）
- OUT：賣了就不買回（現金，報酬 0）。
- HOLD：當初沒賣、一路抱著（參考，回答「創新高可能繼續漲」）。
- R5／R10／R20：t 之後 N 個交易日內，第一個收盤站回 60 日線的那天收盤買回；之後再收盤跌破 60 日線就賣，賣了就不再買。
  N 天內沒站回就不買（報酬 0）。
- R5H：5 天內站回就買回，之後一路抱到期末（不再用季線出場）。
- 成本：買 0.1425%；賣 0.1425%＋證交稅 0.3%。期末還抱著的只算市值、不扣賣出成本。
- 市場比較：同一段期間「全部合格股票等權平均」的報酬；超額＝做法報酬 − 市場報酬（OUT 的超額＝−市場報酬）。

四、誤差與分段
- 先算每個月（出場事件的月份）的平均，再對月份平均；標準誤＝月份平均的標準差 ÷ √月數 × √(期間 ÷ 20)，粗估重疊。
- 分兩段：2010-01～2017-12、2018-01～最後。

五、事先寫定的判斷（120 日為主）
- 某個 N（5、10、20）兩段都滿足：平均報酬 > 0、中位數 > 0、平均超額 > OUT 的平均超額（即 RN 比不買回好，扣掉市場漲跌後也成立）
  → 支持加一條「跌破季線出場後 N 天內站回就買回」，取通過的最小 N。都不通過 → 不支持，維持現行。
- 另列：5 天內就站回（假跌破）的比例、長榮航（2618）2026 年的事件。
- 結果只寫進 gate-probe；網站規則要擁有者看過回測、同意後才改。
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

START = dt.date(2010, 1, 1)
SPLIT = dt.date(2018, 1, 1)
BUY_COST, SELL_COST = 0.001425, 0.001425 + 0.003
HORIZONS = (60, 120)
VARIANTS = ("OUT", "HOLD", "R5", "R10", "R20", "R5H")


def moving_average(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        c = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def reentry_path(adj, ma, t, end, window, follow_exit):
    """回傳從 t 收盤到 end 收盤的報酬（含成本）；window 天內沒站回＝0。"""
    r = next((i for i in range(t + 1, min(t + window, end) + 1) if adj[i] >= ma[i]), None)
    if r is None:
        return 0.0, None
    value = (1 - BUY_COST)
    entry = adj[r]
    for i in range(r + 1, end + 1):
        if follow_exit and adj[i] < ma[i]:
            return value * adj[i] / entry * (1 - SELL_COST) - 1, r
    return value * adj[end] / entry - 1, r


def main(price_folder, out_folder):
    out = Path(out_folder)
    out.mkdir(parents=True, exist_ok=True)
    series, stats = load(price_folder)
    # 等權市場：每天所有合格股票（收盤 ≥ 10、20 日均額 ≥ 1,000 萬）的平均還原報酬
    daily = defaultdict(list)
    prepared = {}
    for key, rows in series.items():
        if len(rows) < 200:
            continue
        dates = [r[0] for r in rows]
        close = np.array([r[1] for r in rows], dtype=float)
        rets = np.array([r[2] if r[2] is not None else 0.0 for r in rows], dtype=float)
        value = np.array([r[3] for r in rows], dtype=float)
        adj = np.cumprod(1 + rets)
        ma60 = moving_average(adj, 60)
        val20 = moving_average(value, 20)
        ok = (close >= 10) & (val20 >= 1e7)
        prepared[key] = (dates, close, adj, ma60, ok)
        for i in range(1, len(rows)):
            if ok[i - 1] and dates[i] >= START and rows[i][2] is not None:
                daily[dates[i]].append(rows[i][2])
    mdates = sorted(daily)
    mlevel = dict(zip(mdates, np.cumprod([1 + statistics.fmean(daily[d]) for d in mdates])))

    events = []
    for (market, code), (dates, close, adj, ma60, ok) in prepared.items():
        n = len(dates)
        above = 0
        for t in range(1, n):
            if np.isnan(ma60[t]) or np.isnan(ma60[t - 1]):
                above = 0
                continue
            if adj[t] < ma60[t] and adj[t - 1] >= ma60[t - 1] and above >= 20 and ok[t] and dates[t] >= START and t + max(HORIZONS) < n:
                ev = {"market": market, "code": code, "date": dates[t].isoformat(), "close": float(close[t])}
                ev["reclaim5"] = any(adj[i] >= ma60[i] for i in range(t + 1, t + 6))
                for h in HORIZONS:
                    end = t + h
                    m0, m1 = mlevel.get(dates[t]), mlevel.get(dates[end])
                    mret = m1 / m0 - 1 if m0 and m1 else None
                    res = {"OUT": 0.0, "HOLD": float(adj[end] / adj[t] - 1)}
                    for name, window, follow in (("R5", 5, True), ("R10", 10, True), ("R20", 20, True), ("R5H", 5, False)):
                        res[name], _ = reentry_path(adj, ma60, t, end, window, follow)
                    ev[f"h{h}"] = res
                    ev[f"m{h}"] = mret
                events.append(ev)
            above = above + 1 if adj[t] >= ma60[t] else 0

    def summarize(rows, h):
        result = {}
        for v in VARIANTS:
            by_month = defaultdict(list)
            exc_month = defaultdict(list)
            allv = []
            for e in rows:
                x = e[f"h{h}"][v]
                allv.append(x)
                by_month[e["date"][:7]].append(x)
                if e[f"m{h}"] is not None:
                    exc_month[e["date"][:7]].append(x - e[f"m{h}"])
            means = [statistics.fmean(a) for a in by_month.values()]
            emeans = [statistics.fmean(a) for a in exc_month.values()]
            se = (statistics.stdev(means) / math.sqrt(len(means)) * math.sqrt(h / 20)) if len(means) > 1 else None
            result[v] = {"mean": statistics.fmean(means), "se": se, "median": statistics.median(allv),
                         "positive": sum(1 for x in allv if x > 0) / len(allv), "p10": float(np.percentile(allv, 10)),
                         "excess": statistics.fmean(emeans) if emeans else None, "events": len(allv), "months": len(means)}
        return result

    parts = {"2010-2017": [e for e in events if e["date"] < SPLIT.isoformat()], "2018-": [e for e in events if e["date"] >= SPLIT.isoformat()]}
    summary = {"events": len(events), "falseBreak5": sum(e["reclaim5"] for e in events) / len(events) if events else None,
               "parts": {name: {f"h{h}": summarize(rows, h) for h in HORIZONS} for name, rows in parts.items()},
               "all": {f"h{h}": summarize(events, h) for h in HORIZONS}}
    decision = None
    for name in ("R5", "R10", "R20"):
        ok = all(summary["parts"][p]["h120"][name]["mean"] > 0 and summary["parts"][p]["h120"][name]["median"] > 0
                 and summary["parts"][p]["h120"][name]["excess"] > summary["parts"][p]["h120"]["OUT"]["excess"] for p in parts)
        summary.setdefault("checks", {})[name] = ok
        if ok and decision is None:
            decision = name
    summary["decision"] = decision or "not_supported"
    summary["eva2026"] = [e for e in events if e["code"] == "2618" and e["date"] >= "2026-01-01"]
    summary["data"] = {"first": min(e["date"] for e in events) if events else None, "last": max(e["date"] for e in events) if events else None, "loaderStats": dict(stats)}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out / "events.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["market", "code", "date", "close", "reclaim5"] + [f"h{h}_{v}" for h in HORIZONS for v in VARIANTS] + [f"m{h}" for h in HORIZONS])
        for e in events:
            w.writerow([e["market"], e["code"], e["date"], e["close"], int(e["reclaim5"])] + [round(e[f"h{h}"][v], 5) for h in HORIZONS for v in VARIANTS] + [None if e[f"m{h}"] is None else round(e[f"m{h}"], 5) for h in HORIZONS])
    print(json.dumps({"events": summary["events"], "falseBreak5": summary["falseBreak5"], "decision": summary["decision"], "checks": summary["checks"]}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:3])
