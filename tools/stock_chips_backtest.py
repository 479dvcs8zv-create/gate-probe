#!/usr/bin/env python3
"""第 32 輪（三）：個股籌碼——法人買賣超、借券賣出餘額變化，之後 20／60 日是否有超額報酬。規則在看結果前寫定（2026-10-26 10:40）。

用法：python3 -I tools/stock_chips_backtest.py <股價資料夾> <籌碼資料夾> <輸出資料夾>

一、資料
- 股價與還原報酬：同 stock_signal_backtest.py（上市 MI_INDEX、上櫃 dailyQuotes；除權息以交易所參考價還原）。
- 法人：證交所 T86（2012-05 起）、櫃買 insti/dailyTrade（有資料的日子起）。外資＝外資及陸資（不含外資自營商），與網站一致。
- 借券：證交所 TWT93U、櫃買 margin/sbl 的「借券賣出當日餘額」。
- 官方表當天有資料、但某檔沒列出：視為當天法人買賣 0（官方表只列有成交的股票；另統計這種情況的比例）。
  該市場當天整份表沒有資料（假日以外的缺日）→ 那天不算，含該天的 20 日窗口也不算。不補值。

二、訊號（與網站面板同一個量：外資＋投信 N 日合計），換成「占同期成交金額的比例」以便跨股票比較
- F20＝Σ20日（外資＋投信淨買股數 × 當日收盤）÷ Σ20日成交金額；F5 同理（5 日）。
- T20＝只看投信。
- L20＝（借券賣出餘額今日 − 20 個交易日前）× 收盤 ÷ Σ20日成交金額（借券放空增加為正）。
- 每個評估日，在合格股票中依訊號分 5 組（Q1 最低、Q5 最高）；另看 F20 > 0 與 < 0。

三、評估（同 stock_signal_backtest.py）
- 每 5 個交易日一次；合格：66 筆以上歷史、收盤 ≥ 10 元、前 20 日平均成交金額 ≥ 1,000 萬元、該訊號可算。
- 之後 20、60 個交易日還原報酬；超額＝減去同日所有合格股票的等權平均。看各組平均超額與勝率。
- 分 2012–2018、2019–2026 兩段，上市、上櫃分開。不扣交易成本（一買一賣約 0.585%）。
"""
import csv
import datetime as dt
import gzip
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from stock_signal_backtest import load, signals  # noqa: E402

D = dt.date


def load_chips(folder, kind):
    """回傳 (有資料的日子集合, {code: {date: row}})。"""
    folder = Path(folder)
    ok_days = set()
    log = folder / f"{kind}-days.csv"
    if log.exists():
        with open(log) as f:
            ok_days = {D.fromisoformat(r["date"]) for r in csv.DictReader(f) if r["status"] == "ok"}
    data = defaultdict(dict)
    for p in sorted(folder.glob(f"{kind}-[0-9][0-9][0-9][0-9].csv.gz")):
        with gzip.open(p, "rt", newline="") as f:
            for r in csv.DictReader(f):
                data[r["code"]][D.fromisoformat(r["date"])] = r
    return ok_days, data


def main(price_folder, chips_folder, out):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    series, stats = load(price_folder)
    chips = {m: {"insti": load_chips(chips_folder, f"{m}_insti"), "lending": load_chips(chips_folder, f"{m}_lending")} for m in ("twse", "tpex")}
    cal = sorted({d for rows in series.values() for d, *_ in rows})
    eval_days = set(cal[::5])
    absent = defaultdict(int)
    recs = []  # (date, market, code, F5, F20, T20, L20, f20, f60)
    for (market, code), rows in series.items():
        if len(rows) < 70:
            continue
        dates, close, adj, score, tech, rsi, val20 = signals(rows)
        n = len(rows)
        values = np.array([r[3] for r in rows])
        iok, idata = chips[market]["insti"]; lok, ldata = chips[market]["lending"]
        mine, lmine = idata.get(code, {}), ldata.get(code, {})
        # 每天的法人淨買金額（外資＋投信、投信），沒有整份表的日子為 nan
        ft = np.full(n, np.nan); tt = np.full(n, np.nan); sbl = np.full(n, np.nan)
        for i, d in enumerate(dates):
            if d in iok:
                r = mine.get(d)
                if r is None:
                    absent["insti"] += 1; ft[i] = 0.0; tt[i] = 0.0
                else:
                    ft[i] = (float(r["foreign"]) + float(r["trust"])) * close[i]; tt[i] = float(r["trust"]) * close[i]
            if d in lok:
                r = lmine.get(d)
                if r is None:
                    absent["lending"] += 1
                else:
                    sbl[i] = float(r["sbl_balance"])
        for i in range(65, n - 1):
            d = dates[i]
            if d not in eval_days or close[i] < 10 or val20[i] < 1e7 or d > cal[-1] - dt.timedelta(days=95):
                continue
            v20 = values[i - 19:i + 1].sum(); v5 = values[i - 4:i + 1].sum()
            w20, w5, t20 = ft[i - 19:i + 1], ft[i - 4:i + 1], tt[i - 19:i + 1]
            F20 = w20.sum() / v20 if v20 > 0 and not np.isnan(w20).any() else math.nan
            F5 = w5.sum() / v5 if v5 > 0 and not np.isnan(w5).any() else math.nan
            T20 = t20.sum() / v20 if v20 > 0 and not np.isnan(t20).any() else math.nan
            L20 = (sbl[i] - sbl[i - 20]) * close[i] / v20 if v20 > 0 and not math.isnan(sbl[i]) and not math.isnan(sbl[i - 20]) else math.nan
            f20 = adj[min(i + 20, n - 1)] / adj[i] - 1
            f60 = adj[min(i + 60, n - 1)] / adj[i] - 1
            recs.append((d, market, code, F5, F20, T20, L20, f20, f60))
    by_day = defaultdict(list)
    for r in recs:
        by_day[r[0]].append(r)
    mean20 = {d: np.mean([x[7] for x in v]) for d, v in by_day.items()}
    mean60 = {d: np.mean([x[8] for x in v]) for d, v in by_day.items()}
    # 每個評估日、每個訊號的分組（只在該訊號可算的股票中分）
    quint = {}
    for k in (3, 4, 5, 6):
        for d, v in by_day.items():
            xs = [r for r in v if not math.isnan(r[k])]
            if len(xs) < 50:
                continue
            xs.sort(key=lambda r: r[k])
            for j, r in enumerate(xs):
                quint[(k, r[0], r[1], r[2])] = min(5, 1 + j * 5 // len(xs))
    lines = []
    p = lines.append
    first = {m: (min(chips[m]["insti"][0]) if chips[m]["insti"][0] else None, min(chips[m]["lending"][0]) if chips[m]["lending"][0] else None) for m in chips}
    p(f"股價 {cal[0]}～{cal[-1]}；法人資料起日 上市 {first['twse'][0]}、上櫃 {first['tpex'][0]}；借券起日 上市 {first['twse'][1]}、上櫃 {first['tpex'][1]}")
    p(f"評估樣本 {len(recs):,} 筆；官方表有資料但該檔未列（視為 0）：法人 {absent['insti']:,} 股票日；借券未列（不算）{absent['lending']:,} 股票日")
    names = {3: "F5 外資＋投信 5 日淨買÷成交", 4: "F20 外資＋投信 20 日淨買÷成交", 5: "T20 投信 20 日淨買÷成交", 6: "L20 借券賣出餘額 20 日增加÷成交"}
    periods = [("全期", lambda r: True), ("2012–2018", lambda r: r[0] <= D(2018, 12, 31)), ("2019–2026", lambda r: r[0] >= D(2019, 1, 1)),
               ("全期只看上市", lambda r: r[1] == "twse"), ("全期只看上櫃", lambda r: r[1] == "tpex")]
    result = {}
    for k in (4, 3, 5, 6):
        for pname, pf in periods:
            p(f"\n## {names[k]}（{pname}）")
            p("組 | 筆數 | 訊號中位數 | 20日超額 | 20日勝率 | 60日超額 | 60日勝率")
            for q in range(1, 6):
                xs = [r for r in recs if pf(r) and quint.get((k, r[0], r[1], r[2])) == q]
                if not xs:
                    continue
                e20 = [r[7] - mean20[r[0]] for r in xs]; e60 = [r[8] - mean60[r[0]] for r in xs]
                result[f"{k}|{pname}|Q{q}"] = {"n": len(xs), "ex20": float(np.mean(e20)), "ex60": float(np.mean(e60))}
                p(f"Q{q}{'（最低）' if q == 1 else '（最高）' if q == 5 else ''} | {len(xs):,} | {np.median([r[k] for r in xs])*100:+.2f}% | "
                  f"{np.mean(e20)*100:+.2f}% | {np.mean([e > 0 for e in e20])*100:.1f}% | {np.mean(e60)*100:+.2f}% | {np.mean([e > 0 for e in e60])*100:.1f}%")
    p("\n## F20 正負（全期）")
    p("組 | 筆數 | 20日超額 | 20日勝率 | 60日超額 | 60日勝率")
    for name, f in (("外資＋投信 20 日淨買 > 0", lambda v: v > 0), ("外資＋投信 20 日淨賣（< 0）", lambda v: v < 0)):
        xs = [r for r in recs if not math.isnan(r[4]) and f(r[4])]
        e20 = [r[7] - mean20[r[0]] for r in xs]; e60 = [r[8] - mean60[r[0]] for r in xs]
        p(f"{name} | {len(xs):,} | {np.mean(e20)*100:+.2f}% | {np.mean([e > 0 for e in e20])*100:.1f}% | {np.mean(e60)*100:+.2f}% | {np.mean([e > 0 for e in e60])*100:.1f}%")
    p("\n交易成本參考：一買一賣約 0.585%。")
    (out / "chips.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (out / "chips.json").write_text(json.dumps({"absent": absent, "records": len(recs), "groups": result}, ensure_ascii=False, indent=1))
    print("\n".join(lines))


if __name__ == "__main__":
    main(*sys.argv[1:])
