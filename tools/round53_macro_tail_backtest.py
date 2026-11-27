#!/usr/bin/env python3
"""第 53 輪：總經改成「平常 65%，信用或融資出事才大幅降」（Gemini 2026-11-27 文件第四節題目 A、B）。
擁有者 2026-11-28 00:15「做完吧」。規則在看結果前寫定（REGISTERED_AT）。門檻是 Gemini 提的，照抄，不另外挑。

用法：python3 -I tools/round53_macro_tail_backtest.py <taiex_usd.csv（含 FRED 欄）> <報酬指數 url-probe 資料夾,...> <第31輪 score_history.csv> <輸出資料夾>

一、資料
- 台股：證交所「發行量加權股價報酬指數」（MFI94U，含股利）每日收盤；另列價格指數（同第 33 輪）。
- FRED：BAMLH0A0HYM2（高收益債利差）、IC4WSA（初領失業金 4 週平均）、DCOILWTICO（WTI）、DEXJPUS（日圓兌美元）、
  TEDRATE（2018-03 以前的融資利差）、SOFR、IORB（2021-07 起）／IOER（之前）。
- 公布延遲（不偷看）：日資料日期 d 的值，台灣 d＋2 天（含）以後的交易日才用；IC4WSA（週六為週末日）d＋6 天以後才用。
- 每個台股交易日 t：用 t 以前已可用的資料算狀態，持股從下一個交易日生效（同第 33 輪；每變動 1 成扣 0.02%，現金報酬 0）。

二、規則（Gemini 題目 A：紅燈 25%）
- 紅燈條件（任一）：
  1. 高收益債利差 − 前 20 筆最低 ≥ 0.75 個百分點。
  2. 融資：2018-03 以前 TED > 0.75%；2018-04 以後 SOFR − IORB（沒有 IORB 用 IOER）> 0.05 個百分點且連續 3 筆，
     日期落在季底前後（3、6、9、12 月 27 日以後，或 1、4、7、10 月 3 日以前）與 4/15～4/17、9/15～9/17 的不算。
  3. 初領失業金 4 週平均 ≥ 前 52 週最低 × 1.12，而且高收益債利差 − 前 60 筆最低 ≥ 0.50 個百分點。
- 紅燈時持股 25%；三個條件都不成立且連續 10 個交易日後，回到 65%。

三、規則（Gemini 題目 B：在 A 上加橘燈 45%）
- 橘燈：日圓 5 筆內升值 ≥ 3%（DEXJPUS 下跌 ≥ 3%），而且 WTI 20 筆內跌 ≥ 15%、高收益債利差 20 筆內擴大 ≥ 0.30 個百分點。
- 解除：高收益債利差連續 5 筆沒有創 20 筆新高，而且日圓 5 筆升幅 < 1.5%。紅燈優先。

四、比較：固定 65%、網站現行 D10（第 31 輪重建分數，同第 33 輪）、A、B。分 2006–2015、2016–2026-10（分數只到第 31 輪資料結束日）。
五、事先寫定的判斷
- A：兩段都滿足「最大跌幅（絕對值）≤ 固定 65% 的 75%」且「年化報酬 ≥ 固定 65%」→ 支持。
- B：兩段都滿足「Calmar（年化 ÷ 最大跌幅絕對值）> A 的 Calmar，也 > 固定 65% 的」→ 支持。
- 主判斷用報酬指數；價格指數只列數字。結果只寫進 gate-probe；網站規則要擁有者看過、同意後才改。
"""
import csv
import datetime as dt
import json
import sys
from bisect import bisect_left, bisect_right
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from round33_backtest import macro, simulate, weight_rules  # noqa: E402

REGISTERED_AT = "2026-11-28 00:22 台北"
D = dt.date
SPLIT = D(2016, 1, 1)


def load_return_index(folders):
    out = {}
    for folder in folders.split(","):
        p = Path(folder)
        for line in (p / "index.jsonl").read_text().splitlines():
            meta = json.loads(line)
            j = json.loads((p / f"{meta['n']}.body").read_text())
            if j.get("stat") != "OK":
                raise SystemExit(f"報酬指數回應不正常：{meta['url']} stat={j.get('stat')!r}")
            for r in j.get("data") or []:
                y, m, d = r[0].strip().split("/")
                out[D(int(y) + 1911, int(m), int(d))] = float(r[1].replace(",", ""))
    return out


def load_fred(path):
    cols = {}
    with open(path, newline="") as f:
        for r in csv.DictReader(f):
            d = D.fromisoformat(r["date"])
            for k, v in r.items():
                if k in ("date", "taiex_close") or v in ("", None):
                    continue
                cols.setdefault(k, []).append((d, float(v)))
    return {k: sorted(v) for k, v in cols.items()}


class Series:
    """觀測序列＋可用日：value 日期 d 從 d＋lag 天起可用。"""

    def __init__(self, rows, lag):
        self.dates = [d for d, _ in rows]
        self.vals = [v for _, v in rows]
        self.avail = [d + dt.timedelta(days=lag) for d in self.dates]

    def upto(self, t):
        """台股日 t 已可用的觀測個數（索引上限）。"""
        return bisect_right(self.avail, t)


def quarter_end_or_tax(d):
    return (d.month in (3, 6, 9, 12) and d.day >= 27) or (d.month in (1, 4, 7, 10) and d.day <= 3) or \
        (d.month == 4 and 15 <= d.day <= 17) or (d.month == 9 and 15 <= d.day <= 17)


def states(days, fred):
    hy = Series(fred["bamlh0a0hym2"], 2)
    claims = Series(fred["ic4wsa"], 6)
    oil = Series(fred["dcoilwtico"], 2)
    jpy = Series(fred["dexjpus"], 2)
    ted = Series(fred["tedrate"], 2)
    sofr = Series(fred["sofr"], 2)
    pol = {d: v for d, v in fred.get("ioer", [])}
    pol.update({d: v for d, v in fred.get("iorb", [])})
    pol_dates = sorted(pol)
    out_a, out_b = [], []
    red_a = False
    calm_a = 0
    orange = False
    for t in days:
        nh = hy.upto(t)
        hv = hy.vals[:nh]
        c1 = nh >= 21 and hv[-1] - min(hv[-21:-1]) >= 0.75
        if t < D(2018, 4, 1):
            nt = ted.upto(t)
            c2 = nt >= 1 and ted.vals[nt - 1] > 0.75
        else:
            ns = sofr.upto(t)
            spreads = []
            for k in range(ns - 1, -1, -1):
                d = sofr.dates[k]
                if quarter_end_or_tax(d):
                    continue
                j = bisect_right(pol_dates, d) - 1
                if j < 0:
                    break
                spreads.append(sofr.vals[k] - pol[pol_dates[j]])
                if len(spreads) == 3:
                    break
            c2 = len(spreads) == 3 and all(s > 0.05 for s in spreads)
        nc = claims.upto(t)
        cv = claims.vals[:nc]
        c3 = nc >= 53 and nh >= 61 and cv[-1] >= 1.12 * min(cv[-53:-1]) and hv[-1] - min(hv[-61:-1]) >= 0.50
        hit = c1 or c2 or c3
        if hit:
            red_a, calm_a = True, 0
        elif red_a:
            calm_a += 1
            if calm_a >= 10:
                red_a = False
        out_a.append(0.25 if red_a else 0.65)
        # 題目 B：橘燈
        nj, no = jpy.upto(t), oil.upto(t)
        jv, ov = jpy.vals[:nj], oil.vals[:no]
        jpy5 = jv[-1] / jv[-6] - 1 if nj >= 6 else None   # 日圓兌美元數值下跌＝日圓升值
        trig = (jpy5 is not None and jpy5 <= -0.03 and no >= 21 and ov[-1] / ov[-21] - 1 <= -0.15 and nh >= 21 and hv[-1] - hv[-21] >= 0.30)
        if trig:
            orange = True
        elif orange and nh >= 25 and jpy5 is not None:
            no_new_high = all(hv[k] < max(hv[k - 20:k]) for k in range(nh - 5, nh))
            if no_new_high and -jpy5 < 0.015:
                orange = False
        out_b.append(0.25 if red_a else 0.45 if orange else 0.65)
    return out_a, out_b


def main(fred_csv, return_folders, score_csv, out):
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    tri = load_return_index(return_folders)
    fred = load_fred(fred_csv)
    mdates, mma, taiex = macro(score_csv)
    d10 = weight_rules(mdates, mma)["D10"]
    end = mdates[-1]
    days = [d for d in sorted(tri) if d <= end]
    rets = [None] + [tri[days[i]] / tri[days[i - 1]] - 1 for i in range(1, len(days))]
    price = {d: v for d, v in zip(mdates, taiex)}
    prets = [None] + [(price[days[i]] / price[days[i - 1]] - 1) if days[i] in price and days[i - 1] in price else None for i in range(1, len(days))]
    wa, wb = states(days, fred)
    wd10 = [d10[bisect_right(mdates, d) - 1] if bisect_right(mdates, d) > 0 else 0.65 for d in days]
    rules = {"fixed65": [0.65] * len(days), "D10": wd10, "A": wa, "B": wb}
    summary = {"registeredAt": REGISTERED_AT, "days": len(days), "first": days[0].isoformat(), "last": days[-1].isoformat(),
               "redShare": sum(w == 0.25 for w in wa) / len(wa), "orangeShare": sum(w == 0.45 for w in wb) / len(wb), "parts": {}}
    # 紅燈期間（方便核對）
    spans, start = [], None
    for d, w in zip(days, wa):
        if w == 0.25 and start is None:
            start = d
        if w != 0.25 and start is not None:
            spans.append((start.isoformat(), d.isoformat()))
            start = None
    if start:
        spans.append((start.isoformat(), days[-1].isoformat()))
    summary["redSpans"] = spans
    for asset, r in (("total_return", rets), ("price", prets)):
        for pname, lo, hi in (("2006-2015", None, D(2015, 12, 31)), ("2016-", SPLIT, None), ("all", None, None)):
            for k, w in rules.items():
                res = simulate(days, r, w, lo, hi)
                res["calmar"] = res["cagr"] / abs(res["mdd"]) if res["mdd"] else None
                summary["parts"][f"{asset}|{pname}|{k}"] = res
    checks = {"A": {}, "B": {}}
    for pname in ("2006-2015", "2016-"):
        g = lambda k: summary["parts"][f"total_return|{pname}|{k}"]  # noqa: E731
        f, a, b = g("fixed65"), g("A"), g("B")
        checks["A"][pname] = {"mdd_ratio": abs(a["mdd"]) / abs(f["mdd"]), "cagr_diff": a["cagr"] - f["cagr"],
                              "pass": abs(a["mdd"]) <= 0.75 * abs(f["mdd"]) and a["cagr"] >= f["cagr"]}
        checks["B"][pname] = {"calmar_B": b["calmar"], "calmar_A": a["calmar"], "calmar_fixed": f["calmar"],
                              "pass": b["calmar"] > a["calmar"] and b["calmar"] > f["calmar"]}
    summary["checks"] = checks
    summary["decision"] = {k: "supported" if all(x["pass"] for x in v.values()) else "not_supported" for k, v in checks.items()}
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"decision": summary["decision"], "checks": checks, "redShare": summary["redShare"], "redSpans": len(spans)}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:5])
