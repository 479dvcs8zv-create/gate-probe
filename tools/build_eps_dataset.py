#!/usr/bin/env python3
"""第 37 輪回測用：全部上市／上櫃公司每季基本每股盈餘（公開資訊觀測站「綜合損益表彙總」t163sb04）。

用法：python3 -I build_eps_dataset.py <輸出資料夾> <起始民國年> <結束民國年>
- 網址：https://mopsov.twse.com.tw/mops/web/ajax_t163sb04?encodeURIComponent=1&step=1&firstin=1&off=1&isQuery=Y&TYPEK={sii|otc}&year={民國年}&season={01..04}
  （GitHub 2026-10-29 實測 GET 可用，gate-probe url-probe；一頁含該市場該季全部公司，依產業格式分多個表格。）
- 每個表格找「公司代號」與「基本每股盈餘」欄；只保留 4 碼代號與可解析的數字，不自行計算或補值。
- 數字是「該年度截至該季的累計」（頁面註2）；單季、近四季由回測程式自己算。
- 彙總表是「現在的版本」，公司事後更正會反映在裡面；回測須註明。
- 每次請求間隔 4 秒、失敗重試 3 次；輸出 eps.csv.gz（可重跑接續）、files.csv（每頁 SHA-256）與原始頁 raw/*.html.gz。
"""
import csv
import gzip
import hashlib
import html
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

UA = {"User-Agent": "Mozilla/5.0 (gate-probe research)"}
BASE = "https://mopsov.twse.com.tw/mops/web/ajax_t163sb04?encodeURIComponent=1&step=1&firstin=1&off=1&isQuery=Y&TYPEK={m}&year={y}&season={s:02d}"


def fetch(url):
    last = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError) as e:
            last = e
            time.sleep(10 * (attempt + 1))
    raise last


def cells(row):
    return [re.sub(r"\s+", "", html.unescape(re.sub(r"<[^>]+>", "", x))) for x in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", row, re.S | re.I)]


def parse(body):
    text = body.decode("utf-8", "replace")
    if "查詢無資料" in text or "查無資料" in text:
        return []
    if "公開資訊觀測站" not in text or "累計" not in text:
        raise ValueError("彙總表格式不符")
    out = []
    for table in re.findall(r"<table[^>]*>(.*?)</table>", text, re.S | re.I):
        rows = re.findall(r"<tr[^>]*>(.*?)</tr>", table, re.S | re.I)
        if not rows:
            continue
        head = cells(rows[0])
        if "公司代號" not in head:
            continue
        eps_cols = [i for i, h in enumerate(head) if h.startswith("基本每股盈餘")]
        if not eps_cols:
            continue
        code_i, name_i, eps_i = head.index("公司代號"), head.index("公司名稱") if "公司名稱" in head else 1, eps_cols[0]
        for row in rows[1:]:
            c = cells(row)
            if len(c) <= eps_i or not re.fullmatch(r"[1-9]\d{3}", c[code_i]):
                continue
            try:
                eps = float(c[eps_i].replace(",", ""))
            except ValueError:
                continue
            out.append((c[code_i], c[name_i], eps))
    if not out:
        raise ValueError("沒有解析到每股盈餘欄")
    return out


def main(out, y0, y1):
    out = Path(out); (out / "raw").mkdir(parents=True, exist_ok=True)
    path, files_log = out / "eps.csv.gz", out / "files.csv"
    rows, done = [], set()
    if path.exists():
        with gzip.open(path, "rt", newline="") as f:
            for r in csv.DictReader(f):
                rows.append(r); done.add((r["market"], r["roc_year"], r["season"]))
    logs = []
    if files_log.exists():
        with open(files_log, newline="") as f:
            logs = list(csv.DictReader(f))
    for y in range(int(y0), int(y1) + 1):
        for s in (1, 2, 3, 4):
            for m in ("sii", "otc"):
                if (m, str(y), str(s)) in done:
                    continue
                url = BASE.format(m=m, y=y, s=s)
                try:
                    body = fetch(url)
                    got = parse(body)
                except Exception as e:  # noqa: BLE001
                    print(m, y, s, "error", e, flush=True)
                    logs.append({"market": m, "roc_year": y, "season": s, "url": url, "status": f"error: {e}"[:200], "rows": 0, "sha256": ""})
                    time.sleep(4)
                    continue
                name = f"{m}-{y}-{s}.html.gz"
                with gzip.open(out / "raw" / name, "wb") as f:
                    f.write(body)
                logs.append({"market": m, "roc_year": y, "season": s, "url": url, "status": "ok" if got else "no_data", "rows": len(got), "sha256": hashlib.sha256(body).hexdigest()})
                for code, nm, eps in got:
                    rows.append({"market": m, "roc_year": str(y), "season": str(s), "code": code, "name": nm, "eps_ytd": eps})
                print(m, y, s, len(got), flush=True)
                time.sleep(4)
    with gzip.open(path, "wt", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["market", "roc_year", "season", "code", "name", "eps_ytd"]); w.writeheader(); w.writerows(rows)
    with open(files_log, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["market", "roc_year", "season", "url", "status", "rows", "sha256"]); w.writeheader(); w.writerows(logs)
    print("rows", len(rows), "pages", len(logs), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
