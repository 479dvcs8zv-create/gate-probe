#!/usr/bin/env python3
"""第 34 輪：短線出場規則。擁有者 2026-10-26 22:53：「短線強弱看 5 跟 10 日，趨勢看 20 日。」
規則在看結果前寫定（2026-10-26 23:05）。

用法：python3 -I tools/round34_exit_backtest.py <股價資料夾> <營收 revenue.csv.gz> <輸出資料夾>

一、進場（擁有者 21:51 核准的條件，同第 33 輪）
- 每 5 個交易日檢查一次；合格（66 筆以上歷史、收盤 ≥ 10、前 20 日均成交金額 ≥ 1,000 萬）且
  技術強（三問技術過、均線強弱 ≥ +3）＋近 3 個已公布月份營收年增率平均 > 10% → 當天收盤買進。
- 同一檔持有中不重複進場；出場當天之後才可再進。

二、出場（每天收盤檢查，觸發就當天收盤賣出；最長 60 個交易日）
- X20：固定抱 20 個交易日。
- S10：收盤跌破 10 日線就出（短線轉弱）。
- S5：收盤同時跌破 5 日線與 10 日線就出。
- T20：收盤跌破 20 日線就出（趨勢破壞）。
- T20D：收盤在 20 日線下、而且 20 日線下彎就出（趨勢轉空）。
- S10T20：短線看 10 日、趨勢看 20 日——收盤跌破 10 日線且 20 日線下彎，或收盤跌破 20 日線，就出。

三、結果（每筆交易扣一買一賣 0.585%）
- 交易筆數、每筆平均與中位數報酬、勝率、平均持有天數、每持有一天平均報酬、
  最差 5% 交易的報酬、虧損超過 10% 的比例、同期間「全部合格股票等權」的報酬（看是否贏大盤）。
- 分 2006–2015、2016–2026（以進場日分）。均線用還原價計算。
"""
import datetime as dt
import json
import math
import sys
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from stock_signal_backtest import load, signals  # noqa: E402
from round33_backtest import revenue_index  # noqa: E402

D = dt.date
COST = 0.00585
RULES = ["X20", "S10", "S5", "T20", "T20D", "S10T20"]


def main(price_folder, revenue_path, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    series, stats = load(price_folder)
    rev = revenue_index(revenue_path)
    cal = sorted({d for rows in series.values() for d, *_ in rows})
    eval_days = set(cal[::5])
    day_rets = defaultdict(list)
    per_stock = []
    for (market, code), rows in series.items():
        if len(rows) < 70:
            continue
        dates, close, adj, score, tech, rsi, val20 = signals(rows)
        n = len(rows)
        cs = np.concatenate([[0.0], np.cumsum(adj)])
        ma = lambda k, i, cs=cs: (cs[i + 1] - cs[i + 1 - k]) / k if i + 1 - k >= 0 else math.nan  # noqa: E731  每檔綁自己的累積和
        rv = rev.get((market, code), []); rvd = [x[0] for x in rv]
        entries = []
        for i in range(65, n - 1):
            d = dates[i]
            ok = close[i] >= 10 and val20[i] >= 1e7 and not math.isnan(score[i]) and not math.isnan(tech[i])
            if ok:
                day_rets[dates[i + 1]].append(adj[i + 1] / adj[i] - 1)
            if not ok or d not in eval_days or d > cal[-1] - dt.timedelta(days=95):
                continue
            if not (tech[i] == 0 and score[i] >= 3):
                continue
            j = bisect_right(rvd, d) - 1
            if j < 0 or (d - rv[j][0]).days > 75 or not rv[j][1] > 10:
                continue
            entries.append(i)
        per_stock.append((market, code, dates, adj, entries, ma, n))
    mdates = sorted(day_rets); midx = {d: k for k, d in enumerate(mdates)}
    mcum = np.concatenate([[1.0], np.cumprod([1 + float(np.mean(day_rets[d])) for d in mdates])])

    def market_ret(d0, d1):  # 進場日收盤到出場日收盤
        a = bisect_right(mdates, d0); b = bisect_right(mdates, d1)
        return mcum[b] / mcum[a] - 1

    trades = {r: [] for r in RULES}
    for market, code, dates, adj, entries, ma, n in per_stock:
        for r in RULES:
            free_from = -1
            for i in entries:
                if i <= free_from:
                    continue
                exit_i = None
                for k in range(i + 1, min(i + 60, n - 1) + 1):
                    c = adj[k]
                    m5, m10, m20, m20p = ma(5, k), ma(10, k), ma(20, k), ma(20, k - 1)
                    hit = (r == "X20" and k - i >= 20) or (r == "S10" and c < m10) or (r == "S5" and c < m5 and c < m10) or \
                          (r == "T20" and c < m20) or (r == "T20D" and c < m20 and m20 < m20p) or \
                          (r == "S10T20" and ((c < m10 and m20 < m20p) or c < m20))
                    if hit:
                        exit_i = k; break
                if exit_i is None:
                    exit_i = min(i + 60, n - 1)
                ret = adj[exit_i] / adj[i] - 1 - COST
                trades[r].append((dates[i], ret, exit_i - i, market_ret(dates[i], dates[exit_i]) - COST))
                free_from = exit_i
    lines = []; p = lines.append; res = {}
    p(f"股價 {cal[0]}～{cal[-1]}；進場條件：技術強＋近 3 月營收年增 >10%（每 5 個交易日檢查）；每筆已扣 0.585%")
    names = {"X20": "X20 固定 20 天", "S10": "S10 跌破 10 日線出", "S5": "S5 跌破 5 日與 10 日線出", "T20": "T20 跌破 20 日線出",
             "T20D": "T20D 20 日線下且下彎出", "S10T20": "S10T20 跌破 10 日且 20 日下彎、或跌破 20 日線出"}
    for pname, pf in (("全期", lambda d: True), ("2006–2015", lambda d: d <= D(2015, 12, 31)), ("2016–2026", lambda d: d >= D(2016, 1, 1))):
        p(f"\n## {pname}")
        p("出場規則 | 筆數 | 每筆平均 | 中位數 | 勝率 | 平均持有天數 | 每天平均 | 最差5% | 虧損>10% 比例 | 同期大盤（同樣扣成本） | 贏大盤")
        for r in RULES:
            xs = [t for t in trades[r] if pf(t[0])]
            if not xs:
                continue
            rets = np.array([t[1] for t in xs]); days = np.array([t[2] for t in xs]); mk = np.array([t[3] for t in xs])
            row = {"n": len(xs), "mean": float(rets.mean()), "median": float(np.median(rets)), "win": float((rets > 0).mean()),
                   "days": float(days.mean()), "per_day": float(rets.mean() / days.mean()), "p5": float(np.percentile(rets, 5)),
                   "loss10": float((rets < -0.10).mean()), "market": float(mk.mean()), "beat": float((rets > mk).mean())}
            res[f"{pname}|{r}"] = row
            p(f"{names[r]} | {row['n']:,} | {row['mean']*100:+.2f}% | {row['median']*100:+.2f}% | {row['win']*100:.1f}% | {row['days']:.1f} | "
              f"{row['per_day']*100:+.3f}% | {row['p5']*100:.1f}% | {row['loss10']*100:.1f}% | {row['market']*100:+.2f}% | {row['beat']*100:.1f}%")
    (out / "output.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print("\n".join(lines))


if __name__ == "__main__":
    main(*sys.argv[1:])
