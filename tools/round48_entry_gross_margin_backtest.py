#!/usr/bin/env python3
"""第 48 輪：網站進場三條件 × 單季毛利率「季增且年增」，合在一起會不會更好。
擁有者 2026-11-27 21:40「好」（要改網站主結論前，先確認回測有效的訊號合起來是否更好）。規則在看結果前寫定（REGISTERED_AT）。

用法：python3 -I tools/round48_entry_gross_margin_backtest.py <股價資料夾> <營收 revenue.csv.gz> <t163sb04 原始頁資料夾> <輸出資料夾>

一、評估方式（同第 33、35 輪）
- 每 5 個交易日評估一次；合格：收盤 ≥ 10 元、前 20 日平均成交金額 ≥ 1,000 萬、技術訊號算得出來、至少 121 筆歷史。上市＋上櫃。
- 進場三條件（網站現行，擁有者 2026-10-26 核准）：技術強（三問技術過且均線強弱 ≥ +3）＋近 3 月營收年增平均 > 10%（75 天內公布）
  ＋均線排列強（5、10 日線都在 20 日線與半年線之上）。還原價計算，同第 35 輪。
- 結果：評估日收盤之後 20、60 個交易日報酬，超額＝減同一天全部合格股票平均（同第 35 輪）；另列 20 日內跌 ≥ 20%、60 日內跌 ≥ 30% 的比例。

二、毛利率狀態（同第 47 輪的資料與算法）
- 單季毛利率：t163sb04 累計數還原單季，營業毛利 ÷ 營業收入。
- 評估日只用「法定公告期限（Q1 5/15、Q2 8/14、Q3 11/14、年報 3/31）已過」的最近一季；
  G＝那一季毛利率比上一季高、也比去年同季高；非 G＝三個數字都有但不是 G；不明＝那一季或比較季缺資料（不往前找更舊的季）。
- 期間：2014-04 起（年增要有去年資料）；分 2014–2018、2019–最後。

三、統計：先算每個月（評估日月份）的平均，再對月平均；標準誤＝月平均的標準差 ÷ √月數 × √(期間 ÷ 20)。

四、事先寫定的判斷
- 在符合進場三條件的樣本裡，兩段都滿足「G 減非 G 的 20 日超額 ≥ +0.5 個百分點」且「60 日超額差 ≥ +1.0 個百分點」
  → 支持把「毛利率季增且年增」加進進場判斷。否則不支持（維持只顯示）。
- 另列（只列數字）：進場三條件整體、G 但不符合進場、兩者都不符合。
- 結果只寫進 gate-probe；網站要擁有者看過、同意後才改。
"""
import datetime as dt
import json
import math
import statistics
import sys
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from round33_backtest import revenue_index  # noqa: E402
from round47_gross_margin_backtest import DEADLINE, quarterly_margins  # noqa: E402
from stock_signal_backtest import load, signals  # noqa: E402

REGISTERED_AT = "2026-11-27 21:41 台北"
D = dt.date
START = D(2014, 4, 1)
SPLIT = D(2019, 1, 1)


def margin_states(gm):
    """回傳 [(可用日, 年, 季)] 依可用日排序，與 {code: {(年,季): 'G'|'notG'}}。"""
    avail = []
    for (y, s) in sorted(gm):
        m, d = DEADLINE[s]
        avail.append((D(y + (1 if s == 4 else 0), m, d), y, s))
    avail.sort()
    state = defaultdict(dict)
    for (y, s), rows in gm.items():
        prev_q = (y, s - 1) if s > 1 else (y - 1, 4)
        for code, now in rows.items():
            q, yy = gm.get(prev_q, {}).get(code), gm.get((y - 1, s), {}).get(code)
            if q is None or yy is None:
                continue
            state[code][(y, s)] = "G" if now > q and now > yy else "notG"
    return avail, state


def month_stats(pairs, h):
    by = defaultdict(list)
    for month, x in pairs:
        by[month].append(x)
    means = [statistics.fmean(v) for v in by.values()]
    if not means:
        return None
    se = statistics.stdev(means) / math.sqrt(len(means)) * math.sqrt(h / 20) if len(means) > 1 else None
    return {"mean": statistics.fmean(means), "se": se, "n": len(pairs), "months": len(means)}


def main(price_folder, revenue_path, raw_folder, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    series, _ = load(price_folder)
    rev = revenue_index(revenue_path)
    avail, state = margin_states(quarterly_margins(raw_folder))
    avail_dates = [a[0] for a in avail]
    cal = sorted({d for rows in series.values() for d, *_ in rows})
    eval_days = set(cal[::5])
    recs = []
    for (market, code), rows in series.items():
        if len(rows) < 130:
            continue
        dates, close, adj, score, tech, rsi, val20 = signals(rows)
        n = len(rows)
        cs = np.concatenate([[0.0], np.cumsum(adj)])
        ma = lambda k, i: (cs[i + 1] - cs[i + 1 - k]) / k  # noqa: E731
        rv = rev.get((market, code), [])
        rvd = [x[0] for x in rv]
        st = state.get(code, {})
        for i in range(120, n - 1):
            d = dates[i]
            if d not in eval_days or d < START or d > cal[-1] - dt.timedelta(days=95):
                continue
            if close[i] < 10 or val20[i] < 1e7 or math.isnan(score[i]) or math.isnan(tech[i]):
                continue
            m5, m10, m20, m120 = ma(5, i), ma(10, i), ma(20, i), ma(120, i)
            strong = m5 > m20 and m10 > m20 and m5 > m120 and m10 > m120
            j = bisect_right(rvd, d) - 1
            entry = tech[i] == 0 and score[i] >= 3 and j >= 0 and (d - rv[j][0]).days <= 75 and rv[j][1] > 10 and strong
            k = bisect_right(avail_dates, d - dt.timedelta(days=1)) - 1   # 期限「已過」：期限日之後才算知道
            g = st.get((avail[k][1], avail[k][2]), "unknown") if k >= 0 else "unknown"
            fw20 = adj[min(i + 20, n - 1)] / adj[i] - 1
            fw60 = adj[min(i + 60, n - 1)] / adj[i] - 1
            recs.append((d, entry, g, fw20, fw60, adj[i + 1:min(i + 21, n)].min() / adj[i] - 1, adj[i + 1:min(i + 61, n)].min() / adj[i] - 1))
    by_day = defaultdict(list)
    for r in recs:
        by_day[r[0]].append(r)
    mean20 = {d: statistics.fmean(x[3] for x in v) for d, v in by_day.items()}
    mean60 = {d: statistics.fmean(x[4] for x in v) for d, v in by_day.items()}

    def group(rows):
        if not rows:
            return None
        return {"ex20": month_stats([(r[0].isoformat()[:7], r[3] - mean20[r[0]]) for r in rows], 20),
                "ex60": month_stats([(r[0].isoformat()[:7], r[4] - mean60[r[0]]) for r in rows], 60),
                "crash20": float(np.mean([r[5] <= -0.2 for r in rows])), "crash60": float(np.mean([r[6] <= -0.3 for r in rows])), "n": len(rows)}

    def diff(a, b, h):
        """同月份配對的差（G − 非G），再對月平均。"""
        ma_, mb = defaultdict(list), defaultdict(list)
        mean = mean20 if h == 20 else mean60
        for r in a:
            ma_[r[0].isoformat()[:7]].append((r[3] if h == 20 else r[4]) - mean[r[0]])
        for r in b:
            mb[r[0].isoformat()[:7]].append((r[3] if h == 20 else r[4]) - mean[r[0]])
        ds = [statistics.fmean(ma_[m]) - statistics.fmean(mb[m]) for m in ma_ if m in mb]
        if not ds:
            return None
        se = statistics.stdev(ds) / math.sqrt(len(ds)) * math.sqrt(h / 20) if len(ds) > 1 else None
        return {"mean": statistics.fmean(ds), "se": se, "months": len(ds), "positive": sum(x > 0 for x in ds) / len(ds)}

    summary = {"registeredAt": REGISTERED_AT, "records": len(recs), "first": min(r[0] for r in recs).isoformat(), "last": max(r[0] for r in recs).isoformat(), "parts": {}}
    checks = {}
    for name, keep in (("2014-2018", lambda d: d < SPLIT), ("2019-", lambda d: d >= SPLIT), ("all", lambda d: True)):
        rows = [r for r in recs if keep(r[0])]
        e = [r for r in rows if r[1]]
        part = {"entry_all": group(e), "entry_G": group([r for r in e if r[2] == "G"]), "entry_notG": group([r for r in e if r[2] == "notG"]),
                "entry_unknown": group([r for r in e if r[2] == "unknown"]), "G_not_entry": group([r for r in rows if not r[1] and r[2] == "G"]),
                "neither": group([r for r in rows if not r[1] and r[2] == "notG"]),
                "diff20_entry_G_minus_notG": diff([r for r in e if r[2] == "G"], [r for r in e if r[2] == "notG"], 20),
                "diff60_entry_G_minus_notG": diff([r for r in e if r[2] == "G"], [r for r in e if r[2] == "notG"], 60)}
        summary["parts"][name] = part
        if name != "all":
            d20, d60 = part["diff20_entry_G_minus_notG"], part["diff60_entry_G_minus_notG"]
            checks[name] = {"diff20": d20 and d20["mean"], "diff60": d60 and d60["mean"],
                            "pass": bool(d20 and d60 and d20["mean"] >= 0.005 and d60["mean"] >= 0.01)}
    summary["checks"] = checks
    summary["decision"] = "supported" if all(c["pass"] for c in checks.values()) else "not_supported"
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"records": len(recs), "decision": summary["decision"], "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:5])
