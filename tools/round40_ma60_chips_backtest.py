#!/usr/bin/env python3
"""第 40 輪：跌破季線時，外資買賣超與集保大戶變化，能不能分辨「假跌破」。
擁有者 2026-11-10 22:27／22:54：籌碼越集中＝股票在大戶手中、散戶越少，拉抬越輕鬆；外資買賣超也很重要。規則在看結果前寫定（2026-11-10 23:10）。

用法：python3 -I tools/round40_ma60_chips_backtest.py <股價資料夾> <法人資料夾> <集保 history 資料夾> <輸出資料夾>

一、出場事件：同第 39 輪（收盤還原價跌破 60 日線、前一天在線上、之前連續 20 天以上在線上；收盤 ≥ 10 元、20 日均額 ≥ 1,000 萬；之後要有 120 個交易日）。
二、外資（長期，2012 起上市、2014 起上櫃）：F20＝跌破當天往前 20 個交易日（含當天）外資買賣超股數 × 收盤價的加總 ÷ 同期成交金額加總。
   - 買超組 F20 > 0、賣超組 F20 < 0；另列強度組 F20 ≥ +3%、≤ −3%。缺法人資料的事件不列入。
三、集保（短期探索，只有約一年）：跌破當天以前最近一週的千張大戶比例，減 4 週前；增加＝集中組，減少＝分散組；股東人數同理（減少＝集中）。
   只有一段期間，達不到「兩段都成立」的要求 → 只列數字、不做判斷。
四、結果：HOLD（沒賣一路抱）60／120 日報酬與超額（減等權市場）；5 天內站回比例（假跌破率）；R5H（5 天內站回就買回、之後抱著）。
   超額、誤差的算法同第 39 輪（先月平均、再對月平均；標準誤 × √(期間 ÷ 20)）。
五、事先寫定的判斷（外資）：兩段（2012–2018、2019–最後）都滿足
   「買超組的 HOLD 60 日超額 − 賣超組 ≥ +1.0 個百分點」且「買超組 5 天內站回比例 − 賣超組 ≥ +3 個百分點」
   → 支持「跌破季線時外資還在買，就先當作可能是假跌破」。否則不支持。
六、結果只寫進 gate-probe；網站規則要擁有者看過回測、同意後才改。
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
from stock_signal_backtest import load  # noqa: E402

START = dt.date(2012, 1, 1)
SPLIT = dt.date(2019, 1, 1)
BUY_COST = 0.001425


def moving_average(x, n):
    out = np.full(len(x), np.nan)
    if len(x) >= n:
        c = np.cumsum(np.insert(x, 0, 0.0))
        out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def load_foreign(folder):
    """{code: {date: 外資買賣超股數}}（上市＋上櫃）。"""
    out = defaultdict(dict)
    for p in sorted(Path(folder).glob("*_insti-[0-9][0-9][0-9][0-9].csv.gz")):
        with gzip.open(p, "rt", newline="") as f:
            for r in csv.DictReader(f):
                try:
                    out[r["code"]][dt.date.fromisoformat(r["date"])] = float(r["foreign"])
                except (ValueError, KeyError):
                    continue
    return out


def load_tdcc(folder):
    out = {}
    for p in Path(folder).glob("*.csv"):
        rows = []
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                try:
                    rows.append((dt.date(int(r["date"][:4]), int(r["date"][4:6]), int(r["date"][6:])), float(r["ge1000_pct"]), int(r["holders"])))
                except (ValueError, KeyError):
                    continue
        if rows:
            out[p.stem] = sorted(rows)
    return out


def month_stats(values, h):
    by = defaultdict(list)
    for month, x in values:
        by[month].append(x)
    means = [statistics.fmean(a) for a in by.values()]
    if not means:
        return None
    se = statistics.stdev(means) / math.sqrt(len(means)) * math.sqrt(h / 20) if len(means) > 1 else None
    return {"mean": statistics.fmean(means), "se": se, "events": len(values), "months": len(means)}


def group_report(events, h=60):
    rep = {}
    for key in ("hold", "hold_ex", "r5h"):
        rep[key] = month_stats([(e["month"], e[f"{key}{h}"]) for e in events if e.get(f"{key}{h}") is not None], h)
    rep["reclaim5"] = sum(e["reclaim5"] for e in events) / len(events) if events else None
    rep["n"] = len(events)
    return rep


def main(price_folder, chips_folder, tdcc_folder, out_folder):
    out = Path(out_folder)
    out.mkdir(parents=True, exist_ok=True)
    series, _ = load(price_folder)
    foreign = load_foreign(chips_folder)
    tdcc = load_tdcc(tdcc_folder) if Path(tdcc_folder).exists() else {}
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
        ok = (close >= 10) & (moving_average(value, 20) >= 1e7)
        prepared[key] = (dates, close, adj, moving_average(adj, 60), ok, value)
        for i in range(1, len(rows)):
            if ok[i - 1] and dates[i] >= START and rows[i][2] is not None:
                daily[dates[i]].append(rows[i][2])
    mdates = sorted(daily)
    mlevel = dict(zip(mdates, np.cumprod([1 + statistics.fmean(daily[d]) for d in mdates])))

    events = []
    for (market, code), (dates, close, adj, ma60, ok, value) in prepared.items():
        fx = foreign.get(code, {})
        hold_rows = tdcc.get(code)
        above = 0
        for t in range(1, len(dates)):
            if np.isnan(ma60[t]) or np.isnan(ma60[t - 1]):
                above = 0
                continue
            if adj[t] < ma60[t] and adj[t - 1] >= ma60[t - 1] and above >= 20 and ok[t] and dates[t] >= START and t + 120 < len(dates):
                e = {"market": market, "code": code, "date": dates[t].isoformat(), "month": dates[t].isoformat()[:7]}
                win = range(t - 19, t + 1)
                if all(dates[i] in fx for i in win):
                    vsum = sum(value[i] for i in win)
                    e["f20"] = sum(fx[dates[i]] * close[i] for i in win) / vsum if vsum > 0 else None
                else:
                    e["f20"] = None
                e["reclaim5"] = any(adj[i] >= ma60[i] for i in range(t + 1, t + 6))
                for h in (60, 120):
                    end = t + h
                    hold = float(adj[end] / adj[t] - 1)
                    m0, m1 = mlevel.get(dates[t]), mlevel.get(dates[end])
                    e[f"hold{h}"] = hold
                    e[f"hold_ex{h}"] = hold - (m1 / m0 - 1) if m0 and m1 else None
                    r = next((i for i in range(t + 1, t + 6) if adj[i] >= ma60[i]), None)
                    e[f"r5h{h}"] = (1 - BUY_COST) * adj[end] / adj[r] - 1 if r is not None else 0.0
                if hold_rows:
                    before = [x for x in hold_rows if x[0] <= dates[t]]
                    if len(before) >= 5:
                        now, ago = before[-1], before[-5]
                        e["d_big"] = now[1] - ago[1]
                        e["d_holders"] = now[2] / ago[2] - 1 if ago[2] else None
                events.append(e)
            above = above + 1 if adj[t] >= ma60[t] else 0

    def split(rows):
        return {"2012-2018": [e for e in rows if e["date"] < SPLIT.isoformat()], "2019-": [e for e in rows if e["date"] >= SPLIT.isoformat()]}

    with_f = [e for e in events if e.get("f20") is not None]
    foreign_result = {}
    for part, rows in split(with_f).items():
        foreign_result[part] = {
            "buy": group_report([e for e in rows if e["f20"] > 0]), "sell": group_report([e for e in rows if e["f20"] < 0]),
            "buy3": group_report([e for e in rows if e["f20"] >= 0.03]), "sell3": group_report([e for e in rows if e["f20"] <= -0.03]),
        }
    checks = {}
    for part, g in foreign_result.items():
        diff = g["buy"]["hold_ex"]["mean"] - g["sell"]["hold_ex"]["mean"]
        rdiff = g["buy"]["reclaim5"] - g["sell"]["reclaim5"]
        checks[part] = {"hold_ex60_diff": diff, "reclaim5_diff": rdiff, "pass": diff >= 0.01 and rdiff >= 0.03}
    decision = "supported" if all(c["pass"] for c in checks.values()) else "not_supported"

    with_t = [e for e in events if e.get("d_big") is not None]
    tdcc_result = {"events": len(with_t), "first": min((e["date"] for e in with_t), default=None), "last": max((e["date"] for e in with_t), default=None)}
    if with_t:
        tdcc_result.update({
            "big_up": group_report([e for e in with_t if e["d_big"] > 0]), "big_down": group_report([e for e in with_t if e["d_big"] <= 0]),
            "holders_down": group_report([e for e in with_t if e["d_holders"] is not None and e["d_holders"] < 0]),
            "holders_up": group_report([e for e in with_t if e["d_holders"] is not None and e["d_holders"] >= 0]),
            "both_conc_foreign_buy": group_report([e for e in with_t if e["d_big"] > 0 and (e.get("f20") or 0) > 0]),
            "both_dist_foreign_sell": group_report([e for e in with_t if e["d_big"] <= 0 and e.get("f20") is not None and e["f20"] < 0]),
        })
    summary = {"events": len(events), "withForeign": len(with_f), "foreign": foreign_result, "checks": checks, "decision": decision, "tdcc_exploratory": tdcc_result}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    with gzip.open(out / "events.csv.gz", "wt", newline="") as f:
        w = csv.writer(f)
        cols = ["market", "code", "date", "f20", "reclaim5", "hold60", "hold_ex60", "r5h60", "hold120", "hold_ex120", "r5h120", "d_big", "d_holders"]
        w.writerow(cols)
        for e in events:
            w.writerow([e.get(c) if not isinstance(e.get(c), float) else round(e[c], 5) for c in cols])
    print(json.dumps({"events": len(events), "withForeign": len(with_f), "decision": decision, "checks": checks, "tdccEvents": len(with_t)}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:5])
