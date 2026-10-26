#!/usr/bin/env python3
"""個股回測用：每月全部上市／上櫃公司營收（公開資訊觀測站彙總靜態檔，Big5）。

用法：python3 -I build_monthly_revenue.py <輸出資料夾> <起始年> <結束年> <可用分鐘數>
- 網址：https://mopsov.twse.com.tw/nas/t21/{sii|otc}/t21sc03_{民國年}_{月}{後綴}.html
  2013 年起分國內（_0）與國外／KY（_1）兩檔；更早只有不帶後綴的一檔。依序嘗試，404 就換下一個。
- 保留：月份、市場、代號、當月營收、去年當月營收、去年同月增減(%)。不自行計算或補值。
- 注意：彙總檔是「現在的版本」（出表日期可能晚於當月），公司事後更正的數字會反映在裡面；回測須註明。
- 每次請求間隔 3 秒；輸出 revenue.csv.gz（可重跑接續）與 files.csv（每個檔的 SHA-256）。
"""
import csv
import datetime as dt
import gzip
import hashlib
import html
import io
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (gate-probe research)"}


def fetch(url):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        raise


def num(s):
    t = s.replace(",", "").strip()
    try:
        return float(t)
    except ValueError:
        return None


def parse(body):
    text = body.decode("cp950", "replace")
    out = []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", text, re.S | re.I):
        c = [html.unescape(re.sub(r"<[^>]+>", "", x)).strip() for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, re.S | re.I)]
        if len(c) >= 7 and re.fullmatch(r"[1-9]\d{3}", c[0]):
            out.append([c[0], c[2].replace(",", ""), c[4].replace(",", ""), c[6].replace(",", "")])
    if "營業收入統計表" not in text or not out:
        raise ValueError("營收彙總表格式不符或沒有資料")
    return out


def main(out, y0, y1, minutes):
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    path, files_log = out / "revenue.csv.gz", out / "files.csv"
    rows, done = [], set()
    if path.exists():
        with gzip.open(path, "rt", newline="") as f:
            for r in csv.DictReader(f):
                rows.append(r); done.add((r["month"], r["market"], r["file"]))
    finished = set()
    if files_log.exists():
        with open(files_log) as f:
            # 以「月份＋市場＋檔案」記錄完成；國內檔（_0）失敗、國外檔（_1）成功時，下次只補國內檔。
            finished = {(r["month"], r["market"], r["file"]) for r in csv.DictReader(f) if r["status"] in ("ok", "404")}
    lf = open(files_log, "a", newline="")
    lw = csv.DictWriter(lf, fieldnames=["month", "market", "file", "url", "status", "rows", "sha256", "bytes"])
    if lf.tell() == 0:
        lw.writeheader()
    deadline = time.time() + float(minutes) * 60
    today = dt.date.today()
    for y in range(int(y0), int(y1) + 1):
        for m in range(1, 13):
            month = f"{y}-{m:02d}"
            if dt.date(y, m, 1) >= today.replace(day=1):
                continue
            for market in ("sii", "otc"):
                if time.time() > deadline:
                    continue
                roc = y - 1911
                suffixes = ["_0", "_1"] if y >= 2013 else [""]
                got_any = False
                for suf in suffixes:
                    if (month, market, suf or "-") in finished:
                        got_any = True
                        continue
                    url = f"https://mopsov.twse.com.tw/nas/t21/{market}/t21sc03_{roc}_{m}{suf}.html"
                    try:
                        body = fetch(url)
                        time.sleep(3)
                        if body is None:
                            lw.writerow({"month": month, "market": market, "file": suf or "-", "url": url, "status": "404", "rows": 0, "sha256": "", "bytes": 0})
                            continue
                        parsed = parse(body)
                        for code, rev, rev_ly, yoy in parsed:
                            rows.append({"month": month, "market": market, "file": suf or "-", "code": code, "revenue": rev, "revenue_last_year": rev_ly, "yoy_pct": yoy})
                        got_any = True
                        lw.writerow({"month": month, "market": market, "file": suf or "-", "url": url, "status": "ok", "rows": len(parsed), "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)})
                    except Exception as e:  # noqa: BLE001
                        lw.writerow({"month": month, "market": market, "file": suf or "-", "url": url, "status": repr(e)[:150], "rows": 0, "sha256": "", "bytes": 0})
                        time.sleep(10)
                    lf.flush()
                if not got_any:
                    print(f"missing {month} {market}", flush=True)
    lf.close()
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=["month", "market", "file", "code", "revenue", "revenue_last_year", "yoy_pct"])
    w.writeheader()
    seen = set()
    for r in sorted(rows, key=lambda r: (r["month"], r["market"], r["code"], r["file"])):
        k = (r["month"], r["market"], r["code"])
        if k in seen:
            continue
        seen.add(k); w.writerow(r)
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as g:
        g.write(buf.getvalue().encode())
    print(f"saved {len(seen)} company-months", flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:])
