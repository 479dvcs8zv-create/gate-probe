#!/usr/bin/env python3
"""第 28 輪回測（規則見 handoff/GEMINI_TASK_LATEST.md；擁有者 2026-10-21 03:15 改由 Claude 直接執行）。

用法：python3 backtest_round28.py <taiex_usd.csv>
只用輸入檔；不補值；不調參數。
口徑（題目沒寫死的地方，在此明訂）：
- 報酬：訊號日收盤 → 之後第 20／60 個交易日收盤。
- 60 日內最大跌幅：min(之後 1～60 個交易日收盤) ÷ 訊號日收盤 − 1。
- 均線濾網：收盤 ≥ N 日均線（含當日）→ 下一個交易日起持有；第一個有均線的日子之前不持有，也不計績效；
  買進持有用同一段日子比較。年化報酬用日曆日：(期末/期初)^(365.25/天數) − 1；年化波動＝日報酬標準差 × √252。
- 分段：訊號依訊號日歸段；均線濾網把全期跑出的每日報酬切段後各自重算（部位不在段首重設）。
"""
import sys
import numpy as np
import pandas as pd

BUY, SELL = 0.001425, 0.001425 + 0.001
PERIODS = [("2006-2015", "2006-01-01", "2015-12-31"), ("2016-end", "2016-01-01", "2100-12-31"), ("full", "1900-01-01", "2100-12-31")]


def load(path):
    df = pd.read_csv(path, dtype=str)
    df["date"] = pd.to_datetime(df["date"])
    for c in ("taiex_close", "dtwexafegs", "dtwexbgs"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def zero_axis(df, col, tx):
    obs = df.loc[df[col].notna(), ["date", col]].reset_index(drop=True)
    v = obs[col].to_numpy()
    z = np.full(len(v), np.nan)
    for i in range(20, len(v)):
        hi, lo = v[i - 20:i].max(), v[i - 20:i].min()
        if hi != lo:
            z[i] = (v[i] - hi) / (hi - lo) * 100
    obs["z"] = z
    days = tx["date"].to_numpy()
    idx = np.searchsorted(days, (obs["date"] + pd.Timedelta(days=8)).to_numpy(), side="left")
    obs = obs[idx < len(days)].copy()
    obs["known"] = days[idx[idx < len(days)]]
    obs = obs.sort_values(["known", "date"]).drop_duplicates("known", keep="last")
    m = pd.merge_asof(tx[["date"]], obs[["known", "date", col, "z"]].rename(columns={"date": "obs_date"}),
                      left_on="date", right_on="known", direction="backward")
    return m


def fwd(tx):
    p = tx["taiex_close"].to_numpy()
    n = len(p)
    r20 = np.full(n, np.nan); r60 = np.full(n, np.nan); dd60 = np.full(n, np.nan)
    for i in range(n):
        if i + 20 < n: r20[i] = p[i + 20] / p[i] - 1
        if i + 60 < n:
            r60[i] = p[i + 60] / p[i] - 1
            dd60[i] = p[i + 1:i + 61].min() / p[i] - 1
    return r20, r60, dd60


def stats(mask, f, label):
    out = {"group": label}
    for name, arr in zip(("r20", "r60", "dd60"), f):
        x = arr[mask & ~np.isnan(arr)]
        out[f"{name}_n"] = len(x)
        out[f"{name}_mean%"] = round(x.mean() * 100, 3) if len(x) else np.nan
        out[f"{name}_median%"] = round(np.median(x) * 100, 3) if len(x) else np.nan
        if name != "dd60":
            out[f"{name}_up%"] = round((x > 0).mean() * 100, 1) if len(x) else np.nan
    return out


def backtest1(df, tx, col):
    m = zero_axis(df, col, tx)
    z = m["z"].to_numpy()
    prev = np.r_[np.nan, z[:-1]]
    sigA = (~np.isnan(z)) & (~np.isnan(prev)) & (z > 0) & (prev <= 0)
    stB = (~np.isnan(z)) & (z > 0)
    stC = (~np.isnan(z)) & (z < -100)
    allz = ~np.isnan(z)
    f = fwd(tx)
    d = tx["date"]
    rows = []
    for pname, a, b in PERIODS:
        per = ((d >= a) & (d <= b)).to_numpy()
        for lab, mk in (("all_days", allz), ("A_cross_up", sigA), ("B_z>0", stB), ("C_z<-100", stC)):
            rows.append({"series": col, "period": pname, **stats(per & mk, f, lab)})
        idx = np.where(per & sigA)[0]
        sel, last = [], -10**9
        for i in idx:
            if i - last >= 20:
                sel.append(i); last = i
        ind = np.zeros(len(z), bool); ind[sel] = True
        rows.append({"series": col, "period": pname, **stats(ind, f, "A_independent_20d")})
    return pd.DataFrame(rows), m, sigA


def strat(tx, n, low):
    p = tx["taiex_close"].to_numpy()
    ma = pd.Series(p).rolling(n).mean().to_numpy()
    sig = np.where(np.isnan(ma), np.nan, np.where(p >= ma, 1.0, low))
    first = int(np.where(~np.isnan(sig))[0][0])
    ret = np.r_[np.nan, p[1:] / p[:-1] - 1]
    pos = np.r_[0.0, sig[:-1]]  # day t return uses signal from t-1
    pos[:first + 1] = 0.0
    pos = np.nan_to_num(pos)
    dpos = np.r_[0.0, np.diff(pos)]
    cost = np.where(dpos > 0, dpos * BUY, np.where(dpos < 0, -dpos * SELL, 0.0))
    sret = (1 + pos * np.nan_to_num(ret)) * (1 - cost) - 1
    live = np.zeros(len(p), bool); live[first + 1:] = True
    return pd.DataFrame({"date": tx["date"], "ret": ret, "sret": sret, "pos": pos, "switch": dpos != 0, "live": live})


def metrics(r, dates):
    eq = np.cumprod(1 + r)
    days = (dates.iloc[-1] - dates.iloc[0]).days
    ann = eq[-1] ** (365.25 / days) - 1 if days > 0 else np.nan
    dd = (eq / np.maximum.accumulate(np.r_[1.0, eq])[1:] - 1).min()
    return round(ann * 100, 3), round(dd * 100, 3), round(r.std(ddof=1) * np.sqrt(252) * 100, 3)


def backtest2(tx):
    rows = []
    for n in (60, 240):
        for low in (0.0, 0.5):
            s = strat(tx, n, low)
            for pname, a, b in PERIODS:
                k = s[s["live"] & (s["date"] >= a) & (s["date"] <= b)]
                if len(k) < 2:
                    continue
                sa, sd, sv = metrics(k["sret"].to_numpy(), k["date"])
                ba, bd, bv = metrics(k["ret"].to_numpy(), k["date"])
                rows.append({"N": n, "low_pos": low, "period": pname, "start": k["date"].iloc[0].date(), "end": k["date"].iloc[-1].date(),
                             "days": len(k), "strat_ann%": sa, "strat_maxdd%": sd, "strat_vol%": sv,
                             "bh_ann%": ba, "bh_maxdd%": bd, "bh_vol%": bv,
                             "switches": int(k["switch"].sum()), "avg_exposure%": round(k["pos"].mean() * 100, 1),
                             "full_pos_days%": round((k["pos"] == 1).mean() * 100, 1)})
    return pd.DataFrame(rows)


def main(path):
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 200)
    df = load(path)
    tx = df[df["taiex_close"].notna()][["date", "taiex_close"]].reset_index(drop=True)
    print(f"rows {len(df)}; taiex {len(tx)} days {tx.date.iloc[0].date()}..{tx.date.iloc[-1].date()}; "
          f"dtwexafegs {df.dtwexafegs.notna().sum()}; dtwexbgs {df.dtwexbgs.notna().sum()}; "
          f"rows without taiex (skipped for backtest 2) {df.taiex_close.isna().sum()}")
    print("\n=== Backtest 1: dollar index zero-axis (forward TAIEX returns, %) ===")
    rng = np.random.default_rng(28)
    for col in ("dtwexafegs", "dtwexbgs"):
        res, m, sigA = backtest1(df, tx, col)
        print(f"\n--- {col} ---")
        print(res.to_string(index=False))
        pick = np.sort(rng.choice(np.where(sigA)[0], 5, replace=False))
        print("5 random signal-A days:")
        print(pd.DataFrame({"trade_date": tx.date.iloc[pick].dt.date.values, "dollar_obs_date": m["obs_date"].iloc[pick].dt.date.values,
                            "dollar_value": m[col].iloc[pick].values, "z": m["z"].iloc[pick].round(2).values,
                            "z_prev_day": m["z"].shift(1).iloc[pick].round(2).values,
                            "taiex_close": tx.taiex_close.iloc[pick].values}).to_string(index=False))
    print("\n=== Backtest 2: TAIEX MA filter (strategy vs buy-and-hold on the same days) ===")
    print(backtest2(tx).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1])
