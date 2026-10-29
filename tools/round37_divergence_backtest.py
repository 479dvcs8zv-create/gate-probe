#!/usr/bin/env python3
"""第 37 輪：估值分歧（2 倍規則）要不要多比「去年全年 EPS」。擁有者 2026-10-29 15:52「好」。規則在看結果前寫定（2026-10-29 16:20）。

用法：python3 -I tools/round37_divergence_backtest.py <股價資料夾> <eps.csv.gz> <輸出資料夾>

一、資料
- EPS：公開資訊觀測站綜合損益表彙總（t163sb04），2013 年起，各季為「當年累計」基本每股盈餘（現在版本，含事後更正）。
- 何時「知道」：一般行業法定期限 Q1 5/15、Q2 8/14、Q3 11/14、年報隔年 3/31；評估日在期限之後才算已知（金融業期限較晚，未另調，略偏樂觀）。
- 股價：與第 32～35 輪相同的還原報酬（tools/stock_signal_backtest.load）。

二、規則（網站 worker/valuation-divergence.js 只用得到的部分：歷史常態 EPS 與近四季 EPS；模型 EPS 與共識無歷史資料，不納入）
- 歷史常態 EPS＝已知完整年度最近 7 年中位數，至少 5 年。
- 近四季 EPS（TTM）＝最新已知季累計＋前一年全年－前一年同季累計；最新已知是第 4 季就用全年。
- 去年全年 EPS＝最近一個已知完整年度。
- 只看近四季與歷史常態都 > 0 的股票（網站對非正 EPS 不參與）。
- 現行：近四季與歷史常態相差 > 2 倍 → 分歧（未評）。
- 提議：現行分歧，而且近四季與去年全年也相差 > 2 倍（或去年全年 ≤ 0）才算分歧。
- 分組：A＝現行不分歧；B＝現行分歧、提議不分歧（「穩定成長／衰退超出歷史常態，但和去年接近」）；C＝兩者都分歧（突然暴增／暴跌）。

三、評估（同第 33～35 輪的合格條件）
- 2018-04 起每 20 個交易日一次；收盤 ≥ 10 元、前 20 日平均成交金額 ≥ 1,000 萬元。
- 之後 60、120 個交易日還原報酬；超額＝減同一天 A＋B＋C 全部合格股票平均（等權）。中途下市算到最後一日。
- 另看 120 日內最低點相對評估日的跌幅，與跌幅 ≥ 30% 的比例。
- 誤差：先算每個評估日的組內平均，再對評估日取平均；標準誤乘 √(期間÷20) 粗估重疊。
- 分 2018-04～2021-12、2022-01～最後。

四、事先寫定的判斷
- 若兩段都滿足：B 的 60、120 日平均超額不比 A 差超過 1 個百分點，且 B 跌 ≥30% 的比例不比 A 高超過 2 個百分點 → 支持提議（B 可以恢復評級）。
- 否則維持現行。另檢查 C 是否明顯比 A 差（提議保留的分歧是否仍抓到風險）。
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

sys.path.insert(0, str(Path(__file__).parent))
from stock_signal_backtest import load  # noqa: E402

D = dt.date
DEADLINE = {1: (5, 15), 2: (8, 14), 3: (11, 14)}


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


def eps_view(q, day):
    """回傳 (median7, ttm, last_year) 或 None。q＝{(年,季): 累計 EPS}。"""
    known = sorted(k for k in q if known_on(*k) < day)
    if not known:
        return None
    annual = {y: q[(y, 4)] for (y, s) in known if s == 4}
    years = sorted(annual)[-7:]
    if len(years) < 5:
        return None
    med = statistics.median(annual[y] for y in years)
    y, s = known[-1]
    if s == 4:
        ttm = annual[y]
    else:
        if (y - 1, 4) not in q or (y - 1, s) not in q or known_on(y - 1, 4) >= day:
            return None
        ttm = q[(y, s)] + q[(y - 1, 4)] - q[(y - 1, s)]
    last = annual[max(annual)]
    return med, ttm, last


def ratio(a, b):
    return max(a, b) / min(a, b)


def main(price_folder, eps_path, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    series, stats = load(price_folder)
    ytd = load_eps(eps_path)
    by_code = defaultdict(list)
    for (market, code), rows in series.items():
        by_code[code].append(rows)
    index = {}
    for code, lists in by_code.items():
        for rows in lists:
            index[(code, id(rows))] = {d: i for i, (d, *_rest) in enumerate(rows)}
    cal = sorted({d for rows in series.values() for d, *_ in rows})
    evals = [d for d in cal[::20] if d >= D(2018, 4, 1)]
    records = []
    for day in evals:
        day_rows = []
        for code, q in ytd.items():
            view = eps_view(q, day)
            if not view:
                continue
            med, ttm, last = view
            if not (med > 0 and ttm > 0):
                continue
            rows = next((r for r in by_code.get(code, []) if day in index[(code, id(r))]), None)
            if rows is None:
                continue
            i = index[(code, id(rows))][day]
            close = rows[i][1]
            if close < 10 or i < 20:
                continue
            if sum(v for *_x, v in rows[i - 20:i]) / 20 < 1e7:
                continue
            cur = ratio(ttm, med) > 2
            prop = cur and (last <= 0 or ratio(ttm, last) > 2)
            group = "C" if prop else "B" if cur else "A"
            path = []
            cum = 1.0
            for _d, _c, ret, _v in rows[i + 1:i + 121]:
                cum *= 1 + (ret or 0.0)
                path.append(cum)
            if len(path) < 60:
                continue
            r60 = path[59] - 1
            r120 = path[-1] - 1 if len(path) >= 120 else None
            low = min(path) - 1
            day_rows.append({"date": day.isoformat(), "code": code, "group": group, "dir": "above" if ttm > med else "below",
                             "med": round(med, 3), "ttm": round(ttm, 3), "last": round(last, 3), "r60": r60, "r120": r120, "low120": low})
        if not day_rows:
            continue
        m60 = sum(r["r60"] for r in day_rows) / len(day_rows)
        r120s = [r["r120"] for r in day_rows if r["r120"] is not None]
        m120 = sum(r120s) / len(r120s) if r120s else None
        for r in day_rows:
            r["x60"] = r["r60"] - m60
            r["x120"] = r["r120"] - m120 if r["r120"] is not None and m120 is not None else None
        records.extend(day_rows)

    def summary(rows, label):
        out_row = {"group": label, "obs": len(rows), "stocks": len({r["code"] for r in rows})}
        for key, h in (("x60", 60), ("x120", 120)):
            per_day = defaultdict(list)
            for r in rows:
                if r[key] is not None:
                    per_day[r["date"]].append(r[key])
            means = [sum(v) / len(v) for v in per_day.values()]
            out_row[f"{key}_mean%"] = round(100 * sum(means) / len(means), 2) if means else None
            out_row[f"{key}_se%"] = round(100 * statistics.stdev(means) / math.sqrt(len(means)) * math.sqrt(h / 20), 2) if len(means) > 2 else None
            vals = [r[key] for r in rows if r[key] is not None]
            out_row[f"{key}_win%"] = round(100 * sum(v > 0 for v in vals) / len(vals), 1) if vals else None
        lows = [r["low120"] for r in rows]
        out_row["low120_mean%"] = round(100 * sum(lows) / len(lows), 2) if lows else None
        out_row["drop30%"] = round(100 * sum(v <= -0.30 for v in lows) / len(lows), 2) if lows else None
        return out_row

    periods = [("2018-04~2021-12", "2018-04-01", "2021-12-31"), ("2022-01~end", "2022-01-01", "2100-12-31"), ("all", "1900-01-01", "2100-12-31")]
    table = []
    for name, a, b in periods:
        rows = [r for r in records if a <= r["date"] <= b]
        for g in ("A", "B", "C"):
            table.append({"period": name, **summary([r for r in rows if r["group"] == g], g)})
        for g in ("B", "C"):
            for direction in ("above", "below"):
                table.append({"period": name, **summary([r for r in rows if r["group"] == g and r["dir"] == direction], f"{g}_{direction}")})
    with open(out / "summary.json", "w") as f:
        json.dump({"evaluations": len(evals), "records": len(records), "price_stats": stats, "table": table}, f, ensure_ascii=False, indent=1)
    with gzip.open(out / "records.csv.gz", "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(records[0].keys())); w.writeheader(); w.writerows(records)
    cols = ["period", "group", "obs", "stocks", "x60_mean%", "x60_se%", "x60_win%", "x120_mean%", "x120_se%", "x120_win%", "low120_mean%", "drop30%"]
    print(f"evaluations {len(evals)}; records {len(records)}")
    print("\t".join(cols))
    for row in table:
        print("\t".join(str(row.get(c)) for c in cols))
    recent = sorted({r["date"] for r in records})[-1:]
    print("latest evaluation", recent, [(r["code"], r["group"], r["med"], r["ttm"], r["last"]) for r in records if r["date"] in recent and r["code"] in ("2330", "2404", "8299", "5289", "5009")])


if __name__ == "__main__":
    main(*sys.argv[1:4])
