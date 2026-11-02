#!/usr/bin/env python3
"""第 38 輪：擁有者的估值方法回測。擁有者 2026-11-03 06:48「第二條可以」。規則在看結果前寫定（2026-11-03 07:30）。

用法：python3 -I tools/round38_owner_valuation_backtest.py <股價資料夾> <eps.csv.gz> <revenue.csv.gz> <taiex_usd.csv> <輸出資料夾>

擁有者的做法（2026-11-03 06:45 原話摘要）：用第一季 EPS 算上成長率估整年獲利；用股災時的歷史本益比上下區間評估；最後用均線看進出場。
網站現在（Gate 7）：今年 EPS＝已公告累計＋剩下各季照過去 5 年同季、乘「今年累計營收年增倍率」（限制 0.70～1.30）；本益比＝近 5 年每天本益比 P20／中位／P80。

一、資料（與第 37 輪相同來源）
- EPS：公開資訊觀測站 t163sb04，2013 起各季「當年累計」基本 EPS（現在版本，含事後更正）。單季＝累計相減。
- 何時「知道」：法定期限 Q1 5/15、Q2 8/14、Q3 11/14、年報隔年 3/31，期限之後才算已知（金融業期限較晚未另調）。
- 月營收：公開資訊觀測站彙總（gate-probe revenue），第 m 月營收在 m+1 月 10 日之後才算已知；去年同月用同列 revenue_last_year。
- 股價：tools/stock_signal_backtest.load（收盤、還原日報酬、成交金額）。均線用還原報酬累積的價格算，避免除權息跳空。
- 加權指數：taiex_usd.csv 的 taiex_close。
- 本益比（每天）＝收盤 ÷ 當天已知的近四季 EPS（近四季 ≤ 0 不算本益比）。

二、估值方法（每種都產生 Bear／Base／Bull 三個情境價）
EPS（今年估計）：
- S_cap（網站現行）：今年已公告累計＋剩下各季＝過去最多 5 個完整年度同季 EPS × 營收倍率（0.70～1.30）；至少 3 年樣本；三情境＝樣本 P20／中位／P80。
- S_uncap：同上，但營收倍率不設上下限（擁有者：成長率不設上限）。
- G（擁有者）：今年已公告到第 s 季時＝去年全年 EPS × 今年累計 ÷ 去年同期累計（去年全年、去年同期、今年累計都要 > 0）；
  今年一季都還沒公告：去年全年已公告就用去年全年；還沒公告（1～3 月）就用前年全年 × 去年前三季 ÷ 前年前三季。三情境都用同一個 EPS。
- R（另一種讀法）：今年累計 × 4 ÷ s；還沒公告就用去年全年（1～3 月用去年前三季 × 4 ÷ 3）。
本益比區間：
- PB5（網站現行）：評估日前近 1250 個交易日的每天本益比，至少 250 筆，P20／中位／P80。
- CRASH（擁有者「股災時的本益比」）：股災日＝加權指數 ≤ 前 250 個交易日最高收盤的 85%；評估日以前所有股災日的本益比，至少 20 筆，P20／中位／P80。
  （2014 年以後的股災日：2015-08～2016-03、2016-05、2018-10／12、2019-01、2020-03～04、2022-05～2023-03、2024-08、2025-04～05、2026-07。）
情境價：S 系列＝EPS P20 × PE P20、中位 × 中位、P80 × P80（與網站相同）；G、R＝EPS × PE P20／中位／P80。
評級（與網站相同）：現價 ≤ Bear → A；≤ Base → B+；≤ Bull → B；以上 → C。
均線：收盤同時低於 20 日線與 60 日線 → 降一級（C 再降為 D）。另列不扣均線的原始評級。
比較的組合：CUR＝S_cap×PB5（現行）、S_uncap×PB5、G×PB5、G×CRASH（擁有者完整做法）、R×CRASH、S_cap×CRASH。

三、評估（同第 37 輪的合格條件）
- 2019-01 起每 20 個交易日一次（本益比 5 年歷史從 2014 起才有）；收盤 ≥ 10 元、前 20 日平均成交金額 ≥ 1,000 萬元。
- 主比較只用「六種組合都算得出評級」的股票日（同一批股票比方法）；另列各組合的可評比例。
- 之後 60、120 個交易日還原報酬；超額＝減同一天這批股票的平均（等權）。另看 120 日內最低點跌幅 ≥ 30% 的比例。
- 誤差：先算每個評估日的組內平均，再對評估日平均；標準誤乘 √(期間÷20) 粗估重疊。
- 分 2019-01～2021-12、2022-01～最後。
- 「便宜組」＝A＋B+；「貴組」＝C（不扣均線）。主指標＝便宜組減貴組的 120 日超額差。

四、事先寫定的判斷
1. 成長率不設上限／擁有者 EPS：某組合（S_uncap×PB5 或 G×PB5）兩段都滿足「便宜減貴的 120 日超額差 ≥ 現行 + 1 個百分點」且「便宜組跌 ≥30% 比例 ≤ 現行便宜組 + 2 個百分點」→ 支持換掉現行 EPS 算法；否則維持。
2. 股災本益比：G×CRASH 對 G×PB5 用同一標準 → 支持改用股災區間；否則維持 5 年區間。
3. 估值分歧未評的股票（近四季 EPS 與 7 年中位數差 > 2 倍，同第 37 輪定義）：在判斷 1、2 選出的組合下（都不通過就用現行），
   這批股票的便宜組兩段都「120 日超額 ≥ 0」且「跌 ≥30% 比例 ≤ 全部合格股票 + 2 個百分點」→ 有證據可以照估值評級，不必一律未評；否則維持未評。
4. 均線：D 組（低於兩條均線且原本就貴）與扣均線前同評級相比，60 日超額兩段都較差 → 支持現行均線扣級；否則列為待查。
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

D = dt.date
DEADLINE = {1: (5, 15), 2: (8, 14), 3: (11, 14)}
GRADES = ["A", "B+", "B", "C", "D"]
COMBOS = [("CUR", "S_cap", "PB5"), ("S_uncap_PB5", "S_uncap", "PB5"), ("G_PB5", "G", "PB5"), ("G_CRASH", "G", "CRASH"), ("R_CRASH", "R", "CRASH"), ("Scap_CRASH", "S_cap", "CRASH")]


def known_on(year, season):
    if season == 4:
        return D(year + 1, 3, 31)
    m, d = DEADLINE[season]
    return D(year, m, d)


def load_eps(path):
    ytd = defaultdict(dict)
    with gzip.open(path, "rt", newline="") as f:
        for r in csv.DictReader(f):
            try:
                ytd[r["code"]][(int(r["roc_year"]) + 1911, int(r["season"]))] = float(r["eps_ytd"])
            except ValueError:
                pass
    return ytd


def load_revenue(path):
    rev = defaultdict(dict)
    with gzip.open(path, "rt", newline="") as f:
        for r in csv.DictReader(f):
            try:
                y, m = int(r["month"][:4]), int(r["month"][5:7])
                rev[r["code"]][(y, m)] = (float(r["revenue"]), float(r["revenue_last_year"]))
            except (ValueError, KeyError):
                pass
    return rev


def rev_known(y, m):
    return D(y + (m == 12), m % 12 + 1, 10)


def pct(values, p):
    return float(np.percentile(values, p * 100))


def grade_of(price, bear, base, bull):
    if not (0 < bear <= base <= bull):
        return None
    return "A" if price <= bear else "B+" if price <= base else "B" if price <= bull else "C"


def down(g):
    return GRADES[min(GRADES.index(g) + 1, len(GRADES) - 1)]


def eps_estimates(q, rev, day):
    """回傳 {方法: (p20, med, p80)}；q＝{(年,季): 累計}，只用 day 以前已知的。"""
    known = {k: v for k, v in q.items() if known_on(*k) < day}
    y = day.year
    s = max([k[1] for k in known if k[0] == y], default=0)
    out = {}
    fy = {yr: known[(yr, 4)] for (yr, ss) in known if ss == 4}
    # 單季
    single = {}
    for (yr, ss), v in known.items():
        prev = 0.0 if ss == 1 else known.get((yr, ss - 1))
        if prev is not None:
            single[(yr, ss)] = v - prev
    actual_ytd = known.get((y, s), 0.0) if s else 0.0
    complete = [yr for yr in sorted(fy) if yr < y and all((yr, qq) in single for qq in (1, 2, 3, 4))][-5:]
    months = [m for m in range(1, 13) if (y, m) in rev and rev_known(y, m) < day]
    mult_raw = 1.0
    if months:
        mx = max(months)
        cur = sum(rev[(y, m)][0] for m in range(1, mx + 1) if (y, m) in rev)
        prior = sum(rev[(y, m)][1] for m in range(1, mx + 1) if (y, m) in rev)
        if prior > 0:
            mult_raw = cur / prior
    remaining = [qq for qq in (1, 2, 3, 4) if qq > s]
    for name, mult in (("S_cap", max(0.7, min(1.3, mult_raw))), ("S_uncap", mult_raw)):
        samples = [actual_ytd + sum(single[(yr, qq)] * mult for qq in remaining) for yr in complete]
        if len(samples) >= 3:
            out[name] = (pct(samples, .2), pct(samples, .5), pct(samples, .8))
    # G：去年全年 × 今年累計成長
    g = None
    if s >= 1:
        last, base_ytd = fy.get(y - 1), known.get((y - 1, s))
        if last and base_ytd and last > 0 and base_ytd > 0 and actual_ytd > 0:
            g = last * actual_ytd / base_ytd
    elif (y - 1) in fy:
        g = fy[y - 1]
    else:
        a, b, c = fy.get(y - 2), known.get((y - 1, 3)), known.get((y - 2, 3))
        if a and b and c and a > 0 and c > 0 and b > 0:
            g = a * b / c
    if g and g > 0:
        out["G"] = (g, g, g)
    r = None
    if s >= 1:
        r = actual_ytd * 4 / s
    elif (y - 1) in fy:
        r = fy[y - 1]
    elif (y - 1, 3) in known:
        r = known[(y - 1, 3)] * 4 / 3
    if r and r > 0:
        out["R"] = (r, r, r)
    return out, fy


def ttm_events(q):
    ev = []
    for (y, s), v in q.items():
        if s == 4:
            ttm = v
        elif (y - 1, 4) in q and (y - 1, s) in q:
            ttm = v + q[(y - 1, 4)] - q[(y - 1, s)]
        else:
            continue
        ev.append((known_on(y, s), ttm))
    return sorted(ev)


def main(price_folder, eps_path, rev_path, taiex_path, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    series, stats = load(price_folder)
    ytd = load_eps(eps_path)
    revenue = load_revenue(rev_path)
    tx = [(D.fromisoformat(r["date"]), float(r["taiex_close"])) for r in csv.DictReader(open(taiex_path)) if r["taiex_close"]]
    crash = {}
    for i, (d, c) in enumerate(tx):
        crash[d] = c <= 0.85 * max(x for _, x in tx[max(0, i - 250):i + 1])
    cal = sorted({d for rows in series.values() for d, *_ in rows})
    evals = [d for d in cal[::20] if d >= D(2019, 1, 1)]
    eval_set = set(evals)
    records = []
    for (market, code), rows in series.items():
        q = ytd.get(code)
        if not q:
            continue
        ev = ttm_events(q)
        if not ev:
            continue
        rev = revenue.get(code, {})
        n = len(rows)
        dates = [r[0] for r in rows]
        close = np.array([r[1] for r in rows], dtype=float)
        rets = np.array([r[2] if r[2] is not None else 0.0 for r in rows], dtype=float)
        value = np.array([r[3] for r in rows], dtype=float)
        adj = np.cumprod(1 + rets)
        pe = np.full(n, np.nan)
        ttm_now = np.full(n, np.nan)
        j = -1
        for i, d in enumerate(dates):
            while j + 1 < len(ev) and ev[j + 1][0] < d:
                j += 1
            if j >= 0:
                ttm_now[i] = ev[j][1]
                if ev[j][1] > 0 and close[i] > 0:
                    pe[i] = close[i] / ev[j][1]
        crash_mask = np.array([crash.get(d, False) for d in dates])
        for i, d in enumerate(dates):
            if d not in eval_set or i < 60 or i + 60 >= n:
                continue
            if close[i] < 10 or value[i - 20:i].mean() < 1e7 or not (ttm_now[i] > 0):
                continue
            window = pe[max(0, i - 1250):i + 1]
            window = window[~np.isnan(window)]
            bands = {}
            if len(window) >= 250:
                bands["PB5"] = (pct(window, .2), pct(window, .5), pct(window, .8))
            cpe = pe[:i + 1][crash_mask[:i + 1]]
            cpe = cpe[~np.isnan(cpe)]
            if len(cpe) >= 20:
                bands["CRASH"] = (pct(cpe, .2), pct(cpe, .5), pct(cpe, .8))
            eps, fy = eps_estimates(q, rev, d)
            years = sorted(fy)[-7:]
            med7 = statistics.median(fy[y] for y in years) if len(years) >= 5 else None
            divergent = None
            if med7 and med7 > 0:
                divergent = "above" if ttm_now[i] / med7 > 2 else "below" if med7 / ttm_now[i] > 2 else "no"
            ma20, ma60 = adj[i - 19:i + 1].mean(), adj[i - 59:i + 1].mean()
            weak = adj[i] < ma20 and adj[i] < ma60
            path = adj[i + 1:i + 121] / adj[i]
            rec = {"date": d.isoformat(), "code": code, "price": close[i], "ttm": round(float(ttm_now[i]), 3), "divergent": divergent, "weak": weak,
                   "r60": float(path[59] - 1), "r120": float(path[119] - 1) if len(path) >= 120 else None, "low120": float(path.min() - 1)}
            for name, e_key, b_key in COMBOS:
                g = None
                if e_key in eps and b_key in bands:
                    e, b = eps[e_key], bands[b_key]
                    g = grade_of(close[i], e[0] * b[0], e[1] * b[1], e[2] * b[2])
                rec[name] = g
                rec[name + "_ma"] = (down(g) if weak else g) if g else None
            records.append(rec)
    # 主比較：六種都算得出評級
    common = [r for r in records if all(r[c[0]] for c in COMBOS)]
    by_date = defaultdict(list)
    for r in common:
        by_date[r["date"]].append(r)
    for rows in by_date.values():
        m60 = sum(r["r60"] for r in rows) / len(rows)
        r120 = [r["r120"] for r in rows if r["r120"] is not None]
        m120 = sum(r120) / len(r120) if r120 else None
        for r in rows:
            r["x60"] = r["r60"] - m60
            r["x120"] = r["r120"] - m120 if r["r120"] is not None and m120 is not None else None

    def summary(rows):
        o = {"obs": len(rows), "stocks": len({r["code"] for r in rows})}
        for key, h in (("x60", 60), ("x120", 120)):
            per_day = defaultdict(list)
            for r in rows:
                if r.get(key) is not None:
                    per_day[r["date"]].append(r[key])
            means = [sum(v) / len(v) for v in per_day.values()]
            o[f"{key}%"] = round(100 * sum(means) / len(means), 2) if means else None
            o[f"{key}_se%"] = round(100 * statistics.stdev(means) / math.sqrt(len(means)) * math.sqrt(h / 20), 2) if len(means) > 2 else None
        lows = [r["low120"] for r in rows]
        o["drop30%"] = round(100 * sum(v <= -0.30 for v in lows) / len(lows), 2) if lows else None
        return o

    def spread(rows, key, cheap, dear):
        per_day = defaultdict(lambda: ([], []))
        for r in rows:
            if r.get("x120") is None:
                continue
            if r[key] in cheap:
                per_day[r["date"]][0].append(r["x120"])
            elif r[key] in dear:
                per_day[r["date"]][1].append(r["x120"])
        diffs = [sum(a) / len(a) - sum(b) / len(b) for a, b in per_day.values() if a and b]
        if len(diffs) < 3:
            return None, None, len(diffs)
        mean = sum(diffs) / len(diffs)
        se = statistics.stdev(diffs) / math.sqrt(len(diffs)) * math.sqrt(120 / 20)
        return round(100 * mean, 2), round(100 * se, 2), len(diffs)

    periods = [("2019-01~2021-12", "2019-01-01", "2021-12-31"), ("2022-01~end", "2022-01-01", "2100-12-31"), ("all", "1900-01-01", "2100-12-31")]
    result = {"evaluations": len(evals), "records": len(records), "common": len(common), "price_stats": stats,
              "coverage%": {c[0]: round(100 * sum(1 for r in records if r[c[0]]) / len(records), 1) for c in COMBOS}, "periods": {}}
    for pname, a, b in periods:
        rows = [r for r in common if a <= r["date"] <= b]
        pr = {"all": summary(rows), "combos": {}}
        for name, *_ in COMBOS:
            cheap_rows = [r for r in rows if r[name] in ("A", "B+")]
            sp = spread(rows, name, ("A", "B+"), ("C",))
            pr["combos"][name] = {"grades": {g: summary([r for r in rows if r[name] == g]) for g in GRADES[:4]},
                                  "ma_grades": {g: summary([r for r in rows if r[name + "_ma"] == g]) for g in GRADES},
                                  "cheap": summary(cheap_rows), "cheap_minus_C_x120": sp,
                                  "share%": {g: round(100 * sum(1 for r in rows if r[name] == g) / max(1, len(rows)), 1) for g in GRADES[:4]}}
            # 均線：原本 C 的股票，弱勢（降為 D）對不弱勢
            pr["combos"][name]["C_weak_vs_not"] = {"weak(D)": summary([r for r in rows if r[name] == "C" and r["weak"]]), "not_weak": summary([r for r in rows if r[name] == "C" and not r["weak"]])}
            div = [r for r in rows if r["divergent"] in ("above", "below")]
            pr["combos"][name]["divergent"] = {"all": summary(div), "cheap": summary([r for r in div if r[name] in ("A", "B+")]),
                                               "C": summary([r for r in div if r[name] == "C"]),
                                               "above_cheap": summary([r for r in div if r["divergent"] == "above" and r[name] in ("A", "B+")]),
                                               "above_C": summary([r for r in div if r["divergent"] == "above" and r[name] == "C"])}
        result["periods"][pname] = pr
    with open(out / "summary.json", "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=1)
    keys = ["date", "code", "price", "ttm", "divergent", "weak", "r60", "r120", "low120"] + [c[0] for c in COMBOS] + [c[0] + "_ma" for c in COMBOS]
    with gzip.open(out / "records.csv.gz", "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=keys, extrasaction="ignore"); w.writeheader(); w.writerows(records)
    print(json.dumps({k: result[k] for k in ("evaluations", "records", "common", "coverage%")}, ensure_ascii=False))
    for pname, pr in result["periods"].items():
        print("==", pname, "all:", pr["all"])
        for name, c in pr["combos"].items():
            print(f"  {name:12s} share {c['share%']} cheap-C x120 {c['cheap_minus_C_x120']} cheap {c['cheap']['x120%']}/{c['cheap']['drop30%']} C {c['grades']['C']['x120%']}/{c['grades']['C']['drop30%']}"
                  f" | div cheap {c['divergent']['cheap']['obs']} {c['divergent']['cheap']['x120%']}/{c['divergent']['cheap']['drop30%']} div C {c['divergent']['C']['x120%']}/{c['divergent']['C']['drop30%']}"
                  f" | C weak x60 {c['C_weak_vs_not']['weak(D)']['x60%']} vs {c['C_weak_vs_not']['not_weak']['x60%']}")
    latest = max(r["date"] for r in records)
    print("latest", latest, [(r["code"], r["divergent"], {c[0]: r[c[0]] for c in COMBOS}) for r in records if r["date"] == latest and r["code"] in ("2330", "2404", "8299", "5289", "5009")])


if __name__ == "__main__":
    main(*sys.argv[1:6])
