#!/usr/bin/env python3
"""第 46 輪：季線轉彎（扣抵價）當出場訊號，會不會比「收盤跌破季線就賣」好。
擁有者 2026-11-27 19:07「好先做」（Gemini 整理的 YouTube 建議：看均線斜率與扣抵價，不只看排列）。規則在看結果前寫定（REGISTERED_AT）。

用法：python3 -I tools/round46_ma60_slope_exit_backtest.py <股價資料夾> <輸出資料夾>

一、樣本（資料與合格條件同第 39 輪）
- 上市＋上櫃，2010-01-01 起；60 日線用還原價（避免除權息跳空）。
- 起點 t0：收盤（還原）已連續 20 天以上（含當天）在 60 日線上，而且 60 日線今天比昨天高的第一天；
  同一段「在線上」期間只算一次，收盤跌破 60 日線後重新起算。
- t0 當天收盤 ≥ 10 元、前 20 日平均成交金額 ≥ 1,000 萬元；t0 之後要有 250 個交易日資料。

二、出場做法（都從 t0 收盤持有；訊號當天收盤賣出，賣了就不買回；最多看 250 個交易日，到期沒賣就算市值）
- A（現行）：收盤跌破 60 日線就賣。
- B：60 日線開始下彎（今天 < 昨天）就賣。60 日線今天會不會下彎，就是今天收盤是否低於 60 天前被扣掉那天的收盤（扣抵價），
  所以 B 也就是「收盤跌破扣抵價」。
- C：收盤跌破 60 日線「而且」60 日線下彎才賣（跌破但季線還在上彎就先不賣）。
- D（只列數字）：A 或 B 任一個先出現就賣。
- HOLD（參考）：不賣，抱 250 天。
- 成本：賣出 0.1425%＋證交稅 0.3%；買進成本各做法相同，不列入。

三、結果：t0 到 t0＋250 的報酬（賣出後現金報酬 0）。平均（先算 t0 所在月份的平均，再對月平均）、中位數、
  最差 10%（第 10 百分位）、平均持有天數，以及和 A 比較的出場天數差。

四、分兩段：2010–2017、2018–最後（依 t0）。

五、事先寫定的判斷：B、C 各自判斷。兩段都滿足「平均報酬 ≥ A ＋ 1.0 個百分點」且「最差 10% ≥ A 的最差 10% − 2.0 個百分點」
  → 支持用它取代 A。都不通過 → 維持現行（跌破季線就賣）。
  結果只寫進 gate-probe；網站規則要擁有者看過、同意後才改。
"""
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from round40_ma60_chips_backtest import moving_average  # noqa: E402
from stock_signal_backtest import load  # noqa: E402

REGISTERED_AT = "2026-11-27 19:09 台北"
START = "2010-01-01"
SPLIT = "2018-01-01"
WINDOW = 250
SELL_COST = 0.001425 + 0.003
VARIANTS = ("A", "B", "C", "D", "HOLD")


def exit_day(adj, ma, t0, rule):
    for i in range(t0 + 1, t0 + WINDOW + 1):
        below = adj[i] < ma[i]
        down = ma[i] < ma[i - 1]
        if (rule == "A" and below) or (rule == "B" and down) or (rule == "C" and below and down) or (rule == "D" and (below or down)):
            return i
    return None


def stats(events, key):
    by = defaultdict(list)
    for e in events:
        by[e["month"]].append(e[key])
    xs = [e[key] for e in events]
    return {"mean": statistics.fmean([statistics.fmean(v) for v in by.values()]), "median": statistics.median(xs),
            "p10": float(np.percentile(xs, 10)), "n": len(xs), "months": len(by)}


def main(price_folder, out_folder):
    out = Path(out_folder)
    out.mkdir(parents=True, exist_ok=True)
    series, _ = load(price_folder)
    events = []
    for (market, code), rows in series.items():
        if len(rows) < 200:
            continue
        dates = [r[0].isoformat() for r in rows]
        close = np.array([r[1] for r in rows], dtype=float)
        adj = np.cumprod(1 + np.array([r[2] if r[2] is not None else 0.0 for r in rows], dtype=float))
        ok = (close >= 10) & (moving_average(np.array([r[3] for r in rows], dtype=float), 20) >= 1e7)
        ma = moving_average(adj, 60)
        above, started = 0, False
        for t in range(1, len(rows) - WINDOW):
            if np.isnan(ma[t]) or np.isnan(ma[t - 1]):
                above, started = 0, False
                continue
            if adj[t] < ma[t]:
                above, started = 0, False
                continue
            above += 1
            if started or above < 20 or not ma[t] > ma[t - 1]:
                continue
            started = True
            if not ok[t] or dates[t] < START:
                continue
            e = {"market": market, "code": code, "date": dates[t], "month": dates[t][:7]}
            for v in VARIANTS:
                x = None if v == "HOLD" else exit_day(adj, ma, t, v)
                e[v] = float(adj[x] / adj[t] * (1 - SELL_COST) - 1) if x is not None else float(adj[t + WINDOW] / adj[t] - 1)
                e[f"{v}_days"] = (x - t) if x is not None else WINDOW
            events.append(e)

    parts = {"2010-2017": [e for e in events if e["date"] < SPLIT], "2018-": [e for e in events if e["date"] >= SPLIT], "all": events}
    summary = {"registeredAt": REGISTERED_AT, "events": len(events), "parts": {}}
    for name, rows in parts.items():
        p = {v: stats(rows, v) for v in VARIANTS}
        for v in VARIANTS:
            p[v]["days"] = statistics.fmean(e[f"{v}_days"] for e in rows)
        for v in ("B", "C", "D"):
            diff = [e[f"{v}_days"] - e["A_days"] for e in rows]
            p[v]["days_vs_A"] = {"mean": statistics.fmean(diff), "earlier_share": sum(d < 0 for d in diff) / len(diff),
                                 "later_share": sum(d > 0 for d in diff) / len(diff)}
        summary["parts"][name] = p
    checks = {}
    for v in ("B", "C"):
        checks[v] = {}
        for name in ("2010-2017", "2018-"):
            a, b = summary["parts"][name]["A"], summary["parts"][name][v]
            checks[v][name] = {"mean_diff": b["mean"] - a["mean"], "p10_diff": b["p10"] - a["p10"],
                               "pass": b["mean"] - a["mean"] >= 0.01 and b["p10"] - a["p10"] >= -0.02}
        checks[v]["supported"] = all(c["pass"] for c in checks[v].values())
    summary["checks"] = checks
    summary["data"] = {"first": min(e["date"] for e in events), "last": max(e["date"] for e in events)}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"events": len(events), "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:3])
