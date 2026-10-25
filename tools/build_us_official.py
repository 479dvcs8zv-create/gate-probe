#!/usr/bin/env python3
"""回測用美國官方資料（FRED 從 GitHub 連不上時改抓原始官方來源）。不使用任何金鑰。

用法：python3 -I build_us_official.py <輸出資料夾> [起始年=2005]
- 勞工統計局 BLS v1（免金鑰，POST，每次最多 10 年）：核心 CPI（CUSR0000SA0L1E，季調）、非農就業總數（CES0000000001，千人，季調）、失業率（LNS14000000，季調）。
- 財政部 Treasury 每日殖利率曲線 CSV（每年一檔）：名目 2 年、10 年；實質 10 年（TIPS 實質殖利率曲線）。
  FRED 的 T10Y2Y＝DGS10−DGS2、DFII10 都是這兩條曲線的同一組數字（H.15 引用財政部）。
- 紐約聯儲 SOFR（2018-04-02 起）。
- 聯準會 DDP「Policy Rates」：IOER（2008-10-09～2021-07-28）、IORB（2021-07-29 起）。
- 原始回應全部存檔＋SHA-256；輸出 us_official.csv（date 欄＋各序列，月資料日期記為該月 1 日）。
- 沒抓到的就留空，不補值；失敗記在 manifest.json。
"""
import csv
import datetime as dt
import hashlib
import io
import json
import sys
import time
import urllib.request
from pathlib import Path

UA = "Mozilla/5.0 (gate-probe research)"


def get(url, data=None, tries=3):
    last = None
    for n in range(tries):
        try:
            req = urllib.request.Request(url, data=data, headers={"User-Agent": UA, **({"Content-Type": "application/json"} if data else {})})
            with urllib.request.urlopen(req, timeout=90) as r:
                return r.read()
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(15 * (n + 1))
    raise RuntimeError(f"{url}: {last!r}")


def main(out, start_year=2005):
    start_year = int(start_year)
    out = Path(out); (out / "raw").mkdir(parents=True, exist_ok=True)
    today = dt.date.today()
    cols, files, failures = {}, [], []

    def save(name, body, url):
        (out / "raw" / name).write_bytes(body)
        files.append({"url": url, "file": f"raw/{name}", "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)})

    def put(series, date, value):
        try:
            v = float(str(value).replace(",", ""))
        except (TypeError, ValueError):
            return  # "-"（例如 2025 年政府關門未公布）、空白、"." 都當缺值
        cols.setdefault(series, {})[date] = v

    # BLS
    bls = {"CUSR0000SA0L1E": "cpilfesl", "CES0000000001": "payems", "LNS14000000": "unrate"}
    y = start_year
    while y <= today.year:
        y2 = min(y + 9, today.year)
        url = "https://api.bls.gov/publicAPI/v1/timeseries/data/"
        try:
            body = get(url, json.dumps({"seriesid": list(bls), "startyear": str(y), "endyear": str(y2)}).encode())
            save(f"bls_{y}_{y2}.json", body, url + f"?POST startyear={y}&endyear={y2}")
            j = json.loads(body)
            if j.get("status") != "REQUEST_SUCCEEDED":
                raise RuntimeError(f"BLS status {j.get('status')} {j.get('message')}")
            for s in j["Results"]["series"]:
                for r in s["data"]:
                    if r["period"].startswith("M") and r["period"] != "M13":
                        put(bls[s["seriesID"]], f"{r['year']}-{r['period'][1:]}-01", r["value"])
        except Exception as e:  # noqa: BLE001
            failures.append({"source": "BLS", "years": f"{y}-{y2}", "error": repr(e)[:300]})
        y = y2 + 1
        time.sleep(3)
    # Treasury
    for y in range(start_year, today.year + 1):
        for kind, wanted in (("daily_treasury_yield_curve", {"2 Yr": "dgs2", "10 Yr": "dgs10"}),
                             ("daily_treasury_real_yield_curve", {"10 YR": "dfii10"})):
            url = (f"https://home.treasury.gov/resource-center/data-chart-center/interest-rates/daily-treasury-rates.csv/{y}/all"
                   f"?type={kind}&field_tdr_date_value={y}&page&_format=csv")
            try:
                body = get(url)
                save(f"treasury_{kind}_{y}.csv", body, url)
                rows = list(csv.DictReader(io.StringIO(body.decode("utf-8-sig"))))
                if not rows:
                    raise RuntimeError("empty")
                for r in rows:
                    m, d, yy = r["Date"].split("/")
                    for src, dst in wanted.items():
                        put(dst, f"{yy}-{m}-{d}", r.get(src))
            except Exception as e:  # noqa: BLE001
                failures.append({"source": "Treasury", "kind": kind, "year": y, "error": repr(e)[:300]})
            time.sleep(2)
    # NY Fed SOFR, one year per request
    for y in range(2018, today.year + 1):
        a, b = (f"{y}-04-01" if y == 2018 else f"{y}-01-01"), f"{y}-12-31"
        url = f"https://markets.newyorkfed.org/api/rates/secured/sofr/search.json?startDate={a}&endDate={b}"
        try:
            body = get(url)
            save(f"sofr_{y}.json", body, url)
            for r in json.loads(body)["refRates"]:
                put("sofr", r["effectiveDate"], r.get("percentRate"))
        except Exception as e:  # noqa: BLE001
            failures.append({"source": "NYFed", "year": y, "error": repr(e)[:300]})
        time.sleep(2)
    # FRB policy rates
    url = ("https://www.federalreserve.gov/datadownload/Output.aspx?rel=PRATES&series=c27939ee810cb2e929a920a6bd77d9f6"
           "&lastobs=&from=&to=&filetype=csv&label=include&layout=seriescolumn&type=package")
    try:
        body = get(url)
        save("frb_prates.csv", body, url)
        lines = body.decode("utf-8-sig").splitlines()
        hdr = next(i for i, l in enumerate(lines) if l.startswith('"Time Period"'))
        names = [x.strip('"') for x in lines[hdr].split(",")]
        for l in lines[hdr + 1:]:
            parts = l.split(",")
            row = dict(zip(names, parts))
            put("ioer", row["Time Period"], row.get("RESBME_N.D"))
            put("iorb", row["Time Period"], row.get("RESBM_N.D"))
    except Exception as e:  # noqa: BLE001
        failures.append({"source": "FRB PRATES", "error": repr(e)[:300]})
    names = sorted(cols)
    dates = sorted(set().union(*[set(v) for v in cols.values()])) if cols else []
    with open(out / "us_official.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["date"] + names)
        for d in dates:
            if d >= f"{start_year}-01-01":
                w.writerow([d] + [cols[n].get(d, "") for n in names])
    (out / "manifest.json").write_text(json.dumps({
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(), "complete": not failures, "failures": failures,
        "counts": {n: len(v) for n, v in cols.items()}, "files": files}, ensure_ascii=False, indent=1))
    print(json.dumps({"counts": {n: len(v) for n, v in cols.items()}, "failures": len(failures)}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:])
