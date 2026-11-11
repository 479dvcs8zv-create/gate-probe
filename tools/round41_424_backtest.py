#!/usr/bin/env python3
"""第 41 輪：今周刊「424 股市長贏必勝法」回測。擁有者 2026-11-11 16:06「你看看要回測嗎？」（附原文截圖）。
規則在看結果前寫定（2026-11-11 16:20）。

用法：python3 -I tools/round41_424_backtest.py <股價資料夾> <輸出資料夾>

一、原文規則（截圖摘要）與這裡的寫死方式（只有收盤價，沒有盤中高低；還原價算均線與報酬）
資金分 10 單位。
買：
1. 第一次投入 4 單位：原文例子都是「股價站上月線」→ 收盤由下往上穿過 20 日線那天收盤買 4。
2. 跌至中長期均線或整數關卡，加碼 2 單位攤平 → 進場後、還沒賣過之前，第一個收盤 ≤ 20 日線 × 1.01 或 ≤ 60 日線 × 1.01 的那天收盤買 2
   （整數關卡需要盤中價，不做）。
3. 股價不如預期暫不加；站上月線或季線、不再破底，加碼 4 單位 → 加碼 2 之後，第一次收盤再由下往上穿過 20 日線、
   而且這段期間收盤沒有跌破加碼 2 那天以前的最低收盤 → 那天收盤買 4。
   跌破那個最低收盤＝「不如預期」，之後不再加碼。
   原文「6 單位可以決定是否停損」沒有數字：主版本用「收盤比平均成本低 8% 全部出清」；另列不停損、收盤跌破 60 日線兩種。
賣：
1. 獲利 5～10% 先賣 4 單位 → 第一次收盤 ≥ 平均成本 × 1.05，賣 4（持有不到 4 就全賣）。賣過之後不再買。
2. 失守 5 日線賣 2 單位 → 賣出第 1 步之後，第一次收盤 < 5 日線，賣 2。
3. 失守下彎 20 日線或失守近一個月的起漲低點，賣剩下全部；20 日線上揚時跌破仍可續抱
   → 任何時候：收盤 < 20 日線且 20 日線比前一天低，或收盤 < 前 20 個交易日最低收盤 → 全部賣出。

二、比較
- 424：上面的規則。
- ALL_SAME：同一天一次買 10 單位，賣法和 424 一樣（看「分批買」的效果）。
- ALL_SIMPLE：同一天一次買 10 單位，只用賣法第 3 步一次全賣（看「分批賣」的效果）；停損同主版本。
- HOLD120：同一天買 10 單位，抱 120 個交易日（參考）。
成本：買 0.1425%；賣 0.1425%＋證交稅 0.3%。

三、樣本：2010-01 起上市＋上櫃；進場那天收盤 ≥ 10 元、20 日均額 ≥ 1,000 萬；同一檔一次只做一筆，賣光才找下一次訊號。
沒有原文「先做足功課」的選股，等於隨便挑股票照規則做；結果主要看規則本身。

四、每筆交易的指標（都以 10 單位為本金，沒用到的單位報酬 0）
- 報酬、最差 10%（P10）、賠錢比例、持有天數；資金效率＝報酬 ÷ 平均占用單位天數 × 100（每 100 單位天）。
- 先算每個月（進場月份）平均，再對月份平均；分兩段：2010-01～2017-12、2018-01～最後。

五、事先寫定的判斷（主版本＝停損 8%）
- 「分批買比較穩」：兩段都「424 的 P10 ≥ ALL_SAME 的 P10 ＋ 1 個百分點」。
- 「分批買不會少賺」：兩段都「424 的平均報酬 ≥ ALL_SAME 平均 − 0.5 個百分點」。
- 「分批賣比較好」：兩段都「ALL_SAME 平均報酬 ≥ ALL_SIMPLE 平均」且「ALL_SAME 的 P10 ≥ ALL_SIMPLE 的 P10」。
- 結果只寫進 gate-probe；網站規則要擁有者看過回測、同意後才改。
"""
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from stock_signal_backtest import load  # noqa: E402

import datetime as dt

START = dt.date(2010, 1, 1)
SPLIT = "2018-01-01"
BUY_COST, SELL_COST = 0.001425, 0.001425 + 0.003


def moving_average(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        c = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


class Book:
    def __init__(self):
        self.lots = []  # (units, price)
        self.cash_pnl = 0.0  # 以「單位」計的已實現損益（1 單位＝本金的 1/10）
        self.unit_days = 0.0

    @property
    def units(self):
        return sum(u for u, _ in self.lots)

    @property
    def cost(self):
        u = self.units
        return sum(u_ * p for u_, p in self.lots) / u if u else None

    def buy(self, units, price):
        self.lots.append((units, price * (1 + BUY_COST)))

    def sell(self, units, price):
        units = min(units, self.units)
        if units <= 0:
            return
        avg = self.cost
        self.cash_pnl += units * (price * (1 - SELL_COST) / avg - 1)
        remain = self.units - units
        self.lots = [(remain, avg)] if remain > 0 else []

    def mark(self, price):
        avg = self.cost
        return self.cash_pnl + (self.units * (price / avg - 1) if self.units else 0.0)


def run_trade(t0, adj, ma5, ma20, ma60, low20, style, stop, n):
    """回傳 (以 10 單位為本金的報酬, 持有天數, 平均占用單位, 是否到資料尾還沒賣完)。"""
    b = Book()
    if style == "424":
        b.buy(4, adj[t0])
    else:
        b.buy(10, adj[t0])
    added2 = added4 = sold1 = sold2 = False
    broke = False
    pull_low = None
    for t in range(t0 + 1, n):
        b.unit_days += b.units
        price = adj[t]
        if style == "HOLD120":
            if t - t0 >= 120:
                b.sell(10, price)
                return b.cash_pnl / 10, t - t0, b.unit_days / (t - t0) / 10, False
            continue
        # 停損（主版本 8%；60 日線版；不停損）
        if b.units and ((stop == "pct8" and price <= b.cost * 0.92) or (stop == "ma60" and price < ma60[t])):
            b.sell(b.units, price)
        # 賣法第 3 步（任何時候）
        elif b.units and ((price < ma20[t] and ma20[t] < ma20[t - 1]) or price < low20[t]):
            b.sell(b.units, price)
        else:
            if style in ("424", "ALL_SAME"):
                if not sold1 and b.units and price >= b.cost * 1.05:
                    b.sell(4, price)
                    sold1 = True
                elif sold1 and not sold2 and price < ma5[t]:
                    b.sell(2, price)
                    sold2 = True
            if style == "424" and not sold1 and b.units:
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


def summarize(trades, key):
    by = defaultdict(list)
    for tr in trades:
        by[tr["month"]].append(tr[key])
    means = [statistics.fmean(v) for v in by.values()]
    allv = [tr[key] for tr in trades]
    return {"mean": statistics.fmean(means), "se": statistics.stdev(means) / math.sqrt(len(means)) if len(means) > 1 else None,
            "median": statistics.median(allv), "p10": float(np.percentile(allv, 10)), "lose": sum(1 for x in allv if x < 0) / len(allv),
            "n": len(allv)}


def main(price_folder, out_folder):
    out = Path(out_folder)
    out.mkdir(parents=True, exist_ok=True)
    series, _ = load(price_folder)
    styles = [("424", "pct8"), ("ALL_SAME", "pct8"), ("ALL_SIMPLE", "pct8"), ("HOLD120", None), ("424", "none"), ("424", "ma60"), ("ALL_SAME", "none"), ("ALL_SIMPLE", "none")]
    trades = defaultdict(list)
    for (market, code), rows in series.items():
        if len(rows) < 200:
            continue
        dates = [r[0] for r in rows]
        close = np.array([r[1] for r in rows], dtype=float)
        rets = np.array([r[2] if r[2] is not None else 0.0 for r in rows], dtype=float)
        value = np.array([r[3] for r in rows], dtype=float)
        adj = np.cumprod(1 + rets)
        ma5, ma20, ma60 = moving_average(adj, 5), moving_average(adj, 20), moving_average(adj, 60)
        low20 = np.full(len(adj), np.nan)
        for i in range(20, len(adj)):
            low20[i] = adj[i - 20:i].min()
        ok = (close >= 10) & (moving_average(value, 20) >= 1e7)
        n = len(adj)
        for style, stop in styles:
            label = f"{style}|{stop}"
            t = 61
            while t < n - 1:
                if (dates[t] >= START and ok[t] and not np.isnan(ma60[t]) and adj[t] > ma20[t] and adj[t - 1] <= ma20[t - 1]):
                    ret, days, avg_units, open_end = run_trade(t, adj, ma5, ma20, ma60, low20, style, stop, n)
                    trades[label].append({"code": code, "date": dates[t].isoformat(), "month": dates[t].isoformat()[:7], "ret": ret,
                                          "days": days, "units": avg_units, "eff": ret / (avg_units * days) * 100 if avg_units and days else 0.0,
                                          "open": open_end})
                    t += max(days, 1)
                else:
                    t += 1
    report = {}
    for label, rows in trades.items():
        report[label] = {}
        for part, sel in (("2010-2017", [r for r in rows if r["date"] < SPLIT]), ("2018-", [r for r in rows if r["date"] >= SPLIT]), ("all", rows)):
            report[label][part] = {"ret": summarize(sel, "ret"), "eff": summarize(sel, "eff"),
                                   "days": statistics.fmean(r["days"] for r in sel), "units": statistics.fmean(r["units"] for r in sel)}
    checks = {}
    for part in ("2010-2017", "2018-"):
        a, s, m = report["424|pct8"][part]["ret"], report["ALL_SAME|pct8"][part]["ret"], report["ALL_SIMPLE|pct8"][part]["ret"]
        checks[part] = {"scale_in_safer": a["p10"] >= s["p10"] + 0.01, "scale_in_not_worse": a["mean"] >= s["mean"] - 0.005,
                        "scale_out_better": s["mean"] >= m["mean"] and s["p10"] >= m["p10"]}
    decision = {k: all(checks[p][k] for p in checks) for k in ("scale_in_safer", "scale_in_not_worse", "scale_out_better")}
    examples = {c: [r for r in trades["424|pct8"] if r["code"] == c and r["date"] >= "2025-09-01"] for c in ("6669", "2330", "8131")}
    summary = {"report": report, "checks": checks, "decision": decision, "examples2025": examples}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"decision": decision, "checks": checks, "trades": {k: len(v) for k, v in trades.items()}}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:3])
