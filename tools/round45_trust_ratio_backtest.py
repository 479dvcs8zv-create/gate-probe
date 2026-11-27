#!/usr/bin/env python3
"""第 45 輪：投本比——投信近 20 日買超佔股本的比例突破門檻的上市股票，之後有沒有比大盤強。
擁有者 2026-11-27 18:38「直接從你這邊寫好上網回測」。出處：Gemini 整理的 YouTube 影片（永豐金 2026-11-27 盤前「投本比鎖定」）。
規則在看結果前寫定（2026-11-27 18:44 台北，commit 6017168）。

用法：python3 -I tools/round45_trust_ratio_backtest.py <股價資料夾> <法人資料夾> <股本資料夾> <輸出資料夾>

一、資料（只做上市；上櫃沒有同樣的官方股本表）
- 投信買賣超股數：證交所 T86（chips/twse_insti-*.csv.gz 的 trust 欄），2012-05 起。
- 發行股數：證交所 MI_QFIIS 每月第一個交易日（shares/twse-shares.csv.gz）；第 t 天只用 t 當天或之前最近一份（不偷看未來）。
- 股價：tools/stock_signal_backtest.load（收盤、還原日報酬、成交金額）。

二、訊號
- T20＝t 往前 20 個交易日（含 t）投信買賣超股數加總 ÷ 發行股數。20 天裡任何一天該股不在 T86 表上就不算（不補 0），另計筆數。
- 事件：T20 由 < 1.0% 變成 ≥ 1.0% 的那天（前一天的 T20 也要算得出來）；同一檔 20 個交易日內不重複算。
- 當天要合格：收盤 ≥ 10 元、前 20 日平均成交金額 ≥ 1,000 萬元（同第 38～43 輪）。
- 另列（只列數字）：門檻 0.5%、2.0%；T20 由 > −1.0% 變成 ≤ −1.0%（投信大賣）。

三、結果
- T86 收盤後才公布 → 從 t＋1 收盤買進，算之後 20、60 個交易日的還原報酬；超額＝減去同期「全部合格上市股票等權平均」報酬。
- 先算每個月（事件月份）的平均，再對月平均；標準誤＝月平均的標準差 ÷ √月數 × √(期間 ÷ 20)。
- 分兩段：2012-06～2018-12、2019-01～最後。另列：市值（收盤 × 發行股數）< 100 億與 ≥ 100 億；2025 年起（主動式 ETF 由投信操作，買賣也算在投信）。

四、事先寫定的判斷（門檻 1.0%）
- 兩段都滿足「60 日平均超額 ≥ +1.0 個百分點」且「20 日平均超額 > 0」→ 支持「投本比突破 1% 的股票之後較強」。否則不支持。
- 結果只寫進 gate-probe；網站要擁有者看過、同意後才加。
"""
import bisect
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
from round40_ma60_chips_backtest import moving_average  # noqa: E402
from stock_signal_backtest import load  # noqa: E402

START = dt.date(2012, 5, 1)
SPLIT = "2019-01-01"
HORIZONS = (20, 60)
SIGNALS = {"buy1.0": (0.01, 1), "buy0.5": (0.005, 1), "buy2.0": (0.02, 1), "sell1.0": (-0.01, -1)}


def load_trust(folder):
    out = defaultdict(dict)
    for p in sorted(Path(folder).glob("twse_insti-[0-9][0-9][0-9][0-9].csv.gz")):
        with gzip.open(p, "rt", newline="") as f:
            for r in csv.DictReader(f):
                try:
                    out[r["code"]][dt.date.fromisoformat(r["date"])] = float(r["trust"])
                except (ValueError, KeyError):
                    continue
    return out


def load_shares(folder):
    out = defaultdict(list)
    with gzip.open(Path(folder) / "twse-shares.csv.gz", "rt", newline="") as f:
        for r in csv.DictReader(f):
            out[r["code"]].append((dt.date.fromisoformat(r["date"]), int(r["shares"])))
    return {k: sorted(v) for k, v in out.items()}


def month_stats(values, h):
    by = defaultdict(list)
    for month, x in values:
        by[month].append(x)
    means = [statistics.fmean(a) for a in by.values()]
    if not means:
        return None
    se = statistics.stdev(means) / math.sqrt(len(means)) * math.sqrt(h / 20) if len(means) > 1 else None
    return {"mean": statistics.fmean(means), "se": se, "events": len(values), "months": len(means)}


def group(events):
    rep = {"n": len(events)}
    for h in HORIZONS:
        rep[f"ex{h}"] = month_stats([(e["month"], e[f"ex{h}"]) for e in events if e.get(f"ex{h}") is not None], h)
        rep[f"ret{h}"] = month_stats([(e["month"], e[f"ret{h}"]) for e in events if e.get(f"ret{h}") is not None], h)
    return rep


def main(price_folder, chips_folder, shares_folder, out_folder):
    out = Path(out_folder)
    out.mkdir(parents=True, exist_ok=True)
    series, _ = load(price_folder)
    trust, shares = load_trust(chips_folder), load_shares(shares_folder)
    daily, prepared = defaultdict(list), {}
    for (market, code), rows in series.items():
        if market != "twse" or len(rows) < 200:
            continue
        dates = [r[0] for r in rows]
        close = np.array([r[1] for r in rows], dtype=float)
        rets = np.array([r[2] if r[2] is not None else 0.0 for r in rows], dtype=float)
        value = np.array([r[3] for r in rows], dtype=float)
        ok = (close >= 10) & (moving_average(value, 20) >= 1e7)
        prepared[code] = (dates, close, np.cumprod(1 + rets), ok)
        for i in range(1, len(rows)):
            if ok[i - 1] and dates[i] >= START and rows[i][2] is not None:
                daily[dates[i]].append(rows[i][2])
    mdates = sorted(daily)
    mlevel = dict(zip(mdates, np.cumprod([1 + statistics.fmean(daily[d]) for d in mdates])))

    events = {k: [] for k in SIGNALS}
    counts = {"windows": 0, "missing_trust_day": 0, "missing_shares": 0}
    for code, (dates, close, adj, ok) in prepared.items():
        tx, sx = trust.get(code, {}), shares.get(code)
        if not tx or not sx:
            continue
        sdates = [d for d, _ in sx]
        last = {k: -10 ** 9 for k in SIGNALS}
        prev = None
        for t in range(19, len(dates) - 1):
            if dates[t] < START:
                continue
            counts["windows"] += 1
            k = bisect.bisect_right(sdates, dates[t]) - 1
            win = dates[t - 19:t + 1]
            if k < 0:
                counts["missing_shares"] += 1
                prev = None
                continue
            if not all(d in tx for d in win):
                counts["missing_trust_day"] += 1
                prev = None
                continue
            cur = sum(tx[d] for d in win) / sx[k][1]
            if prev is not None and ok[t]:
                for name, (thr, side) in SIGNALS.items():
                    crossed = prev < thr <= cur if side > 0 else prev > thr >= cur
                    if crossed and t - last[name] >= 20:
                        last[name] = t
                        e = {"code": code, "date": dates[t].isoformat(), "month": dates[t].isoformat()[:7], "t20": cur,
                             "mcap": float(close[t]) * sx[k][1]}
                        entry = t + 1
                        for h in HORIZONS:
                            end = entry + h
                            if end >= len(dates):
                                continue
                            ret = float(adj[end] / adj[entry] - 1)
                            m0, m1 = mlevel.get(dates[entry]), mlevel.get(dates[end])
                            e[f"ret{h}"] = ret
                            e[f"ex{h}"] = ret - (m1 / m0 - 1) if m0 and m1 else None
                        events[name].append(e)
            prev = cur

    def parts(rows):
        return {"2012-2018": [e for e in rows if e["date"] < SPLIT], "2019-": [e for e in rows if e["date"] >= SPLIT], "all": rows}

    summary = {"counts": counts, "signals": {}}
    for name, rows in events.items():
        sig = {p: group(r) for p, r in parts(rows).items()}
        sig["small_lt_100e8"] = group([e for e in rows if e["mcap"] < 1e10])
        sig["large_ge_100e8"] = group([e for e in rows if e["mcap"] >= 1e10])
        sig["since2025"] = group([e for e in rows if e["date"] >= "2025-01-01"])
        summary["signals"][name] = sig
    checks = {}
    for p in ("2012-2018", "2019-"):
        g = summary["signals"]["buy1.0"][p]
        ex60, ex20 = (g["ex60"] or {}).get("mean"), (g["ex20"] or {}).get("mean")
        checks[p] = {"ex60": ex60, "ex20": ex20, "pass": ex60 is not None and ex20 is not None and ex60 >= 0.01 and ex20 > 0}
    summary["checks"] = checks
    summary["decision"] = "supported" if all(c["pass"] for c in checks.values()) else "not_supported"
    all_events = [e for rows in events.values() for e in rows]
    summary["data"] = {"first": min((e["date"] for e in all_events), default=None), "last": max((e["date"] for e in all_events), default=None)}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    with gzip.open(out / "events.csv.gz", "wt", newline="") as f:
        w = csv.writer(f)
        cols = ["signal", "code", "date", "t20", "mcap", "ret20", "ex20", "ret60", "ex60"]
        w.writerow(cols)
        for name, rows in events.items():
            for e in rows:
                w.writerow([name] + [round(e[c], 6) if isinstance(e.get(c), float) else e.get(c) for c in cols[1:]])
    print(json.dumps({"events": {k: len(v) for k, v in events.items()}, "counts": counts, "decision": summary["decision"], "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:5])
