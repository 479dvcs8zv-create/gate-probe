#!/usr/bin/env python3
"""回測用證交所當沖成交股數占比（每日）。
- 2014-07 起：TWTB4U2 月表（一個月一次請求，每日一列；證交所註明自民國 103 年 6 月 30 日起提供）。
- 2014-01-06～2014-06-30：TWTB4U 日表（現股當沖開放首日起），逐日請求。
- 每次請求間隔 4 秒；原始回應只存 SHA-256；輸出 daytrade.csv（date, daytrade_share, source, sha256）。
用法：python3 -I build_twse_daytrade.py <輸出資料夾> [交易日快取資料夾]
"""
import csv
import datetime as dt
import hashlib
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from build_twse_daily import fetch, num, parse_dt, trading_days  # noqa: E402


def main(out, cache="results/backtest-data/twse-cache"):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    rows, fails = {}, []
    days = trading_days(cache)
    for d in [x for x in days if dt.date(2014, 1, 6) <= x < dt.date(2014, 7, 1)]:
        ymd = d.strftime("%Y%m%d")
        try:
            b = fetch(f"https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U?date={ymd}&selectType=All&response=json")
            rows[d.isoformat()] = {"date": d.isoformat(), "daytrade_share": parse_dt(b, ymd), "source": "TWTB4U", "sha256": hashlib.sha256(b).hexdigest()}
        except Exception as e:  # noqa: BLE001
            fails.append({"date": d.isoformat(), "error": repr(e)[:200]})
        time.sleep(4)
    m, today = dt.date(2014, 7, 1), dt.date.today()
    while m <= today:
        url = f"https://www.twse.com.tw/rwd/zh/dayTrading/TWTB4U2?date={m.strftime('%Y%m%d')}&stockNo=&response=json"
        try:
            b = fetch(url)
            j = json.loads(b)
            if j.get("stat") != "OK":
                raise ValueError(f"stat={j.get('stat')!r}")
            t = next(t for t in j["tables"] if t.get("fields") and "日期" in t["fields"])
            f = t["fields"]
            k = next(x for x in f if "當日沖銷交易總成交股數占市場比重" in x)
            sha = hashlib.sha256(b).hexdigest()
            for r in t["data"]:
                y, mo, dd = r[f.index("日期")].strip().split("/")
                iso = dt.date(int(y) + 1911, int(mo), int(dd)).isoformat()
                rows[iso] = {"date": iso, "daytrade_share": num(r[f.index(k)]), "source": "TWTB4U2", "sha256": sha}
        except Exception as e:  # noqa: BLE001
            fails.append({"month": m.isoformat()[:7], "error": repr(e)[:200]})
        time.sleep(4)
        m = dt.date(m.year + (m.month == 12), m.month % 12 + 1, 1)
    with open(out / "daytrade.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "daytrade_share", "source", "sha256"])
        w.writeheader()
        for k in sorted(rows):
            w.writerow(rows[k])
    (out / "daytrade_failures.json").write_text(json.dumps(fails, ensure_ascii=False, indent=1))
    print(f"daytrade rows {len(rows)}, failures {len(fails)}")


if __name__ == "__main__":
    main(*sys.argv[1:])
