#!/usr/bin/env python3
"""第 31 輪：重建 2006–2026 每日「台股總經與市場位階」分數（照網站 worker/macro-scoring.js 的規則），
再回測「只在極端時調整持股」的做法。規則全部寫在這裡、看結果之前寫定。

用法：python3 -I tools/macro_score_history.py <資料集 CSV> <國發會 ZIP> <輸出資料夾> [台股每日 CSV] [央行 CSV]

一、計分（與網站相同）
- 台股模型＝美國「物價」20、「成長就業」25、「利率信用流動性」25 ＋ 台股「本土」30；
  每個維度＝該維度有值訊號的平均；總分＝有值維度的加權平均（權重重新歸一），四捨五入成整數。
- 每個訊號的分段門檻逐字照抄 macro-scoring.js（見 SCORERS）。
- 網站的「資料未齊（灰燈）」條件也照算：覆蓋率≥60 且四個維度覆蓋率都≥0.5，否則記為未齊（仍保留分數）。

二、沒有未來資料（每個值從「公布日」起才可用）
- 核心 CPI：觀測月 M → M+1 月 20 日；核心 PCE：M+2 月 1 日；非農、失業率、Sahm：M+1 月 10 日；
  零售銷售：M+1 月 20 日；初領失業金 4 週均：週六觀測 → +5 日（週四）；FRED 日資料：+1 日；
  國發會景氣對策信號：M+2 月 1 日；央行 M1B、M2：M+2 月 1 日；台股當日資料：當日收盤後。
- 過期：月資料公布後 45 日、週資料 14 日、日資料 7 日內沒有新值就不用（不補值）。
- FRED 是「現在版本」（含事後修訂），不是當時的初值；2013、2025 年政府關門造成的延後公布也沒有模擬。結果需註明。

三、持股（收盤算分，隔天起生效；價格指數不含股利；現金報酬 0；每調動 1 成持股扣 0.02%）
- A 固定 65%（擁有者基準）。
- B1 當天分數 < 40（網站紅燈）→ 25%，否則 65%。
- B2 20 日平均分數 < 40 → 25%，否則 65%。
- B3 20 日平均 < 40 進入 25%，回到 ≥ 45 才恢復 65%（避免來回）。
- B4 20 日平均低於「到當天為止」歷史的第 10 百分位（至少 3 年資料）→ 25%，否則 65%。
- C  B3 ＋ 20 日平均 ≥ 70（網站綠燈）→ 85%。（擁有者只說基準與下限；上限是附加對照。）
"""
import csv
import datetime as dt
import io
import json
import math
import sys
import zipfile
from bisect import bisect_right
from pathlib import Path

D = dt.date


def day(s):
    return D.fromisoformat(s[:10])


def month_add(d, n, dd=1):
    y, m = d.year + (d.month - 1 + n) // 12, (d.month - 1 + n) % 12 + 1
    return D(y, m, dd)


# ---------- 計分門檻（逐字照抄 worker/macro-scoring.js） ----------
def lower_is_better(v, levels):
    for mx, s in levels:
        if v <= mx:
            return s
    return levels[-1][1]


def momentum(v):
    return 20 if v <= -2 else 40 if v <= -0.5 else 55 if v < 0.5 else 75 if v <= 2 else 65


def ndc(v):
    return 75 if 23 <= v <= 31 else 45 if v >= 32 else 60 if v >= 17 else 45 if v >= 9 else 25


def breadth(v):
    return 25 if v < 30 else 45 if v < 40 else 60 if v <= 60 else 75 if v <= 70 else 65


SCORERS = {
    "core_cpi_3m": ("inflation", lambda v: lower_is_better(v, [(2.3, 85), (3, 70), (4, 45), (math.inf, 20)])),
    "core_pce_3m": ("inflation", lambda v: lower_is_better(v, [(2.3, 85), (3, 70), (4, 45), (math.inf, 20)])),
    "sahm": ("growth", lambda v: 85 if v < 0.2 else 70 if v < 0.35 else 50 if v < 0.5 else 15),
    "nfp": ("growth", lambda v: 75 if v >= 150 else 65 if v >= 100 else 50 if v > 0 else 25),
    "unrate": ("growth", lambda v: 75 if v <= 4.2 else 55 if v <= 4.8 else 25),
    "claims4w": ("growth", lambda v: 75 if v < 230000 else 55 if v <= 260000 else 25),
    "retail_mom": ("growth", lambda v: 75 if v >= 0.3 else 60 if v >= 0 else 30),
    "real10y": ("rates", lambda v: 80 if v < 1.5 else 65 if v < 2 else 45 if v <= 2.5 else 25),
    "hy": ("rates", lambda v: 80 if v < 3 else 65 if v < 4 else 45 if v < 5 else 20),
    "t10y2y": ("rates", lambda v: 40 if v < 0 else 60 if v < 0.5 else 65 if v < 1.5 else 55),
    "sofr_iorb_bps": ("rates", lambda v: 75 if v <= 0 else 60 if v <= 5 else 40 if v <= 10 else 20),
    "twse_breadth": ("local", breadth),
    "tpex_breadth": ("local", breadth),
    "taiex_1d": ("local", momentum),
    "elec_1d": ("local", momentum),
    "ndc_signal": ("local", ndc),
    "m1b_m2": ("local", lambda v: 65 if v > 0 else 45),
    "daytrade": ("local", lambda v: 60 if v < 30 else 70 if v <= 38 else 50 if v <= 44 else 25),
}
DIMS = {"inflation": (20, 2), "growth": (25, 5), "rates": (25, 4), "local": (30, 7)}
STALE = {"monthly": 45, "weekly": 14, "daily": 7}


def read_dataset(path):
    cols = {}
    with open(path) as f:
        for r in csv.DictReader(f):
            for k, v in r.items():
                if k != "date" and v not in ("", "."):
                    cols.setdefault(k, {})[r["date"]] = float(v)
    return cols


def monthly_series(col):
    return {day(k).replace(day=1): v for k, v in col.items()}


class Known:
    """一個訊號：(公布日, 觀測日, 值) 的序列；查詢某天時取公布日 ≤ 該天的最新一筆，過期就是 None。"""

    def __init__(self, rows, freq):
        rows = sorted(rows)
        self.avail = [r[0] for r in rows]
        self.rows = rows
        self.max_age = STALE[freq]

    def at(self, d):
        i = bisect_right(self.avail, d) - 1
        if i < 0:
            return None
        a, obs, v = self.rows[i]
        return None if (d - a).days > self.max_age else (v, obs)


def build_signals(ds, ndc_rows, tw_daily, cbc):
    s = {}
    cpi, pce = monthly_series(ds.get("cpilfesl", {})), monthly_series(ds.get("pcepilfe", {}))

    def ann3(series, lag_months, lag_day):
        out = []
        for m, v in series.items():
            p = series.get(month_add(m, -3))
            if p:
                out.append((month_add(m, lag_months, lag_day), m, ((v / p) ** 4 - 1) * 100))
        return out
    s["core_cpi_3m"] = Known(ann3(cpi, 1, 20), "monthly")
    s["core_pce_3m"] = Known(ann3(pce, 2, 1), "monthly")
    pay = monthly_series(ds.get("payems", {}))
    s["nfp"] = Known([(month_add(m, 1, 10), m, v - pay[month_add(m, -1)]) for m, v in pay.items() if month_add(m, -1) in pay], "monthly")
    s["unrate"] = Known([(month_add(m, 1, 10), m, v) for m, v in monthly_series(ds.get("unrate", {})).items()], "monthly")
    s["sahm"] = Known([(month_add(m, 1, 10), m, v) for m, v in monthly_series(ds.get("sahmrealtime", {})).items()], "monthly")
    rs = monthly_series(ds.get("rsafs", {}))
    s["retail_mom"] = Known([(month_add(m, 1, 20), m, (v / rs[month_add(m, -1)] - 1) * 100) for m, v in rs.items() if month_add(m, -1) in rs], "monthly")
    s["claims4w"] = Known([(day(k) + dt.timedelta(days=5), day(k), v) for k, v in ds.get("ic4wsa", {}).items()], "weekly")

    def daily(col, f=lambda v: v):
        return Known([(day(k) + dt.timedelta(days=1), day(k), f(v)) for k, v in col.items()], "daily")
    s["real10y"] = daily(ds.get("dfii10", {}))
    s["hy"] = daily(ds.get("bamlh0a0hym2", {}))
    s["t10y2y"] = daily(ds.get("t10y2y", {}))
    sofr, iorb, ioer = ds.get("sofr", {}), ds.get("iorb", {}), ds.get("ioer", {})
    spread = {k: (v - (iorb.get(k) if k in iorb else ioer.get(k))) * 100 for k, v in sofr.items() if k in iorb or k in ioer}
    s["sofr_iorb_bps"] = daily(spread)
    s["ndc_signal"] = Known([(month_add(m, 2, 1), m, v) for m, v in ndc_rows.items()], "monthly")
    if cbc:
        s["m1b_m2"] = Known([(month_add(m, 2, 1), m, v) for m, v in cbc.items()], "monthly")
    tx = sorted((day(k), v) for k, v in ds.get("taiex_close", {}).items())
    s["taiex_1d"] = Known([(d1, d1, (v1 / v0 - 1) * 100) for (d0, v0), (d1, v1) in zip(tx, tx[1:])], "daily")
    for key in ("twse_breadth", "tpex_breadth", "elec_1d", "daytrade"):
        if tw_daily.get(key):
            s[key] = Known([(day(k), day(k), v) for k, v in tw_daily[key].items()], "daily")
    return s, tx


def read_ndc(zip_path):
    z = zipfile.ZipFile(zip_path)
    real = lambda i: i.filename if i.flag_bits & 0x800 else i.filename.encode("cp437").decode("utf8")
    info = next(i for i in z.infolist() if real(i) == "景氣指標與燈號.csv")
    text = z.read(info).decode("utf-8-sig")
    out = {}
    for r in csv.DictReader(io.StringIO(text)):
        v = r.get("景氣對策信號綜合分數", "").strip()
        if v and v != "-":
            k = r["Date"].strip()
            out[D(int(k[:4]), int(k[4:6]), 1)] = float(v)
    return out


def score_day(sig, d):
    dims = {k: [] for k in DIMS}
    used = {}
    for key, known in sig.items():
        got = known.at(d)
        if got is None:
            continue
        dim, f = SCORERS[key]
        sc = max(0, min(100, f(got[0])))
        dims[dim].append(sc)
        used[key] = round(got[0], 4)
    obs = {k: sum(v) / len(v) for k, v in dims.items() if v}
    wsum = sum(DIMS[k][0] for k in obs)
    if not wsum:
        return None
    raw = sum(obs[k] * DIMS[k][0] for k in obs) / wsum
    coverage = sum(DIMS[k][0] * min(1, len(dims[k]) / DIMS[k][1]) for k in DIMS)
    complete = coverage >= 60 and all(len(dims[k]) / DIMS[k][1] >= 0.5 for k in DIMS)
    return {"score": round(raw), "raw": raw, "coverage": round(coverage, 1), "complete": complete,
            "dims": {k: round(v, 1) for k, v in obs.items()}, "counts": {k: len(v) for k, v in dims.items()}, "values": used}


def pct(x):
    return f"{x * 100:+.2f}%"


def simulate(dates, rets, weights, cost=0.0002):
    eq, peak, mdd, w_prev, switches, turnover = 1.0, 1.0, 0.0, None, 0, 0.0
    for i in range(len(dates) - 1):
        w = weights[i]
        if w_prev is not None and abs(w - w_prev) > 1e-9:
            switches += 1
            turnover += abs(w - w_prev)
            eq *= 1 - cost * abs(w - w_prev) * 10
        eq *= 1 + w * rets[i + 1]
        peak = max(peak, eq)
        mdd = min(mdd, eq / peak - 1)
        w_prev = w
    years = (dates[-1] - dates[0]).days / 365.25
    return {"cagr": eq ** (1 / years) - 1, "mdd": mdd, "switches_per_year": switches / years, "final": eq,
            "avg_weight": sum(weights[:-1]) / (len(weights) - 1)}


def main(dataset, ndc_zip, out, tw_daily_csv=None, cbc_csv=None):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    ds = read_dataset(dataset)
    tw = {}
    if tw_daily_csv:
        with open(tw_daily_csv) as f:
            for r in csv.DictReader(f):
                for k, v in r.items():
                    if k != "date" and v not in ("", "."):
                        tw.setdefault(k, {})[r["date"]] = float(v)
    cbc = None
    if cbc_csv:
        with open(cbc_csv) as f:
            cbc = {day(r["date"]).replace(day=1): float(r["m1b_m2"]) for r in csv.DictReader(f) if r.get("m1b_m2")}
    sig, tx = build_signals(ds, read_ndc(ndc_zip), tw, cbc)
    rows = []
    for d, close in tx:
        if d < D(2006, 1, 1):
            continue
        r = score_day(sig, d)
        if r:
            rows.append((d, close, r))
    with open(out / "score_history.csv", "w", newline="") as f:
        w = csv.writer(f)
        keys = list(SCORERS)
        w.writerow(["date", "taiex", "score", "raw", "coverage", "complete", "inflation", "growth", "rates", "local"] + keys)
        for d, c, r in rows:
            w.writerow([d, c, r["score"], f"{r['raw']:.2f}", r["coverage"], int(r["complete"])] + [r["dims"].get(k, "") for k in DIMS] + [r["values"].get(k, "") for k in keys])
    dates = [d for d, _, _ in rows]
    closes = [c for _, c, _ in rows]
    rets = [0.0] + [closes[i] / closes[i - 1] - 1 for i in range(1, len(closes))]
    raw = [r["raw"] for _, _, r in rows]
    ma20 = [sum(raw[max(0, i - 19):i + 1]) / (i + 1 - max(0, i - 19)) for i in range(len(raw))]
    lines = []
    p = lambda s="": lines.append(s)
    p(f"資料：{dates[0]} ～ {dates[-1]}，{len(dates)} 個交易日")
    cover = {}
    for d, _, r in rows:
        y = d.year
        c = cover.setdefault(y, {"n": 0, "complete": 0, **{k: 0 for k in SCORERS}})
        c["n"] += 1
        c["complete"] += r["complete"]
        for k in r["values"]:
            c[k] += 1
    p("\n## 每年各訊號有值的比例（%）")
    p("年 | 資料齊 | " + " | ".join(SCORERS))
    for y, c in sorted(cover.items()):
        p(f"{y} | {c['complete'] * 100 // c['n']} | " + " | ".join(str(c[k] * 100 // c["n"]) for k in SCORERS))
    p("\n## 分數分布（當天分數）")
    bands = [("<40 紅", lambda v: v < 40), ("40–54 橘", lambda v: 40 <= v < 55), ("55–69 黃", lambda v: 55 <= v < 70), ("≥70 綠", lambda v: v >= 70)]
    for name, f in bands:
        idx = [i for i in range(len(rows)) if f(rows[i][2]["score"])]
        p(f"{name}: {len(idx)} 天（{len(idx) * 100 / len(rows):.1f}%）")
    p("\n## 之後 60 個交易日（當天分數 / 20 日平均分數）")
    for label, series in (("當天", [r["score"] for _, _, r in rows]), ("20日平均", ma20)):
        for name, f in bands:
            idx = [i for i in range(len(rows) - 60) if f(series[i])]
            if not idx:
                p(f"{label} {name}: 0 天")
                continue
            fwd = [closes[i + 60] / closes[i] - 1 for i in idx]
            dd = [min(closes[i + k] for k in range(1, 61)) / closes[i] - 1 for i in idx]
            p(f"{label} {name}: {len(idx)} 天｜之後60日平均 {pct(sum(fwd) / len(fwd))}｜60日內平均最大跌幅 {pct(sum(dd) / len(dd))}")
    allfwd = [closes[i + 60] / closes[i] - 1 for i in range(len(rows) - 60)]
    p(f"所有日子：之後60日平均 {pct(sum(allfwd) / len(allfwd))}")
    # 持股規則
    def b3(enter=40, exit_=45, high=None):
        out_w, state = [], 0.65
        for v in ma20:
            if state == 0.25 and v >= exit_:
                state = 0.65
            elif state != 0.25 and v < enter:
                state = 0.25
            if high is not None and state != 0.25:
                state = 0.85 if v >= high else 0.65
            out_w.append(state)
        return out_w
    pctl = []
    for i, v in enumerate(ma20):
        hist = sorted(ma20[:i + 1])
        enough = (dates[i] - dates[0]).days >= 3 * 365
        pctl.append(0.25 if enough and v < hist[int(0.1 * (len(hist) - 1))] else 0.65)
    rules = {
        "A 固定 65%": [0.65] * len(rows),
        "B1 當天 <40 → 25%": [0.25 if r["score"] < 40 else 0.65 for _, _, r in rows],
        "B2 20日均 <40 → 25%": [0.25 if v < 40 else 0.65 for v in ma20],
        "B3 20日均 <40 進、≥45 出": b3(),
        "B4 20日均 < 歷史第10百分位": pctl,
        "C B3 ＋ 20日均 ≥70 → 85%": b3(high=70),
        "（對照）一直 100%": [1.0] * len(rows),
    }
    p("\n## 持股規則（全期）")
    p("做法 | 年化 | 最大跌幅 | 平均持股 | 每年調整次數")
    results = {}
    for name, wts in rules.items():
        r = simulate(dates, rets, wts)
        results[name] = r
        p(f"{name} | {pct(r['cagr'])} | {pct(r['mdd'])} | {r['avg_weight'] * 100:.0f}% | {r['switches_per_year']:.1f}")
    for lo, hi in ((D(2006, 1, 1), D(2015, 12, 31)), (D(2016, 1, 1), D(2026, 12, 31))):
        idx = [i for i, d in enumerate(dates) if lo <= d <= hi]
        p(f"\n## 分段 {dates[idx[0]]} ～ {dates[idx[-1]]}")
        p("做法 | 年化 | 最大跌幅 | 每年調整次數")
        for name, wts in rules.items():
            r = simulate([dates[i] for i in idx], [rets[i] for i in idx], [wts[i] for i in idx])
            p(f"{name} | {pct(r['cagr'])} | {pct(r['mdd'])} | {r['switches_per_year']:.1f}")
    reduced = [(dates[i], ma20[i]) for i in range(len(rows)) if rules["B3 20日均 <40 進、≥45 出"][i] == 0.25]
    p("\n## B3 降到 25% 的期間")
    if reduced:
        start = prev = reduced[0][0]
        for d, _ in reduced[1:] + [(None, None)]:
            if d is None or (d - prev).days > 7:
                i0, i1 = dates.index(start), dates.index(prev)
                p(f"{start} ～ {prev}（{i1 - i0 + 1} 天）加權 {closes[i0]:.0f} → {closes[i1]:.0f}")
                start = d
            prev = d if d else prev
    else:
        p("（沒有）")
    (out / "output.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "summary.json").write_text(json.dumps({k: v for k, v in results.items()}, ensure_ascii=False, indent=1, default=str))
    print("\n".join(lines))


if __name__ == "__main__":
    main(*sys.argv[1:])
