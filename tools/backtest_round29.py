#!/usr/bin/env python3
"""第 29 輪：總體加減分合計 → 建議持股比例（擁有者 2026-10-21 03:36／03:39）。

用法：python3 backtest_round29.py <taiex_usd.csv（含 vixcls、vxvcls、bamlh0a0hym2、baa10y 欄）>
規則在看結果之前寫定，不依結果調整：
因子（每個交易日 t 收盤時，只用當時已公布的資料）：
  F1 美元：DTWEXAFEGS 零軸 > 0（站上前 20 個觀測的最高）→ −1，否則 0（擁有者：走弱不加分）。觀測日 d 於 d+8 日曆日起第一個台股交易日才可用。
  F2 信用利差：利差零軸 > 0（利差創 20 個觀測新高＝明顯擴大）→ −1，否則 0。主要用高收益債利差 BAMLH0A0HYM2；若其歷史不足，用 BAA10Y。觀測日 d 於 d+2 起可用。
  F3 恐慌加分：VIX ≥ 30 且 VIX ÷ 3 個月 VIX（VXVCLS）> 1（期限結構倒掛）→ +1，否則 0。觀測日 d 於 d+2 起可用。（30 為常用恐慌線，事先寫定）
  F4 大盤年線：收盤 > 240 日線且 240 日線比前一日高 → +1；收盤 < 240 日線且 240 日線比前一日低 → −1；其他 0。
  合計 S（−3～+2）。持股 h = 65% + k × S，下限 25%、上限 100%；k = 5、10、15、20 各做一次。t 收盤決定，t+1 起生效。
  交易成本按實際買賣的比例：買 0.1425%、賣 0.1425%＋0.1%。比較：固定 65%（每日維持 65%，不計再平衡成本）、一直持有 100%。
  所有因子都有資料的第一天起算；分 2006–2015、2016 以後、全期（以實際起算日為準）。
報酬口徑與第 28 輪相同（價格指數、不含股利，現金報酬 0）。
"""
import sys
import numpy as np
import pandas as pd

BUY, SELL = 0.001425, 0.001425 + 0.001
PERIODS = [("2006-2015", "2006-01-01", "2015-12-31"), ("2016-end", "2016-01-01", "2100-12-31"), ("full", "1900-01-01", "2100-12-31")]


def known_series(df, col, tx, lag_days, fn=None):
    """把觀測序列（可先經 fn 轉換）依公布延遲對應到台股交易日。"""
    obs = df.loc[df[col].notna(), ["date", col]].reset_index(drop=True)
    obs["v"] = fn(obs[col].to_numpy()) if fn else obs[col]
    days = tx["date"].to_numpy()
    idx = np.searchsorted(days, (obs["date"] + pd.Timedelta(days=lag_days)).to_numpy(), side="left")
    ok = idx < len(days)
    obs = obs[ok].copy(); obs["known"] = days[idx[ok]]
    obs = obs.sort_values(["known", "date"]).drop_duplicates("known", keep="last")
    m = pd.merge_asof(tx[["date"]], obs[["known", "v"]], left_on="date", right_on="known", direction="backward")
    return m["v"].to_numpy()


def zaxis(v):
    z = np.full(len(v), np.nan)
    for i in range(20, len(v)):
        hi, lo = v[i - 20:i].max(), v[i - 20:i].min()
        if hi != lo:
            z[i] = (v[i] - hi) / (hi - lo) * 100
    return z


def factors(df, tx, credit_col):
    p = tx["taiex_close"].to_numpy()
    f = pd.DataFrame({"date": tx["date"], "close": p})
    zu = known_series(df, "dtwexafegs", tx, 8, zaxis)
    f["F1_usd"] = np.where(np.isnan(zu), np.nan, np.where(zu > 0, -1, 0))
    zc = known_series(df, credit_col, tx, 2, zaxis)
    f["F2_credit"] = np.where(np.isnan(zc), np.nan, np.where(zc > 0, -1, 0))
    both = df[df.vixcls.notna() & df.vxvcls.notna()]
    tmp = df.copy(); tmp["ratio"] = np.nan; tmp.loc[both.index, "ratio"] = (both.vixcls / both.vxvcls).values
    tmp["vixok"] = np.nan; tmp.loc[both.index, "vixok"] = ((both.vixcls >= 30) & (both.vixcls / both.vxvcls > 1)).astype(float).values
    fv = known_series(tmp, "vixok", tx, 2)
    f["F3_panic"] = np.where(np.isnan(fv), np.nan, np.where(fv > 0, 1, 0))
    ma = pd.Series(p).rolling(240).mean().to_numpy()
    prev = np.r_[np.nan, ma[:-1]]
    f4 = np.where(np.isnan(ma) | np.isnan(prev), np.nan, np.where((p > ma) & (ma > prev), 1, np.where((p < ma) & (ma < prev), -1, 0)))
    f["F4_ma240"] = f4
    cols = ["F1_usd", "F2_credit", "F3_panic", "F4_ma240"]
    f["S"] = f[cols].sum(axis=1, min_count=4)
    return f, cols


def fwd(p):
    n = len(p); r20 = np.full(n, np.nan); r60 = np.full(n, np.nan); dd = np.full(n, np.nan)
    for i in range(n):
        if i + 20 < n: r20[i] = p[i + 20] / p[i] - 1
        if i + 60 < n: r60[i] = p[i + 60] / p[i] - 1; dd[i] = p[i + 1:i + 61].min() / p[i] - 1
    return r20, r60, dd


def cond_table(f, cols):
    r20, r60, dd = fwd(f["close"].to_numpy())
    rows = []
    for pname, a, b in PERIODS:
        per = ((f.date >= a) & (f.date <= b) & f.S.notna()).to_numpy()
        groups = [("all", np.ones(len(f), bool))]
        for c in cols:
            for v in sorted(f[c].dropna().unique()):
                groups.append((f"{c}={int(v):+d}", (f[c] == v).to_numpy()))
        for v in sorted(f.S.dropna().unique()):
            groups.append((f"S={int(v):+d}", (f.S == v).to_numpy()))
        for lab, mk in groups:
            m = per & mk
            row = {"period": pname, "group": lab, "days": int(m.sum())}
            for name, arr in (("r20", r20), ("r60", r60), ("dd60", dd)):
                x = arr[m & ~np.isnan(arr)]
                row[f"{name}_mean%"] = round(x.mean() * 100, 2) if len(x) else np.nan
                if name != "dd60":
                    row[f"{name}_up%"] = round((x > 0).mean() * 100, 1) if len(x) else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def run(f, h):
    p = f["close"].to_numpy()
    ret = np.r_[np.nan, p[1:] / p[:-1] - 1]
    pos = np.r_[0.0, h[:-1]]
    start = int(np.where(~np.isnan(h))[0][0])
    pos[:start + 1] = 0.0; pos = np.nan_to_num(pos)
    d = np.r_[0.0, np.diff(pos)]
    cost = np.where(d > 0, d * BUY, np.where(d < 0, -d * SELL, 0.0))
    sret = (1 + pos * np.nan_to_num(ret)) * (1 - cost) - 1
    live = np.zeros(len(p), bool); live[start + 1:] = True
    return pd.DataFrame({"date": f.date, "ret": np.nan_to_num(ret), "sret": sret, "pos": pos, "chg": d != 0, "live": live})


def metrics(r, dates):
    eq = np.cumprod(1 + r); days = (dates.iloc[-1] - dates.iloc[0]).days
    ann = eq[-1] ** (365.25 / days) - 1
    dd = (eq / np.maximum.accumulate(np.r_[1.0, eq])[1:] - 1).min()
    return round(ann * 100, 2), round(dd * 100, 2), round(r.std(ddof=1) * np.sqrt(252) * 100, 2)


def holdings_table(f):
    S = f.S.to_numpy(); rows = []
    variants = [("constant 65%", np.where(np.isnan(S), np.nan, 0.65)), ("buy&hold 100%", np.where(np.isnan(S), np.nan, 1.0))]
    for k in (5, 10, 15, 20):
        variants.append((f"k={k}%/point", np.where(np.isnan(S), np.nan, np.clip(0.65 + k / 100 * S, 0.25, 1.0))))
    # 看過上面結果後才加的版本（可能有事後偏差，另行標示）：合計在 −1～+1 之間不動，只有超過的分數才換算。
    for k in (10, 20):
        beyond = np.sign(S) * np.maximum(np.abs(S) - 1, 0)
        variants.append((f"POST-HOC deadband k={k}%", np.where(np.isnan(S), np.nan, np.clip(0.65 + k / 100 * beyond, 0.25, 1.0))))
    for lab, h in variants:
        s = run(f, h)
        for pname, a, b in PERIODS:
            q = s[s.live & (s.date >= a) & (s.date <= b)]
            if len(q) < 2:
                continue
            ann, dd, vol = metrics(q.sret.to_numpy(), q.date)
            rows.append({"variant": lab, "period": pname, "start": q.date.iloc[0].date(), "end": q.date.iloc[-1].date(),
                         "ann%": ann, "maxdd%": dd, "vol%": vol, "avg_exposure%": round(q.pos.mean() * 100, 1),
                         "min_exposure%": round(q.pos.min() * 100, 1), "changes": int(q.chg.sum())})
    return pd.DataFrame(rows)


def main(path):
    pd.set_option("display.width", 250); pd.set_option("display.max_columns", 30); pd.set_option("display.max_rows", 500)
    df = pd.read_csv(path, dtype=str); df["date"] = pd.to_datetime(df["date"])
    for c in df.columns[1:]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values("date").reset_index(drop=True)
    tx = df[df.taiex_close.notna()][["date", "taiex_close"]].reset_index(drop=True)
    for c in ("dtwexafegs", "vixcls", "vxvcls", "bamlh0a0hym2", "baa10y"):
        s = df.loc[df[c].notna(), "date"]
        print(f"{c}: {len(s)} obs {s.min().date() if len(s) else None}..{s.max().date() if len(s) else None}")
    hy_first = df.loc[df.bamlh0a0hym2.notna(), "date"].min()
    credits = ["bamlh0a0hym2", "baa10y"] if pd.notna(hy_first) and hy_first <= pd.Timestamp("2007-12-31") else ["baa10y"]
    if credits == ["baa10y"]:
        print("BAMLH0A0HYM2 history starts", hy_first, "-> too short; primary credit spread = BAA10Y")
    for i, cc in enumerate(credits):
        f, cols = factors(df, tx, cc)
        first = f.loc[f.S.notna(), "date"].min()
        tag = "PRIMARY" if i == 0 else "SENSITIVITY"
        print(f"\n######## {tag}: credit spread = {cc}; all four factors available from {first.date()} ########")
        print("\nDays per total score S:", f.S.value_counts().sort_index().to_dict())
        print("\n=== A. Forward TAIEX returns by factor state and by total score (%) ===")
        print(cond_table(f, cols).to_string(index=False))
        print("\n=== B. Holdings = 65% + k x S (floor 25%, cap 100%) vs constant 65% and 100% ===")
        print(holdings_table(f).to_string(index=False))
        last = f[f.S.notna()].iloc[-1]
        print(f"\nLatest {last.date.date()}: " + ", ".join(f"{c}={int(last[c]):+d}" for c in cols) + f", S={int(last.S):+d}")


if __name__ == "__main__":
    main(sys.argv[1])
