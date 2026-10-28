#!/usr/bin/env python3
"""第 36 輪回測：新台幣匯率（FRED DEXTAUS，1 美元兌新台幣）突破前 20 日高／低點之後，加權指數表現。

擁有者 2026-10-29 06:23「好」：先回測新台幣，結果明顯比美元指數強才考慮放上網站或計分。
用法：python3 round36_twd_backtest.py <taiex_usd.csv（含 dextaus 欄）>
口徑與第 28 輪（tools/backtest_round28.py）完全相同，只換序列：
- 零軸＝(當天匯率 − 前 20 筆最高) ÷ (前 20 筆最高 − 最低) × 100，不含當天。DEXTAUS 上升＝美元升值、新台幣貶值。
- 報酬：訊號日收盤 → 之後第 20／60 個交易日收盤；60 日內最大跌幅＝min(之後 1～60 日收盤) ÷ 訊號日收盤 − 1。
- 狀態 B：零軸 > 0（新台幣在 20 日貶值高點之外）；訊號 A：零軸由 ≤ 0 變 > 0；A 獨立事件：相隔至少 20 個交易日；狀態 C：零軸 < −100（新台幣升破 20 日高點）。
- 何時「知道」：
  - lag8：觀測日＋8 天後第一個交易日（FRED H.10 每週公布，與第 28 輪美元指數同一延遲）。
  - lag1：觀測日隔天起第一個交易日（模擬改用央行／台北外匯每日收盤：當天 16:00 收盤，台股已收，最早隔天才能用）。
- 誤差：重疊樣本以「天數 ÷ 20」估獨立樣本數；差距 ÷ 標準誤 ≥ 2 才算明顯。只用輸入檔；不補值；不調參數。
"""
import sys
import numpy as np
import pandas as pd

PERIODS = [("2006-2015", "2006-01-01", "2015-12-31"), ("2016-end", "2016-01-01", "2100-12-31"), ("full", "1900-01-01", "2100-12-31")]


def load(path):
    df = pd.read_csv(path, dtype=str)
    df["date"] = pd.to_datetime(df["date"])
    for c in ("taiex_close", "dtwexafegs", "dextaus"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("date").reset_index(drop=True)


def zero_axis(df, col, tx, lag_days):
    obs = df.loc[df[col].notna(), ["date", col]].reset_index(drop=True)
    v = obs[col].to_numpy()
    z = np.full(len(v), np.nan)
    for i in range(20, len(v)):
        hi, lo = v[i - 20:i].max(), v[i - 20:i].min()
        if hi != lo:
            z[i] = (v[i] - hi) / (hi - lo) * 100
    obs["z"] = z
    days = tx["date"].to_numpy()
    idx = np.searchsorted(days, (obs["date"] + pd.Timedelta(days=lag_days)).to_numpy(), side="left")
    obs = obs[idx < len(days)].copy()
    obs["known"] = days[idx[idx < len(days)]]
    obs = obs.sort_values(["known", "date"]).drop_duplicates("known", keep="last")
    return pd.merge_asof(tx[["date"]], obs[["known", "date", col, "z"]].rename(columns={"date": "obs_date"}),
                         left_on="date", right_on="known", direction="backward")


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


def summarize(mask, base, f, label, horizon_days=20):
    out = {"group": label}
    for name, arr in zip(("r20", "r60", "dd60"), f):
        x = arr[mask & ~np.isnan(arr)]; b = arr[base & ~np.isnan(arr)]
        out[f"{name}_n"] = len(x)
        out[f"{name}_mean%"] = round(x.mean() * 100, 3) if len(x) else np.nan
        if name != "dd60":
            out[f"{name}_up%"] = round((x > 0).mean() * 100, 1) if len(x) else np.nan
        if name == "r20" and len(x) > 1:
            n_eff = max(len(x) / horizon_days, 1.0) if label != "A_independent_20d" else len(x)
            se = x.std(ddof=1) / np.sqrt(n_eff)
            out["r20_diff_vs_all%"] = round((x.mean() - b.mean()) * 100, 3)
            out["r20_diff/se"] = round((x.mean() - b.mean()) / se, 2) if se > 0 else np.nan
    return out


def backtest(df, tx, col, lag_days):
    m = zero_axis(df, col, tx, lag_days)
    z = m["z"].to_numpy(); prev = np.r_[np.nan, z[:-1]]
    allz = ~np.isnan(z)
    sigA = allz & (~np.isnan(prev)) & (z > 0) & (prev <= 0)
    stB = allz & (z > 0); stC = allz & (z < -100)
    f = fwd(tx); d = tx["date"]; rows = []
    for pname, a, b in PERIODS:
        per = ((d >= a) & (d <= b)).to_numpy()
        base = per & allz
        for lab, mk in (("all_days", allz), ("A_cross_up", sigA), ("B_z>0", stB), ("C_z<-100", stC)):
            rows.append({"series": col, "lag": lag_days, "period": pname, **summarize(per & mk, base, f, lab)})
        sel, last = [], -10**9
        for i in np.where(per & sigA)[0]:
            if i - last >= 20:
                sel.append(i); last = i
        ind = np.zeros(len(z), bool); ind[sel] = True
        rows.append({"series": col, "lag": lag_days, "period": pname, **summarize(ind, base, f, "A_independent_20d")})
    return pd.DataFrame(rows)


def main(path):
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 200)
    df = load(path)
    tx = df[df["taiex_close"].notna() & (df["date"] >= "2006-01-01")][["date", "taiex_close"]].reset_index(drop=True)
    print(f"taiex {len(tx)} days {tx.date.iloc[0].date()}..{tx.date.iloc[-1].date()}; "
          f"dextaus {df.dextaus.notna().sum()} obs {df.loc[df.dextaus.notna(), 'date'].min().date()}..{df.loc[df.dextaus.notna(), 'date'].max().date()}; "
          f"dtwexafegs {df.dtwexafegs.notna().sum()}")
    for col, lag in (("dtwexafegs", 8), ("dextaus", 8), ("dextaus", 1)):
        print(f"\n--- {col} (known after {lag} day{'s' if lag > 1 else ''}) ---")
        print(backtest(df, tx, col, lag).to_string(index=False))


if __name__ == "__main__":
    main(sys.argv[1])
