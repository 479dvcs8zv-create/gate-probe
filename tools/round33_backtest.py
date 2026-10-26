#!/usr/bin/env python3
"""第 33 輪：擁有者 2026-10-26 21:15 的設計——
「個股幾乎都是短線；持股比例依當時總經狀況判斷，固定 65% 可以，但要上下加減；個股有可能跌到不值錢，
  要考慮技術面和公司狀況才決定要不要進。」
規則在看結果前寫定（2026-10-26 21:30）。

用法：python3 -I tools/round33_backtest.py <股價資料夾> <營收 revenue.csv.gz> <第31輪 score_history.csv> <輸出資料夾>

一、大盤層：65% 基準，依總經上下加減（收盤算、隔天生效；每變動 1 成扣 0.02%；現金報酬 0）
- 總經＝第 31 輪重建的網站總經分數（20 日平均，與網站同一套計分）。
- A   固定 65%。
- L5／L10／L15：20 日平均 ≥ 70（網站綠燈）→ 65＋k；55～69 → 65；< 55（橘燈以下）→ 65－k（k＝5、10、15）。
- D10：看「方向」不看高低——20 日平均比 60 個交易日前高 5 分以上 → 75；低 5 分以上 → 55；其餘 65。
- R10（反向，只當對照、不建議採用）：≥ 70 → 55；< 55 → 75。
- 套在兩種標的：加權指數（價格指數，同第 31 輪）、全部合格股票等權（同第 32 輪，含除權息還原）。
- 分 2006–2015、2016–2026 兩段。

二、個股層：進場前看技術面＋公司狀況（短線：之後 5、10、20 個交易日；另看 60 日）
- 技術（照網站）：強＝三問技術過且均線強弱 ≥ +3；弱＝三問技術不過；中＝其餘。
- 公司狀況＝月營收（公開資訊觀測站彙總檔）。只用當時已公布的：M 月營收從 M＋1 月 11 日起才可用。
  取最近 3 個已公布月份的年增率平均：成長＞+10%；衰退＜−10%；持平＝其餘；不足 3 個月＝不分組。
- 每 5 個交易日評估一次；合格條件同第 32 輪（66 筆以上歷史、收盤 ≥ 10、前 20 日均成交金額 ≥ 1,000 萬）。
- 看：之後 5／10／20／60 日超額（減同日全部合格股票平均）、勝率，以及「跌倒」機率：
  之後 20 日內最低收盤比進場價低 20% 以上的比例、之後 60 日內低 30% 以上的比例。
- 分 2006–2015、2016–2026 兩段。

限制：營收彙總檔是現在的版本（含事後更正）；不扣交易成本（一買一賣約 0.585%）。
"""
import csv
import datetime as dt
import gzip
import json
import math
import sys
from bisect import bisect_right
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from stock_signal_backtest import load, signals  # noqa: E402

D = dt.date


def macro(path):
    rows = list(csv.DictReader(open(path)))
    dates = [D.fromisoformat(r["date"]) for r in rows]
    raw = [float(r["raw"]) for r in rows]
    taiex = [float(r["taiex"]) for r in rows]
    ma = [sum(raw[max(0, i - 19):i + 1]) / len(raw[max(0, i - 19):i + 1]) for i in range(len(raw))]
    return dates, ma, taiex


def weight_rules(dates, ma):
    """每天收盤後的目標持股（隔天生效）。"""
    out = {}
    for name in ("A", "L5", "L10", "L15", "D10", "R10"):
        w = []
        for i, v in enumerate(ma):
            if name == "A":
                x = 65
            elif name[0] == "L":
                k = int(name[1:]); x = 65 + k if v >= 70 else 65 - k if v < 55 else 65
            elif name == "D10":
                x = 65 if i < 60 else 75 if v - ma[i - 60] >= 5 else 55 if v - ma[i - 60] <= -5 else 65
            else:
                x = 55 if v >= 70 else 75 if v < 55 else 65
            w.append(x / 100)
        out[name] = w
    return out


def simulate(dates, rets, weights, lo=None, hi=None, cost=0.0002):
    """rets[i]＝dates[i] 當天報酬；weights[i-1] 生效。回傳年化、最大跌幅、平均持股、每年調整次數。"""
    eq = peak = 1.0; mdd = 0.0; prev = None; n = 0; changes = 0; wsum = 0.0; first = last = None
    for i in range(1, len(dates)):
        d = dates[i]
        if (lo and d < lo) or (hi and d > hi) or rets[i] is None:
            continue
        w = weights[i - 1]
        c = cost * abs(w - prev) * 10 if prev is not None else 0.0
        if prev is not None and abs(w - prev) > 1e-9:
            changes += 1
        eq *= 1 + w * rets[i] - c; peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
        prev = w; n += 1; wsum += w; first = first or d; last = d
    yrs = (last - first).days / 365.25
    return {"cagr": eq ** (1 / yrs) - 1, "mdd": mdd, "avg_w": wsum / n, "changes_per_year": changes / yrs, "from": str(first), "to": str(last)}


def revenue_index(path):
    """{(market, code): [(available_date, avg3_yoy)]}，依可用日排序。"""
    by = defaultdict(dict)
    with gzip.open(path, "rt", newline="") as f:
        for r in csv.DictReader(f):
            try:
                yoy = float(r["yoy_pct"])
            except ValueError:
                continue
            m = "twse" if r["market"] == "sii" else "tpex"
            by[(m, r["code"])][r["month"]] = yoy
    out = {}
    for key, months in by.items():
        ms = sorted(months)
        rows = []
        for j, mo in enumerate(ms):
            y, mm = int(mo[:4]), int(mo[5:])
            prev3 = [f"{y if mm - k > 0 else y - 1}-{(mm - k - 1) % 12 + 1:02d}" for k in range(3)]
            if all(p in months for p in prev3):
                avail = D(y + (mm == 12), mm % 12 + 1, 11)
                rows.append((avail, sum(months[p] for p in prev3) / 3))
        out[key] = rows
    return out


def main(price_folder, revenue_path, score_csv, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    mdates, mma, taiex = macro(score_csv)
    rules = weight_rules(mdates, mma)
    series, stats = load(price_folder)
    rev = revenue_index(revenue_path)
    cal = sorted({d for rows in series.values() for d, *_ in rows})
    eval_days = set(cal[::5])
    day_rets = defaultdict(list)   # 等權組合：合格股票隔天報酬
    recs = []  # (date, market, code, tech, comp, ex5..., f5, f10, f20, f60, dd20, dd60)
    for (market, code), rows in series.items():
        if len(rows) < 70:
            continue
        dates, close, adj, score, tech, rsi, val20 = signals(rows)
        n = len(rows)
        rv = rev.get((market, code), []); rv_dates = [x[0] for x in rv]
        for i in range(65, n - 1):
            d = dates[i]
            ok = close[i] >= 10 and val20[i] >= 1e7 and not math.isnan(score[i]) and not math.isnan(tech[i])
            if not ok:
                continue
            day_rets[dates[i + 1]].append(adj[i + 1] / adj[i] - 1)
            if d not in eval_days or d > cal[-1] - dt.timedelta(days=95):
                continue
            t = "強" if tech[i] == 0 and score[i] >= 3 else "弱" if tech[i] == 1 else "中"
            j = bisect_right(rv_dates, d) - 1
            comp = None
            if j >= 0 and (d - rv[j][0]).days <= 75:
                y3 = rv[j][1]; comp = "成長" if y3 > 10 else "衰退" if y3 < -10 else "持平"
            fw = [adj[min(i + h, n - 1)] / adj[i] - 1 for h in (5, 10, 20, 60)]
            dd20 = adj[i + 1:min(i + 21, n)].min() / adj[i] - 1
            dd60 = adj[i + 1:min(i + 61, n)].min() / adj[i] - 1
            recs.append((d, market, code, t, comp, *fw, dd20, dd60))
    # ---------- 一、大盤層
    lines = []; p = lines.append; res = {"portfolio": {}, "entry": {}}
    p(f"股價 {cal[0]}～{cal[-1]}；股票 {len(series)} 檔；評估樣本 {len(recs):,} 筆；有營收分組 {sum(1 for r in recs if r[4]):,} 筆")
    eq_dates = sorted(day_rets); eq_rets = [float(np.mean(day_rets[d])) for d in eq_dates]
    mi = {d: i for i, d in enumerate(mdates)}
    def align(target_dates):
        # 每個目標日用「前一個總經日」的持股
        idx = [bisect_right(mdates, d) - 1 for d in target_dates]
        return idx
    tx_rets = [None] + [taiex[i] / taiex[i - 1] - 1 for i in range(1, len(taiex))]
    names = {"A": "A 固定 65%", "L5": "L5 綠燈 70%／橘燈 60%", "L10": "L10 綠燈 75%／橘燈 55%", "L15": "L15 綠燈 80%／橘燈 50%",
             "D10": "D10 分數 60 日內升 5 分 → 75%、降 5 分 → 55%", "R10": "R10 反向對照：綠燈 55%／橘燈 75%"}
    for asset in ("加權指數（價格指數）", "全部合格股票等權（含除權息）"):
        for pname, lo, hi in (("全期", None, None), ("2006–2015", None, D(2015, 12, 31)), ("2016–2026", D(2016, 1, 1), None)):
            p(f"\n## 大盤層｜{asset}｜{pname}")
            p("規則 | 年化 | 最大跌幅 | 平均持股 | 每年調整次數")
            for k in names:
                if asset.startswith("加權"):
                    r = simulate(mdates, tx_rets, rules[k], lo, hi)
                else:
                    idx = align(eq_dates)
                    w = [rules[k][j] if j >= 0 else 0.65 for j in idx]
                    # simulate 用「前一天」的持股：把 w 往後移一格（w[i-1] 對應 eq_dates[i]）
                    r = simulate(eq_dates, [None] + eq_rets[1:], w, lo, hi)
                res["portfolio"][f"{asset}|{pname}|{k}"] = r
                p(f"{names[k]} | {r['cagr']*100:+.2f}% | {r['mdd']*100:.1f}% | {r['avg_w']*100:.1f}% | {r['changes_per_year']:.1f}")
    # 總經分數分布（說明加減會發生多少天）
    green = sum(v >= 70 for v in mma); orange = sum(v < 55 for v in mma)
    p(f"\n總經 20 日平均：≥70 有 {green} 天、<55 有 {orange} 天、共 {len(mma)} 天（{mdates[0]}～{mdates[-1]}）")
    # ---------- 二、個股層
    by_day = defaultdict(list)
    for r in recs:
        by_day[r[0]].append(r)
    means = {h: {d: np.mean([x[5 + h] for x in v]) for d, v in by_day.items()} for h in range(4)}
    for pname, pf in (("全期", lambda r: True), ("2006–2015", lambda r: r[0] <= D(2015, 12, 31)), ("2016–2026", lambda r: r[0] >= D(2016, 1, 1))):
        p(f"\n## 個股層｜技術 × 營收｜{pname}")
        p("技術 | 營收 | 筆數 | 5日超額 | 10日超額 | 20日超額 | 20日勝率 | 60日超額 | 20日內跌≥20% | 60日內跌≥30%")
        for t in ("強", "中", "弱"):
            for c in ("成長", "持平", "衰退", "全部"):
                xs = [r for r in recs if pf(r) and r[3] == t and (r[4] == c if c != "全部" else True)]
                if not xs:
                    continue
                ex = [[r[5 + h] - means[h][r[0]] for r in xs] for h in range(4)]
                row = {"n": len(xs), "ex5": float(np.mean(ex[0])), "ex10": float(np.mean(ex[1])), "ex20": float(np.mean(ex[2])), "win20": float(np.mean([e > 0 for e in ex[2]])),
                       "ex60": float(np.mean(ex[3])), "crash20": float(np.mean([r[9] <= -0.2 for r in xs])), "crash60": float(np.mean([r[10] <= -0.3 for r in xs]))}
                res["entry"][f"{pname}|{t}|{c}"] = row
                p(f"{t} | {c} | {row['n']:,} | {row['ex5']*100:+.2f}% | {row['ex10']*100:+.2f}% | {row['ex20']*100:+.2f}% | {row['win20']*100:.1f}% | "
                  f"{row['ex60']*100:+.2f}% | {row['crash20']*100:.1f}% | {row['crash60']*100:.1f}%")
        xs = [r for r in recs if pf(r)]
        p(f"（同期全部：20日內跌≥20% {np.mean([r[9] <= -0.2 for r in xs])*100:.1f}%、60日內跌≥30% {np.mean([r[10] <= -0.3 for r in xs])*100:.1f}%）")
    p("\n交易成本參考：一買一賣約 0.585%；短線 5～20 日的超額要扣掉這個才算賺。")
    (out / "output.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(res, ensure_ascii=False, indent=1))
    print("\n".join(lines))


if __name__ == "__main__":
    main(*sys.argv[1:])
