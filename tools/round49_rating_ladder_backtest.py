#!/usr/bin/env python3
"""第 49 輪：Gemini 建議的新主結論階梯（技術狀態分級）有沒有照順序分出好壞。
擁有者 2026-11-28 00:15「做完吧」（Gemini 2026-11-27 文件第二節的決策樹）。規則在看結果前寫定（REGISTERED_AT）。

用法：python3 -I tools/round49_rating_ladder_backtest.py <股價資料夾> <營收 revenue.csv.gz> <t163sb04 原始頁資料夾> <輸出資料夾>

一、評估方式（同第 48 輪）：每 5 個交易日；合格＝收盤 ≥ 10 元、前 20 日均額 ≥ 1,000 萬、技術訊號算得出來、至少 121 筆歷史；上市＋上櫃；還原價。
二、分級（依序判斷，先符合先算）
- D：收盤 < 20 日線，而且 < 60 日線。
- C：收盤 < 20 日線（仍在 60 日線上）。
- A：進場三條件（同第 48 輪）＋毛利率季增且年增（公告期限已過的最近一季）。
  Gemini 的 A 另要求「現金流健康」：歷史現金流量表沒有免費彙總檔，本輪不加這一條（照實註明）。
- B+：進場三條件，但毛利率不是季增年增或不明。
- B：其餘（收盤在 20 日線上、未符合進場三條件）。
三、結果：之後 20、60 個交易日的超額（減同一天全部合格股票平均）；先算每月平均、再對月平均。
  分兩段：2014-04～2018、2019～最後（毛利率要有去年資料）。另列 2006～2013（只分 D／C／B／E，E＝A＋B+）。
四、事先寫定的判斷
- 主判斷（E＝A＋B+ 合併）：兩段都滿足 20 日超額 D < C < B < E，而且 E − D ≥ +1.0 個百分點 → 支持以這個階梯當網站主結論。
- A、B+ 要不要分開：兩段都滿足「A − B+（同月配對）20 日超額 ≥ +0.5 個百分點」才分開；否則合併成一級。
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
from round47_gross_margin_backtest import quarterly_margins  # noqa: E402
from round48_entry_gross_margin_backtest import margin_states, month_stats  # noqa: E402
from stock_signal_backtest import load, signals  # noqa: E402

REGISTERED_AT = "2026-11-28 00:18 台北"
D = dt.date
PERIODS = (("2006-2013", D(2006, 1, 1), D(2014, 1, 1)), ("2014-2018", D(2014, 4, 1), D(2019, 1, 1)), ("2019-", D(2019, 1, 1), D(2100, 1, 1)))


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
            if d not in eval_days or d > cal[-1] - dt.timedelta(days=95):
                continue
            if close[i] < 10 or val20[i] < 1e7 or math.isnan(score[i]) or math.isnan(tech[i]):
                continue
            m5, m10, m20, m60, m120 = ma(5, i), ma(10, i), ma(20, i), ma(60, i), ma(120, i)
            c = adj[i]
            j = bisect_right(rvd, d) - 1
            entry = (tech[i] == 0 and score[i] >= 3 and j >= 0 and (d - rv[j][0]).days <= 75 and rv[j][1] > 10
                     and m5 > m20 and m10 > m20 and m5 > m120 and m10 > m120)
            k = bisect_right(avail_dates, d - dt.timedelta(days=1)) - 1
            g = st.get((avail[k][1], avail[k][2])) if k >= 0 else None
            if c < m20 and c < m60:
                tier = "D"
            elif c < m20:
                tier = "C"
            elif entry:
                tier = "A" if g == "G" else "B+"
            else:
                tier = "B"
            recs.append((d, tier, adj[min(i + 20, n - 1)] / c - 1, adj[min(i + 60, n - 1)] / c - 1))
    by_day = defaultdict(list)
    for r in recs:
        by_day[r[0]].append(r)
    mean = {h: {d: statistics.fmean(x[h] for x in v) for d, v in by_day.items()} for h in (2, 3)}

    def stats(rows, h):
        return month_stats([(r[0].isoformat()[:7], r[2 if h == 20 else 3] - mean[2 if h == 20 else 3][r[0]]) for r in rows], h)

    def paired(a, b, h):
        col = 2 if h == 20 else 3
        ma_, mb = defaultdict(list), defaultdict(list)
        for r in a:
            ma_[r[0].isoformat()[:7]].append(r[col] - mean[col][r[0]])
        for r in b:
            mb[r[0].isoformat()[:7]].append(r[col] - mean[col][r[0]])
        ds = [statistics.fmean(ma_[m]) - statistics.fmean(mb[m]) for m in ma_ if m in mb]
        if len(ds) < 2:
            return None
        return {"mean": statistics.fmean(ds), "se": statistics.stdev(ds) / math.sqrt(len(ds)) * math.sqrt(h / 20), "months": len(ds)}

    summary = {"registeredAt": REGISTERED_AT, "records": len(recs), "note": "A 未含現金流條件（無歷史資料）", "parts": {}}
    checks = {}
    for name, lo, hi in PERIODS:
        rows = [r for r in recs if lo <= r[0] < hi]
        tiers = {t: [r for r in rows if r[1] == t] for t in ("D", "C", "B", "B+", "A")}
        tiers["E"] = tiers["A"] + tiers["B+"]
        part = {t: {"n": len(v), "share": len(v) / len(rows) if rows else None, "ex20": stats(v, 20), "ex60": stats(v, 60)} for t, v in tiers.items() if v}
        part["A_minus_Bplus"] = {"ex20": paired(tiers["A"], tiers["B+"], 20), "ex60": paired(tiers["A"], tiers["B+"], 60)}
        part["E_minus_D"] = {"ex20": paired(tiers["E"], tiers["D"], 20), "ex60": paired(tiers["E"], tiers["D"], 60)}
        summary["parts"][name] = part
        if name != "2006-2013":
            m = {t: part[t]["ex20"]["mean"] for t in ("D", "C", "B", "E")}
            ed = part["E_minus_D"]["ex20"]["mean"]
            ab = part["A_minus_Bplus"]["ex20"]
            checks[name] = {"ex20": m, "monotonic": m["D"] < m["C"] < m["B"] < m["E"], "E_minus_D": ed,
                            "ladder_pass": m["D"] < m["C"] < m["B"] < m["E"] and ed >= 0.01, "A_minus_Bplus": ab and ab["mean"],
                            "split_pass": bool(ab and ab["mean"] >= 0.005)}
    summary["checks"] = checks
    summary["decision"] = {"ladder": "supported" if all(c["ladder_pass"] for c in checks.values()) else "not_supported",
                           "split_A_Bplus": "keep_split" if all(c["split_pass"] for c in checks.values()) else "merge"}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"records": len(recs), "decision": summary["decision"], "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:5])
