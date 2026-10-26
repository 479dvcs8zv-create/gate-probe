#!/usr/bin/env python3
"""第 35 輪：均線排列。擁有者 2026-10-26 23:24：「5、10 日線在 20 日線下或半年線下，股價很疲弱、勝率更低；反之在上面越強勢。」
規則在看結果前寫定（2026-10-26 23:30）。

用法：python3 -I tools/round35_alignment_backtest.py <股價資料夾> <營收 revenue.csv.gz> <輸出資料夾>

- 均線用還原價：MA5、MA10、MA20、MA120（半年線，約 120 個交易日）。需 121 筆以上歷史。
- 排列分三種：
  強：MA5 與 MA10 都在 MA20 之上，且都在 MA120 之上。
  弱：MA5 與 MA10 都在 MA20 之下，或都在 MA120 之下。
  中：其餘。
- 評估同第 33 輪：每 5 個交易日、合格股票（收盤 ≥ 10、前 20 日均成交金額 ≥ 1,000 萬、技術訊號可算）。
  看之後 5／10／20／60 日超額（減同日全部合格股票平均）、20 日勝率（之後 20 日報酬 > 0 的比例）、20 日超額勝率、
  20 日內跌 ≥20%、60 日內跌 ≥30% 的比例。
- 另看：在已核准的進場條件（技術強＋近 3 月營收年增 >10%）裡，再分三種排列，是否還有差別。
- 分 2006–2015、2016–2026。
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


def main(price_folder, revenue_path, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    series, stats = load(price_folder)
    rev = revenue_index(revenue_path)
    cal = sorted({d for rows in series.values() for d, *_ in rows})
    eval_days = set(cal[::5])
    recs = []  # (date, align, entry_ok, f5, f10, f20, f60, dd20, dd60)
    for (market, code), rows in series.items():
        if len(rows) < 130:
            continue
        dates, close, adj, score, tech, rsi, val20 = signals(rows)
        n = len(rows)
        cs = np.concatenate([[0.0], np.cumsum(adj)])
        ma = lambda k, i: (cs[i + 1] - cs[i + 1 - k]) / k  # noqa: E731  （每檔當下就用，不存起來）
        rv = rev.get((market, code), []); rvd = [x[0] for x in rv]
        for i in range(120, n - 1):
            d = dates[i]
            if d not in eval_days or d > cal[-1] - dt.timedelta(days=95):
                continue
            if close[i] < 10 or val20[i] < 1e7 or math.isnan(score[i]) or math.isnan(tech[i]):
                continue
            m5, m10, m20, m120 = ma(5, i), ma(10, i), ma(20, i), ma(120, i)
            if m5 > m20 and m10 > m20 and m5 > m120 and m10 > m120:
                al = "強"
            elif (m5 < m20 and m10 < m20) or (m5 < m120 and m10 < m120):
                al = "弱"
            else:
                al = "中"
            j = bisect_right(rvd, d) - 1
            entry = tech[i] == 0 and score[i] >= 3 and j >= 0 and (d - rv[j][0]).days <= 75 and rv[j][1] > 10
            fw = [adj[min(i + h, n - 1)] / adj[i] - 1 for h in (5, 10, 20, 60)]
            recs.append((d, al, entry, *fw, adj[i + 1:min(i + 21, n)].min() / adj[i] - 1, adj[i + 1:min(i + 61, n)].min() / adj[i] - 1))
    by_day = defaultdict(list)
    for r in recs:
        by_day[r[0]].append(r)
    means = {h: {d: np.mean([x[3 + h] for x in v]) for d, v in by_day.items()} for h in range(4)}
    lines = []; p = lines.append; res = {}
    p(f"股價 {cal[0]}～{cal[-1]}；評估樣本 {len(recs):,} 筆（需 121 筆以上歷史）")
    for pname, pf in (("全期", lambda d: True), ("2006–2015", lambda d: d <= D(2015, 12, 31)), ("2016–2026", lambda d: d >= D(2016, 1, 1))):
        for scope, sf in (("全部合格股票", lambda r: True), ("已核准進場條件（技術強＋營收成長）內", lambda r: r[2])):
            p(f"\n## {pname}｜{scope}")
            p("排列 | 筆數 | 5日超額 | 10日超額 | 20日超額 | 60日超額 | 20日上漲機率 | 20日贏大盤機率 | 20日內跌≥20% | 60日內跌≥30%")
            for al in ("強", "中", "弱"):
                xs = [r for r in recs if pf(r[0]) and sf(r) and r[1] == al]
                if not xs:
                    continue
                ex = [[r[3 + h] - means[h][r[0]] for r in xs] for h in range(4)]
                row = {"n": len(xs), "ex5": float(np.mean(ex[0])), "ex10": float(np.mean(ex[1])), "ex20": float(np.mean(ex[2])), "ex60": float(np.mean(ex[3])),
                       "up20": float(np.mean([r[5] > 0 for r in xs])), "beat20": float(np.mean([e > 0 for e in ex[2]])),
                       "crash20": float(np.mean([r[7] <= -0.2 for r in xs])), "crash60": float(np.mean([r[8] <= -0.3 for r in xs]))}
                res[f"{pname}|{scope}|{al}"] = row
                p(f"{al} | {row['n']:,} | {row['ex5']*100:+.2f}% | {row['ex10']*100:+.2f}% | {row['ex20']*100:+.2f}% | {row['ex60']*100:+.2f}% | "
                  f"{row['up20']*100:.1f}% | {row['beat20']*100:.1f}% | {row['crash20']*100:.1f}% | {row['crash60']*100:.1f}%")
    (out / "output.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print("\n".join(lines))


if __name__ == "__main__":
    main(*sys.argv[1:])
