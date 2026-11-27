#!/usr/bin/env python3
"""第 45 輪補充（看過第 45 輪結果之後才加，**不是事先寫定的規則**，不改第 45 輪的判斷）：對照組。

為什麼加：第 45 輪「投信大賣」（T20 ≤ −1%）之後也贏等權大盤，表示超額可能大多來自「投信有在交易的股票」本身，而不是投信買。
這裡用和第 45 輪完全相同的資料、合格條件、T20 算法、t＋1 收盤進場與超額算法，另算兩個對照：
- 有投信資料的合格日（T20 算得出來；每檔每 20 個交易日取一天，避免重疊）。
- 中性：其中 |T20| < 0.2% 的日子。
並抽 5 筆第 45 輪的「突破 1%」事件，從原始 T86 與股本重算 T20，核對程式。

用法：python3 -I tools/round45b_trust_ratio_control.py <股價資料夾> <法人資料夾> <股本資料夾> <第 45 輪輸出資料夾>
"""
import bisect
import csv
import gzip
import json
import random
import statistics
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from round40_ma60_chips_backtest import moving_average  # noqa: E402
from round45_trust_ratio_backtest import HORIZONS, SPLIT, START, group, load_shares, load_trust  # noqa: E402
from stock_signal_backtest import load  # noqa: E402


def main(price_folder, chips_folder, shares_folder, r45_folder):
    out = Path(r45_folder)
    series, _ = load(price_folder)
    trust, shares = load_trust(chips_folder), load_shares(shares_folder)
    daily, prepared = defaultdict(list), {}
    for (market, code), rows in series.items():
        if market != "twse" or len(rows) < 200:
            continue
        dates = [r[0] for r in rows]
        close = np.array([r[1] for r in rows], dtype=float)
        rets = np.array([r[2] if r[2] is not None else 0.0 for r in rows], dtype=float)
        value = np.array([r[3] for r in rows], dtype=float)
        ok = (close >= 10) & (moving_average(value, 20) >= 1e7)
        prepared[code] = (dates, close, np.cumprod(1 + rets), ok)
        for i in range(1, len(rows)):
            if ok[i - 1] and dates[i] >= START and rows[i][2] is not None:
                daily[dates[i]].append(rows[i][2])
    mdates = sorted(daily)
    mlevel = dict(zip(mdates, np.cumprod([1 + statistics.fmean(daily[d]) for d in mdates])))

    covered, neutral, t20_of = [], [], {}
    for code, (dates, close, adj, ok) in prepared.items():
        tx, sx = trust.get(code, {}), shares.get(code)
        if not tx or not sx:
            continue
        sdates = [d for d, _ in sx]
        step = 0
        for t in range(19, len(dates) - 1):
            if dates[t] < START:
                continue
            k = bisect.bisect_right(sdates, dates[t]) - 1
            win = dates[t - 19:t + 1]
            if k < 0 or not all(d in tx for d in win):
                continue
            cur = sum(tx[d] for d in win) / sx[k][1]
            t20_of[(code, dates[t].isoformat())] = cur
            if not ok[t]:
                continue
            step += 1
            if step % 20:
                continue
            e = {"date": dates[t].isoformat(), "month": dates[t].isoformat()[:7]}
            entry = t + 1
            for h in HORIZONS:
                end = entry + h
                if end >= len(dates):
                    continue
                ret = float(adj[end] / adj[entry] - 1)
                m0, m1 = mlevel.get(dates[entry]), mlevel.get(dates[end])
                e[f"ret{h}"] = ret
                e[f"ex{h}"] = ret - (m1 / m0 - 1) if m0 and m1 else None
            covered.append(e)
            if abs(cur) < 0.002:
                neutral.append(e)

    def parts(rows):
        return {"2012-2018": group([e for e in rows if e["date"] < SPLIT]), "2019-": group([e for e in rows if e["date"] >= SPLIT]), "all": group(rows)}

    # 抽查：從原始 T86（trust 欄）與股本重算 5 筆事件的 T20
    with gzip.open(out / "events.csv.gz", "rt", newline="") as f:
        ev = [r for r in csv.DictReader(f) if r["signal"] == "buy1.0"]
    random.seed(45)
    spot = []
    for r in random.sample(ev, 5):
        mine = t20_of.get((r["code"], r["date"]))
        spot.append({"code": r["code"], "date": r["date"], "t20_event": float(r["t20"]), "t20_recomputed": mine,
                     "match": mine is not None and abs(mine - float(r["t20"])) < 1e-6})
    result = {"note": "post-registration control (added after round 45 results); does not change the round 45 decision",
              "covered_sampled": parts(covered), "neutral_abs_lt_0.2pct": parts(neutral), "spotcheck": spot}
    (out / "control_post_registration.json").write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(json.dumps({"covered": len(covered), "neutral": len(neutral), "spot": spot}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:5])
