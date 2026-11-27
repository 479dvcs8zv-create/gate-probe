#!/usr/bin/env python3
"""第 47 輪：單季毛利率「季增且年增」的股票，之後有沒有比較強。
擁有者 2026-11-27 19:07「好先做」（Gemini 整理的 YouTube 建議：玩股網 2026-11-25「最新一季毛利率要比去年同季高，而且要比上季高」）。
規則在看結果前寫定（REGISTERED_AT）。

用法：python3 -I tools/round47_gross_margin_backtest.py <t163sb04 原始頁資料夾> <股價資料夾> <輸出資料夾>

一、資料
- 公開資訊觀測站 t163sb04「綜合損益表彙總」原始頁（gate-probe results/backtest-data/eps/raw，2013Q1～2026Q2；
  2026Q3 那份抓的時候只有 30 家公司，不用）。
- 只用一般產業格式表格的「營業收入」與「營業毛利（毛損）淨額」（沒有淨額欄才用「營業毛利（毛損）」）；金融、保險等沒有毛利的格式不列入。
- 數字是年度累計：Q1＝累計；Q2～Q4＝本季累計 − 上一季累計（上一季缺就不算）。單季毛利率＝單季毛利 ÷ 單季營收，營收 ≤ 0 不算。
- 彙總表是「現在的版本」，含公司事後更正；結果須註明。

二、訊號日與分組
- 訊號日：法定公告期限（Q1 5/15、Q2 8/14、Q3 11/14、年報 3/31）之後的第一個交易日；所有公司都等到這天才算「已知」，
  不用實際公告日（避免偷看）。
- G（季增且年增）：本季毛利率 > 上一季，而且 > 去年同季。三個數字都要有。
- 其他：三個數字都有，但不是 G。另列（只列數字）：只季增、只年增、兩個都沒有。
- 訊號日要合格：收盤 ≥ 10 元、前 20 日平均成交金額 ≥ 1,000 萬元。上市＋上櫃。

三、結果
- 訊號日收盤買進，之後 20、60 個交易日的還原報酬；超額＝減去同期全部合格股票等權平均。
- 每一季是一個批次：每批算 G 與「其他」的平均超額與兩者差，再對批次平均；標準誤＝批次值的標準差 ÷ √批數
  （批次相隔約 60 個交易日，60 日報酬幾乎不重疊）。
- 分兩段：2014–2018、2019–最後（依訊號日；年增要有去年資料，2014 起才有 G）。

四、事先寫定的判斷
- 兩段都滿足「G 減其他的 60 日超額差 ≥ +1.0 個百分點」且「20 日超額差 > 0」→ 支持把它當基本面輔助指標（先只顯示）。否則不支持。
- 結果只寫進 gate-probe；網站要擁有者看過、同意後才加。
"""
import datetime as dt
import gzip
import html
import json
import math
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from round40_ma60_chips_backtest import moving_average  # noqa: E402
from stock_signal_backtest import load  # noqa: E402

REGISTERED_AT = "2026-11-27 19:09 台北"
SPLIT = "2019-01-01"
HORIZONS = (20, 60)
DEADLINE = {1: (5, 15), 2: (8, 14), 3: (11, 14), 4: (3, 31)}


def cells(row):
    return [re.sub(r"\s+", "", html.unescape(re.sub(r"<[^>]+>", "", x))) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)]


def num(s):
    try:
        return float(s.replace(",", ""))
    except ValueError:
        return None


def parse_page(body):
    """回傳 {代號: (累計營收, 累計毛利)}，只取一般產業格式。"""
    text = body.decode("utf-8", "replace")
    out = {}
    for table in re.findall(r"<table[^>]*>(.*?)</table>", text, re.S | re.I):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)
        if not rows:
            continue
        head = cells(rows[0])
        if "公司代號" not in head or "營業收入" not in head:
            continue
        gp = "營業毛利（毛損）淨額" if "營業毛利（毛損）淨額" in head else "營業毛利（毛損）" if "營業毛利（毛損）" in head else None
        if gp is None:
            continue
        ic, ir, ig = head.index("公司代號"), head.index("營業收入"), head.index(gp)
        for row in rows[1:]:
            c = cells(row)
            if len(c) <= max(ir, ig) or not re.fullmatch(r"[1-9]\d{3}", c[ic]):
                continue
            rev, g = num(c[ir]), num(c[ig])
            if rev is not None and g is not None:
                out[c[ic]] = (rev, g)
    return out


def quarterly_margins(raw):
    cum = defaultdict(dict)  # (年, 季) -> 代號 -> (累計營收, 累計毛利)
    for p in sorted(Path(raw).glob("*-*-*.html.gz")):
        m, y, s = p.name[:-len(".html.gz")].split("-")
        year, season = int(y) + 1911, int(s)
        if (year, season) == (2026, 3):
            continue
        with gzip.open(p, "rb") as f:
            cum[(year, season)].update(parse_page(f.read()))
    gm = defaultdict(dict)  # (年, 季) -> 代號 -> 單季毛利率
    for (year, season), rows in cum.items():
        for code, (rev, g) in rows.items():
            if season > 1:
                prev = cum.get((year, season - 1), {}).get(code)
                if prev is None:
                    continue
                rev, g = rev - prev[0], g - prev[1]
            if rev > 0:
                gm[(year, season)][code] = g / rev
    return gm


def signal_day(year, season, trading):
    m, d = DEADLINE[season]
    deadline = dt.date(year + (1 if season == 4 else 0), m, d)
    later = [x for x in trading if x > deadline]
    return later[0] if later else None


def main(raw, price_folder, out_folder):
    out = Path(out_folder)
    out.mkdir(parents=True, exist_ok=True)
    gm = quarterly_margins(raw)
    series, _ = load(price_folder)
    daily, prepared = defaultdict(list), {}
    for (market, code), rows in series.items():
        if len(rows) < 200:
            continue
        dates = [r[0] for r in rows]
        close = np.array([r[1] for r in rows], dtype=float)
        adj = np.cumprod(1 + np.array([r[2] if r[2] is not None else 0.0 for r in rows], dtype=float))
        ok = (close >= 10) & (moving_average(np.array([r[3] for r in rows], dtype=float), 20) >= 1e7)
        prepared[code] = (dates, {d: i for i, d in enumerate(dates)}, adj, ok)
        for i in range(1, len(rows)):
            if ok[i - 1] and rows[i][2] is not None:
                daily[dates[i]].append(rows[i][2])
    mdates = sorted(daily)
    mlevel = dict(zip(mdates, np.cumprod([1 + statistics.fmean(daily[d]) for d in mdates])))

    batches = []
    for (year, season) in sorted(gm):
        prev_q = (year, season - 1) if season > 1 else (year - 1, 4)
        if prev_q not in gm or (year - 1, season) not in gm:
            continue
        day = signal_day(year, season, mdates)
        if day is None:
            continue
        groups = defaultdict(list)
        for code, now in gm[(year, season)].items():
            qoq, yoy = gm[prev_q].get(code), gm[(year - 1, season)].get(code)
            if qoq is None or yoy is None or code not in prepared:
                continue
            dates, index, adj, ok = prepared[code]
            t = index.get(day)
            if t is None or not ok[t]:
                continue
            up_q, up_y = now > qoq, now > yoy
            e = {"code": code}
            for h in HORIZONS:
                if t + h < len(dates) and dates[t + h] in mlevel:
                    ret = float(adj[t + h] / adj[t] - 1)
                    e[f"ex{h}"] = ret - (mlevel[dates[t + h]] / mlevel[day] - 1)
            key = "G" if up_q and up_y else "qoq_only" if up_q else "yoy_only" if up_y else "neither"
            groups[key].append(e)
            if key != "G":
                groups["other"].append(e)
        batch = {"quarter": f"{year}Q{season}", "date": day.isoformat(), "n": {k: len(v) for k, v in groups.items()}}
        for h in HORIZONS:
            for k, v in groups.items():
                xs = [e[f"ex{h}"] for e in v if f"ex{h}" in e]
                batch[f"{k}_ex{h}"] = statistics.fmean(xs) if xs else None
            if batch.get(f"G_ex{h}") is not None and batch.get(f"other_ex{h}") is not None:
                batch[f"diff{h}"] = batch[f"G_ex{h}"] - batch[f"other_ex{h}"]
        batches.append(batch)

    def agg(rows, key):
        xs = [b[key] for b in rows if b.get(key) is not None]
        if not xs:
            return None
        return {"mean": statistics.fmean(xs), "se": statistics.stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else None,
                "batches": len(xs), "positive": sum(x > 0 for x in xs) / len(xs)}

    parts = {"2014-2018": [b for b in batches if b["date"] < SPLIT], "2019-": [b for b in batches if b["date"] >= SPLIT], "all": batches}
    summary = {"registeredAt": REGISTERED_AT, "batches": len(batches), "parts": {}}
    for name, rows in parts.items():
        summary["parts"][name] = {key: agg(rows, key) for key in
                                  ["diff20", "diff60"] + [f"{k}_ex{h}" for k in ("G", "other", "qoq_only", "yoy_only", "neither") for h in HORIZONS]}
        summary["parts"][name]["avg_counts"] = {k: statistics.fmean(b["n"].get(k, 0) for b in rows) for k in ("G", "other")} if rows else None
    checks = {}
    for name in ("2014-2018", "2019-"):
        p = summary["parts"][name]
        d60, d20 = (p["diff60"] or {}).get("mean"), (p["diff20"] or {}).get("mean")
        checks[name] = {"diff60": d60, "diff20": d20, "pass": d60 is not None and d20 is not None and d60 >= 0.01 and d20 > 0}
    summary["checks"] = checks
    summary["decision"] = "supported" if all(c["pass"] for c in checks.values()) else "not_supported"
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "batches.json").write_text(json.dumps(batches, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"batches": len(batches), "decision": summary["decision"], "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:4])
