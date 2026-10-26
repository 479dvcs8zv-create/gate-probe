#!/usr/bin/env python3
"""個股回測用：證交所「除權除息計算結果表」TWT49U（每年一次請求，2006 起）。

用法：python3 -I build_twse_exrights.py <輸出資料夾> <起始年> <結束年>
為什麼需要：證交所 MI_INDEX 在除權息日把漲跌標成「X（不比價）」、漲跌價差 0，無法從收盤推回參考價；
回測改用本表的「除權息參考價」：當日還原報酬＝收盤 ÷ 除權息參考價 − 1。
保留：日期、代號、除權息前收盤價、除權息參考價、權值＋息值、權／息。只留 4 碼普通股。原始回應記 SHA-256。
"""
import csv
import hashlib
import json
import re
import sys
import time
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (gate-probe research)", "Accept": "application/json"}


def main(out, y0, y1):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    rows, log = [], []
    for y in range(int(y0), int(y1) + 1):
        url = f"https://www.twse.com.tw/rwd/zh/exRight/TWT49U?startDate={y}0101&endDate={y}1231&response=json"
        body = urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90).read()
        j = json.loads(body)
        if j.get("stat") != "OK":
            raise ValueError(f"{y}: stat={j.get('stat')!r}")
        f = [x.strip() for x in j["fields"]]
        ix = {k: f.index(k) for k in ("資料日期", "股票代號", "除權息前收盤價", "除權息參考價", "權值+息值", "權/息")}
        n = 0
        for r in j.get("data") or []:
            code = str(r[ix["股票代號"]]).strip()
            if not re.fullmatch(r"[1-9]\d{3}", code):
                continue
            m = re.fullmatch(r"(\d+)年(\d+)月(\d+)日", str(r[ix["資料日期"]]).strip())
            date = f"{int(m[1]) + 1911:04d}-{int(m[2]):02d}-{int(m[3]):02d}"
            rows.append([date, code, str(r[ix["除權息前收盤價"]]).replace(",", ""), str(r[ix["除權息參考價"]]).replace(",", ""),
                         str(r[ix["權值+息值"]]).replace(",", ""), str(r[ix["權/息"]]).strip()])
            n += 1
        log.append([y, n, hashlib.sha256(body).hexdigest(), len(body)])
        print(y, n, flush=True)
        time.sleep(4)
    with open(out / "twse-exrights.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["date", "code", "pre_close", "reference", "rights_plus_dividend", "type"]); w.writerows(sorted(rows))
    with open(out / "twse-exrights-files.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["year", "rows", "sha256", "bytes"]); w.writerows(log)


if __name__ == "__main__":
    main(*sys.argv[1:])
