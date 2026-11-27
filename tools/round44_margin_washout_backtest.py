#!/usr/bin/env python3
"""第 44 輪：融資「清洗倍數」——大盤急跌時，融資減幅 ÷ 指數跌幅夠高，之後是不是比較好。
擁有者 2026-11-27 18:38「直接從你這邊寫好上網回測」。出處：Gemini 整理的 YouTube 影片（永豐金 2026-11-27 盤前：
「利用融資減幅再除以指數的減幅，定義叫清洗倍數」，片中說歷史經驗 1.2～1.39、觀察分界 1.15）。規則在看結果前寫定（2026-11-27 18:44 台北，commit 6017168）。

用法：python3 -I tools/round44_margin_washout_backtest.py <MI_5MINS_HIST 快取資料夾> <FinMind 融資總表 JSON> <核對用 url-probe 資料夾> <輸出資料夾>

一、資料
- 加權指數收盤：證交所 MI_5MINS_HIST（2006-01 起）。
- 上市融資金額餘額：FinMind TaiwanStockTotalMarginPurchaseShortSale 的 MarginPurchaseMoney.TodayBalance（元），
  是證交所 MI_MARGN「融資金額(仟元) 今日餘額」的彙整。先用 12 個平均分散的日期和證交所原始回應逐筆核對（仟元 × 1000 要完全相同），
  任何一筆不符或缺少就停止、不出結果。
- 只用兩邊都有的交易日。

二、定義（第 t 天收盤後才知道；融資餘額晚上才公布）
- 前高：t 往前 60 個交易日（含 t）的最高收盤，那天記為 h（同值取最近一天）。
- 指數跌幅 D＝1 − 收盤(t) ÷ 收盤(h)；融資減幅 M＝1 − 融資餘額(t) ÷ 融資餘額(h)；清洗倍數 W＝M ÷ D（只在 D ≥ 10% 時計算）。
- 急跌段：D 第一次 ≥ 10% 開始；D 回到 5% 以下才結束，之後才能開始下一段。

三、比較（都從「訊號日隔天收盤」買進，避免用到收盤後才公布的融資資料）
- S（清洗完成）：每一段裡第一個 W ≥ 1.15 的日子；到這段結束都沒達到就沒有 S。
- N（跌 10% 就買）：每一段的第一天（D 第一次 ≥ 10%）。
- 另列門檻 1.0、1.3、1.5 的 S，以及全部交易日（重疊樣本，只當背景）。
- 結果：加權指數（價格指數，不含股利）之後 20、60、120 個交易日報酬；之後 60 個交易日內再跌的最大幅度（最低收盤 ÷ 買進價 − 1）。
- 每一段列明細（起日、S 日、當時 D、M、W、之後報酬），方便逐段核對。

四、事先寫定的判斷（門檻 1.15）
- 分兩段：2006–2015、2016–最後（依事件日）。每段 S 至少 3 次，否則「樣本不足，不判斷」。
- 兩段都滿足「S 的 60 日平均報酬 − N 的 60 日平均報酬 ≥ +3 個百分點」且「S 的 60 日內最大再跌幅平均比 N 小（較不負）」
  → 支持「等清洗倍數 ≥ 1.15 再進場，比跌 10% 就進場好」。否則不支持。
- 一段只算一筆，筆數少，結果只供參考；結果只寫進 gate-probe，網站要擁有者看過、同意後才加。
"""
import csv
import datetime as dt
import json
import statistics
import sys
from pathlib import Path

SPLIT = "2016-01-01"
THRESHOLDS = (1.0, 1.15, 1.3, 1.5)
HORIZONS = (20, 60, 120)


def load_taiex(cache):
    out = {}
    for p in sorted(Path(cache).glob("MI_5MINS_HIST_*.json")):
        j = json.loads(p.read_text())
        ic = j["fields"].index("收盤指數")
        for r in j.get("data", []):
            y, m, d = r[0].strip().split("/")
            out[dt.date(int(y) + 1911, int(m), int(d)).isoformat()] = float(r[ic].replace(",", ""))
    return out


def load_margin(path):
    return {r["date"]: int(r["TodayBalance"]) for r in json.loads(Path(path).read_text())["data"] if r["name"] == "MarginPurchaseMoney"}


def verify(margin, probe_dir):
    checked = []
    probe = Path(probe_dir)
    for line in (probe / "index.jsonl").read_text().splitlines():
        meta = json.loads(line)
        ymd = meta["url"].split("date=")[1][:8]
        day = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
        j = json.loads((probe / f"{meta['n']}.body").read_text())
        if j.get("stat") != "OK" or j.get("date") != ymd:
            raise SystemExit(f"核對失敗：{day} 證交所回應 stat={j.get('stat')!r} date={j.get('date')!r}")
        row = next((r for t in j.get("tables") or [] for r in t.get("data") or [] if r and r[0] == "融資金額(仟元)"), None)
        if row is None:
            raise SystemExit(f"核對失敗：{day} 證交所回應沒有融資金額列")
        official = int(row[5].replace(",", "")) * 1000
        if margin.get(day) != official:
            raise SystemExit(f"核對失敗：{day} FinMind {margin.get(day)} ≠ 證交所 {official}")
        checked.append(day)
    if len(checked) < 12:
        raise SystemExit(f"核對日期只有 {len(checked)} 天（要 12 天）")
    return checked


def mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def report(events):
    rep = {"n": len(events)}
    for h in HORIZONS:
        xs = [e[f"r{h}"] for e in events if e.get(f"r{h}") is not None]
        rep[f"r{h}"] = {"mean": mean(xs), "median": statistics.median(xs) if xs else None,
                        "positive": sum(x > 0 for x in xs) / len(xs) if xs else None, "n": len(xs)}
    rep["dd60"] = mean([e.get("dd60") for e in events])
    return rep


def main(cache, finmind, probe_dir, out_folder):
    out = Path(out_folder)
    out.mkdir(parents=True, exist_ok=True)
    taiex, margin = load_taiex(cache), load_margin(finmind)
    checked = verify(margin, probe_dir)
    days = sorted(set(taiex) & set(margin))
    close = [taiex[d] for d in days]
    bal = [margin[d] for d in days]
    n = len(days)

    def forward(t):
        e = t + 1
        res = {"entry": days[e] if e < n else None}
        for h in HORIZONS:
            res[f"r{h}"] = close[e + h] / close[e] - 1 if e + h < n else None
        res["dd60"] = min(close[e + 1:e + 61]) / close[e] - 1 if e + 60 < n else None
        return res

    episodes, cur = [], None
    for t in range(59, n - 1):
        window = close[t - 59:t + 1]
        top = max(window)
        h = t - 59 + max(i for i, x in enumerate(window) if x == top)
        dd = 1 - close[t] / close[h]
        md = 1 - bal[t] / bal[h]
        if cur is None and dd >= 0.10:
            cur = {"start": days[t], "high_day": days[h], "N": {"date": days[t], "D": dd, "M": md, "W": md / dd, **forward(t)}, "S": {}, "maxD": dd}
            episodes.append(cur)
        if cur is not None:
            if dd < 0.05:
                cur["end"] = days[t]
                cur = None
                continue
            cur["maxD"] = max(cur["maxD"], dd)
            if dd >= 0.10:
                w = md / dd
                for thr in THRESHOLDS:
                    if thr not in cur["S"] and w >= thr:
                        cur["S"][thr] = {"date": days[t], "D": dd, "M": md, "W": w, **forward(t)}
    if cur is not None:
        cur["end"] = None

    alldays = [forward(t) for t in range(59, n - 1)]
    parts = {"2006-2015": lambda d: d < SPLIT, "2016-": lambda d: d >= SPLIT, "all": lambda d: True}
    summary = {"data": {"first": days[0], "last": days[-1], "days": n, "verifiedDates": checked},
               "episodes": len(episodes), "parts": {}, "allDays": report(alldays)}
    for name, keep in parts.items():
        eps = [e for e in episodes if keep(e["start"])]
        part = {"episodes": len(eps), "N": report([e["N"] for e in eps])}
        for thr in THRESHOLDS:
            part[f"S{thr}"] = report([e["S"][thr] for e in eps if thr in e["S"]])
        summary["parts"][name] = part
    checks = {}
    for name in ("2006-2015", "2016-"):
        p = summary["parts"][name]
        s, nn = p["S1.15"], p["N"]
        if s["n"] < 3 or s["r60"]["mean"] is None or nn["r60"]["mean"] is None:
            checks[name] = {"pass": None, "reason": "樣本不足"}
            continue
        diff = s["r60"]["mean"] - nn["r60"]["mean"]
        checks[name] = {"r60_diff": diff, "dd60_S": s["dd60"], "dd60_N": nn["dd60"],
                        "pass": diff >= 0.03 and s["dd60"] is not None and nn["dd60"] is not None and s["dd60"] > nn["dd60"]}
    summary["checks"] = checks
    if any(c["pass"] is None for c in checks.values()):
        summary["decision"] = "insufficient_sample"
    else:
        summary["decision"] = "supported" if all(c["pass"] for c in checks.values()) else "not_supported"
    (out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(out / "episodes.csv", "w", newline="") as f:
        w = csv.writer(f)
        cols = ["start", "end", "high_day", "maxD", "N_date", "N_W", "N_r20", "N_r60", "N_r120", "N_dd60"]
        for thr in THRESHOLDS:
            cols += [f"S{thr}_date", f"S{thr}_D", f"S{thr}_M", f"S{thr}_r20", f"S{thr}_r60", f"S{thr}_r120", f"S{thr}_dd60"]
        w.writerow(cols)
        rnd = lambda x: None if x is None else round(x, 4)
        for e in episodes:
            row = [e["start"], e.get("end"), e["high_day"], rnd(e["maxD"]), e["N"]["date"], rnd(e["N"]["W"]),
                   rnd(e["N"]["r20"]), rnd(e["N"]["r60"]), rnd(e["N"]["r120"]), rnd(e["N"]["dd60"])]
            for thr in THRESHOLDS:
                s = e["S"].get(thr)
                row += [s["date"], rnd(s["D"]), rnd(s["M"]), rnd(s["r20"]), rnd(s["r60"]), rnd(s["r120"]), rnd(s["dd60"])] if s else [None] * 7
            w.writerow(row)
    print(json.dumps({"episodes": len(episodes), "decision": summary["decision"], "checks": checks}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:5])
