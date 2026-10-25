#!/usr/bin/env python3
"""第 32 輪：個股回測——網站用股價算的個股訊號，分數高的股票之後是否比分數低的好。規則在看結果前寫定。

用法：python3 -I tools/stock_signal_backtest.py <股價資料夾 results/backtest-data/stock-prices> <輸出資料夾>

一、資料與還原
- 上市（TWSE MI_INDEX 逐日）、上櫃（TPEx dailyQuotes，2007-07 起）全部 4 碼普通股，含日後下市者（無存活者偏差）。
- 除權息還原的當日報酬：上市＝收盤 ÷（收盤 − 漲跌價差）− 1；上櫃＝收盤 ÷ 前一交易日「次日參考價」− 1。
  （兩者都以交易所公布的參考價為基準，除權息日的下跌不算虧損。）
- 無成交（收盤 0 或 --）當天不算一筆；漲跌標記 X（不比價）、或報酬超過當時漲跌幅上限（2015-06-01 前 7%、之後 10%，
  加 0.5% 容忍）視為無法還原（例如減資、新上市），當天報酬記 0。這些天數另外統計。
- 訊號用還原後價格計算（網站用未還原收盤，回測用還原價避免除息日誤判；註明差異）。

二、訊號（照抄網站 worker/panel-calculations.mjs）
- 均線強弱分數 −4～+4：5／10／20／60 日線各一票；收盤在線上且線上彎 +1，收盤在線下且線下彎 −1，其餘 0。需 61 筆。
- 三問「技術」：收盤連續超過 5 個交易日低於 60 日線，且 60 日線比前一日低 → 不過；否則過。需 66 筆。
- RSI(14)：Wilder 平滑、從第一筆一路算到當天。分組 <20、20–30、30–50、50–70、70–80、≥80。

三、評估
- 每 5 個交易日取一次（約每週），只看當天：有 66 筆以上歷史、收盤 ≥ 10 元、前 20 個交易日平均成交金額 ≥ 1,000 萬元的股票。
- 之後 20、60 個交易日的還原報酬；股票中途下市就算到最後一個交易日（含下市損失）。
- 「超額」＝該股之後報酬 − 同一天所有合格股票的平均（等權）。看各組平均、勝率（超額 > 0 的比例）。
- 分 2006–2015、2016–2026 兩段，上市、上櫃分開與合計；不扣交易成本（一買一賣約 0.585%，報告另列）。
"""
import csv
import datetime as dt
import gzip
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

D = dt.date


def limit_for(d):
    return 0.075 if d < D(2015, 6, 1) else 0.105


def load(folder):
    """回傳 {(market, code): [(date, close, ret_or_None, value)]}，依日期排序。"""
    series = defaultdict(list)
    stats = defaultdict(int)
    for market in ("twse", "tpex"):
        files = sorted(Path(folder).glob(f"{market}-[0-9][0-9][0-9][0-9].csv.gz"))
        prev_ref = {}
        for p in files:
            with gzip.open(p, "rt", newline="") as f:
                rows = list(csv.DictReader(f))
            rows.sort(key=lambda r: (r["date"], r["code"]))
            for r in rows:
                d = D.fromisoformat(r["date"]); code = r["code"]
                try:
                    close = float(r["close"])
                except ValueError:
                    close = 0.0
                try:
                    value = float(r["value"] or 0)
                except ValueError:
                    value = 0.0
                ret = None
                if market == "twse":
                    sign = r["sign"]
                    try:
                        chg = float(r["change"] or 0)
                    except ValueError:
                        chg = None
                    if close > 0 and chg is not None and sign in ("+", "-", "0", " ", ""):
                        signed = chg if sign == "+" else -chg if sign == "-" else 0.0
                        base = close - signed
                        ret = close / base - 1 if base > 0 else None
                else:
                    ref = prev_ref.get(code)
                    if close > 0 and ref and ref > 0:
                        ret = close / ref - 1
                    try:
                        nr = float(r["next_ref"])
                    except ValueError:
                        nr = 0.0
                    if nr > 0:
                        prev_ref[code] = nr
                if close <= 0:
                    stats["no_trade"] += 1
                    continue
                if ret is None or abs(ret) > limit_for(d):
                    stats["unadjustable"] += 1
                    ret = None
                stats["obs"] += 1
                series[(market, code)].append((d, close, ret, value))
    return series, dict(stats)


def signals(rows):
    """對一檔股票逐日算還原價、均線分數、技術題、RSI。回傳 numpy 陣列。"""
    n = len(rows)
    dates = [r[0] for r in rows]
    close = np.array([r[1] for r in rows])
    value = np.array([r[3] for r in rows])
    ret = np.array([0.0 if r[2] is None else r[2] for r in rows])
    ret[0] = 0.0
    adj = 100 * np.cumprod(1 + ret)
    cs = np.concatenate([[0.0], np.cumsum(adj)])

    def ma(k, i):  # 第 i 天（含）的 k 日均
        return (cs[i + 1] - cs[i + 1 - k]) / k
    score = np.full(n, np.nan)
    tech = np.full(n, np.nan)   # 1＝不過，0＝過
    rsi = np.full(n, np.nan)
    below = 0
    gain = loss = 0.0
    for i in range(n):
        if i >= 60:
            s = 0
            for k in (5, 10, 20, 60):
                m, pm = ma(k, i), ma(k, i - 1)
                s += 1 if adj[i] > m and m > pm else -1 if adj[i] < m and m < pm else 0
            score[i] = s
        if i >= 59:
            below = below + 1 if adj[i] < ma(60, i) else 0
            if i >= 65:
                falling = ma(60, i) < ma(60, i - 1)
                tech[i] = 1.0 if below > 5 and falling else 0.0
        if i >= 1:
            dlt = adj[i] - adj[i - 1]
            if i <= 14:
                gain += max(dlt, 0); loss += max(-dlt, 0)
                if i == 14:
                    gain /= 14; loss /= 14
            else:
                gain = (gain * 13 + max(dlt, 0)) / 14; loss = (loss * 13 + max(-dlt, 0)) / 14
            if i >= 59:
                rsi[i] = 100.0 if loss == 0 else 100 - 100 / (1 + gain / loss)
    cv = np.concatenate([[0.0], np.cumsum(value)])
    lo = np.maximum(0, np.arange(n) - 19)
    val20 = (cv[np.arange(n) + 1] - cv[lo]) / (np.arange(n) + 1 - lo)
    return dates, close, adj, score, tech, rsi, val20


def main(folder, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    series, stats = load(folder)
    cal = sorted({d for rows in series.values() for d, *_ in rows})
    eval_days = set(cal[::5])
    recs = []  # (date, market, code, score, tech, rsi, f20, f60)
    for (market, code), rows in series.items():
        if len(rows) < 70:
            continue
        dates, close, adj, score, tech, rsi, val20 = signals(rows)
        n = len(rows)
        for i in range(65, n - 1):
            d = dates[i]
            if d not in eval_days or close[i] < 10 or val20[i] < 1e7:
                continue
            f20 = adj[min(i + 20, n - 1)] / adj[i] - 1
            f60 = adj[min(i + 60, n - 1)] / adj[i] - 1
            if d > cal[-1] - dt.timedelta(days=95):
                continue  # 60 日後的資料還沒有
            recs.append((d, market, code, score[i], tech[i], rsi[i], f20, f60))
    by_day = defaultdict(list)
    for r in recs:
        by_day[r[0]].append(r)
    mean20 = {d: np.mean([x[6] for x in v]) for d, v in by_day.items()}
    mean60 = {d: np.mean([x[7] for x in v]) for d, v in by_day.items()}
    lines = []
    p = lines.append
    p(f"資料：{cal[0]}～{cal[-1]}；股票 {len(series)} 檔（上市 {sum(1 for k in series if k[0]=='twse')}、上櫃 {sum(1 for k in series if k[0]=='tpex')}）；"
      f"有成交的股票日 {stats.get('obs',0):,}，無法還原（記 0）{stats.get('unadjustable',0):,}，無成交 {stats.get('no_trade',0):,}")
    p(f"評估樣本：{len(recs):,} 筆（{len(by_day)} 個評估日，每 5 個交易日一次）")

    def table(title, key, groups, subset=lambda r: True):
        p(f"\n## {title}")
        p("組 | 筆數 | 之後20日 | 20日超額 | 20日勝率 | 之後60日 | 60日超額 | 60日勝率")
        for name, f in groups:
            xs = [r for r in recs if subset(r) and not math.isnan(key(r)) and f(key(r))]
            if not xs:
                p(f"{name} | 0 | | | | | |"); continue
            e20 = [r[6] - mean20[r[0]] for r in xs]; e60 = [r[7] - mean60[r[0]] for r in xs]
            p(f"{name} | {len(xs):,} | {np.mean([r[6] for r in xs])*100:+.2f}% | {np.mean(e20)*100:+.2f}% | {np.mean([e>0 for e in e20])*100:.1f}% | "
              f"{np.mean([r[7] for r in xs])*100:+.2f}% | {np.mean(e60)*100:+.2f}% | {np.mean([e>0 for e in e60])*100:.1f}%")
    ma_groups = [(f"{s:+d}", (lambda s: lambda v: v == s)(s)) for s in range(4, -5, -1)]
    tech_groups = [("過", lambda v: v == 0), ("不過", lambda v: v == 1)]
    rsi_groups = [("≥80", lambda v: v >= 80), ("70–80", lambda v: 70 <= v < 80), ("50–70", lambda v: 50 <= v < 70),
                  ("30–50", lambda v: 30 <= v < 50), ("20–30", lambda v: 20 <= v < 30), ("<20", lambda v: v < 20)]
    periods = [("全期", lambda r: True), ("2006–2015", lambda r: r[0] <= D(2015, 12, 31)), ("2016–2026", lambda r: r[0] >= D(2016, 1, 1))]
    for pname, pf in periods:
        table(f"均線強弱分數（{pname}，上市＋上櫃）", lambda r: r[3], ma_groups, pf)
    for pname, pf in periods:
        table(f"三問・技術（{pname}，上市＋上櫃）", lambda r: r[4], tech_groups, pf)
    for pname, pf in periods:
        table(f"RSI(14)（{pname}，上市＋上櫃）", lambda r: r[5], rsi_groups, pf)
    for mk, mname in (("twse", "上市"), ("tpex", "上櫃")):
        table(f"均線強弱分數（全期，只看{mname}）", lambda r: r[3], ma_groups, lambda r, mk=mk: r[1] == mk)
        table(f"三問・技術（全期，只看{mname}）", lambda r: r[4], tech_groups, lambda r, mk=mk: r[1] == mk)
    combo = [("均線 ≥ +3 且技術過", lambda r: r[3] >= 3 and r[4] == 0), ("均線 ≤ −3 且技術不過", lambda r: r[3] <= -3 and r[4] == 1)]
    p("\n## 組合（全期）")
    p("組 | 筆數 | 20日超額 | 20日勝率 | 60日超額 | 60日勝率")
    for name, f in combo:
        xs = [r for r in recs if not math.isnan(r[3]) and not math.isnan(r[4]) and f(r)]
        e20 = [r[6] - mean20[r[0]] for r in xs]; e60 = [r[7] - mean60[r[0]] for r in xs]
        p(f"{name} | {len(xs):,} | {np.mean(e20)*100:+.2f}% | {np.mean([e>0 for e in e20])*100:.1f}% | {np.mean(e60)*100:+.2f}% | {np.mean([e>0 for e in e60])*100:.1f}%")
    p("\n交易成本參考：一買一賣約 0.585%（手續費 0.1425%×2＋證交稅 0.3%）。")
    (out / "output.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "stats.json").write_text(json.dumps({"stats": stats, "records": len(recs), "eval_days": len(by_day)}, ensure_ascii=False, indent=1))
    print("\n".join(lines))


if __name__ == "__main__":
    main(*sys.argv[1:])
