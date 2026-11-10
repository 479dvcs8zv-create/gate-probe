#!/usr/bin/env python3
"""集保股權分散表（大戶／散戶持股）。擁有者 2026-11-10 22:27：籌碼越集中＝股票在大戶手中、散戶越少，拉抬越輕鬆。

只讀公開資料、不使用任何金鑰；只寫入 gate-probe 的 results/tdcc/。

用法：
  python3 -I tools/tdcc_holders.py latest <輸出資料夾>
      讀集保開放資料 1-5（只有最新一週、全部股票），存原始檔與每檔摘要；同一週已存過就跳過。
  python3 -I tools/tdcc_holders.py history <代號,代號,...> <輸出資料夾>
      用集保「股權分散表查詢」頁（約最近一年的每週資料），補指定股票的歷史；每次查詢間隔 3 秒，已存過的週次跳過。

持股分級（集保官方）：1＝1～999 股 … 8＝40,001～50,000 股（≤50 張）、12～15＝400,001 股以上（≥400 張）、15＝1,000,001 股以上（≥1,000 張）、17＝合計。
摘要欄位：holders（總人數）、ge1000_pct／ge1000_holders（千張大戶）、ge400_pct（400 張以上）、le50_pct（50 張以下，散戶）。
每一份都核對：分級 1～15 的比例加總約 100%、合計列人數＝分級人數加總；不符就不存、照實列出。
"""
import csv
import gzip
import html
import http.cookiejar
import io
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

OPEN_DATA = "https://opendata.tdcc.com.tw/getOD.ashx?id=1-5"
QUERY = "https://www.tdcc.com.tw/portal/zh/smWeb/qryStock"
UA = "Mozilla/5.0 (gate-probe research; public data)"
LEVELS = range(1, 16)


def summarize(levels):
    """levels: {分級: (人數, 股數, 比例)}，含 17（合計）。回傳摘要或錯誤說明。"""
    if any(k not in levels for k in list(LEVELS) + [17]):
        return None, "缺少分級"
    pct_sum = sum(levels[k][2] for k in LEVELS)
    holders_sum = sum(levels[k][0] for k in LEVELS)
    if abs(pct_sum - 100) > 0.6 and levels[17][1] > 0:
        return None, f"分級比例加總 {pct_sum:.2f}% 不是 100%"
    if holders_sum != levels[17][0]:
        return None, f"分級人數加總 {holders_sum} ≠ 合計 {levels[17][0]}"
    return {
        "holders": levels[17][0], "shares": levels[17][1],
        "ge1000_pct": round(levels[15][2], 2), "ge1000_holders": levels[15][0],
        "ge400_pct": round(sum(levels[k][2] for k in (12, 13, 14, 15)), 2),
        "le50_pct": round(sum(levels[k][2] for k in range(1, 9)), 2),
    }, None


FIELDS = ["date", "code", "holders", "shares", "ge1000_pct", "ge1000_holders", "ge400_pct", "le50_pct"]


def latest(out):
    out = Path(out)
    req = urllib.request.Request(OPEN_DATA, headers={"User-Agent": UA})
    raw = urllib.request.urlopen(req, timeout=60).read()
    rows = list(csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
    if rows[0][:6] != ["資料日期", "證券代號", "持股分級", "人數", "股數", "占集保庫存數比例%"]:
        raise SystemExit(f"欄位不符：{rows[0]}")
    dates = {r[0] for r in rows[1:] if r}
    if len(dates) != 1:
        raise SystemExit(f"資料日期不只一個：{sorted(dates)[:5]}")
    date = dates.pop()
    if not re.fullmatch(r"20\d{6}", date):
        raise SystemExit(f"資料日期格式不符：{date}")
    target = out / "summary" / f"{date}.csv"
    if target.exists():
        print(f"{date} 已存過，跳過")
        return 0
    stocks = {}
    for r in rows[1:]:
        if len(r) < 6:
            continue
        code = r[1].strip()
        stocks.setdefault(code, {})[int(r[2])] = (int(r[3]), int(r[4]), float(r[5]))
    good, bad = [], []
    for code, levels in sorted(stocks.items()):
        s, err = summarize(levels)
        if s is None:
            bad.append((code, err))
            continue
        if s["holders"] > 0:
            good.append({"date": date, "code": code, **s})
    (out / "raw").mkdir(parents=True, exist_ok=True)
    (out / "summary").mkdir(parents=True, exist_ok=True)
    (out / "raw" / f"{date}.csv.gz").write_bytes(gzip.compress(raw, mtime=0))
    with open(target, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(good)
    print(f"{date}：{len(good)} 檔存入；{len(bad)} 檔核對不符未存" + (f"（例：{bad[:3]}）" if bad else ""))
    return 0


class Session:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.token = None
        self.dates = []

    def _open(self, data=None):
        req = urllib.request.Request(QUERY, data=data, headers={"User-Agent": UA, "Referer": QUERY})
        body = self.opener.open(req, timeout=60).read().decode("utf-8", "replace")
        m = re.search(r'name="SYNCHRONIZER_TOKEN" value="([^"]+)"', body)
        if m:
            self.token = m.group(1)
        return body

    def start(self):
        body = self._open()
        self.dates = re.findall(r'<option value="(20\d{6})"', body)
        if not self.token or not self.dates:
            raise SystemExit("查詢頁沒有 token 或週次清單")
        return self.dates

    def query(self, code, date, debug_dir=None):
        form = {"SYNCHRONIZER_TOKEN": self.token, "SYNCHRONIZER_URI": "/portal/zh/smWeb/qryStock", "method": "submit",
                "firDate": self.dates[0], "scaDate": date, "sqlMethod": "StockNo", "stockNo": code, "stockName": ""}
        body = self._open(urllib.parse.urlencode(form).encode())
        result, err = parse_result(body, code, date)
        if result is None and debug_dir is not None and not any(Path(debug_dir).glob("debug-*.html")):
            # 第一次解析失敗時留一份公開查詢結果頁，方便對欄位（只留一份）
            Path(debug_dir, f"debug-{code}-{date}.html").write_text(body, encoding="utf-8")
        return result, err


def parse_result(body, code, date):
    compact = re.sub(r"<[^>]+>", " ", html.unescape(body))
    compact = re.sub(r"\s+", " ", compact)
    shown = re.search(r"資料日期[：:]\s*(\d{8})", compact)
    if shown and shown.group(1) != date:
        return None, f"頁面資料日期 {shown.group(1)} 不是 {date}"
    levels = {}
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", body, re.S):
        cells = [re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", c))).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) != 5:
            continue
        num = lambda x: x.replace(",", "")
        try:
            holders, shares, pct = int(num(cells[2])), int(num(cells[3])), float(num(cells[4]))
        except ValueError:
            continue
        if cells[0].isdigit() and 1 <= int(cells[0]) <= 17:
            levels[int(cells[0])] = (holders, shares, pct)
        elif "合" in cells[0] or "合" in cells[1]:
            levels[17] = (holders, shares, pct)
    if 16 in levels and 17 not in levels:
        levels[17] = levels.pop(16)
    return summarize(levels)


def history(codes, out):
    out = Path(out) / "history"
    out.mkdir(parents=True, exist_ok=True)
    s = Session()
    dates = s.start()
    print(f"查詢頁週次：{dates[-1]}～{dates[0]}，共 {len(dates)} 週")
    for code in codes:
        path = out / f"{code}.csv"
        have = {}
        if path.exists():
            with open(path, newline="") as f:
                have = {r["date"]: r for r in csv.DictReader(f)}
        errors = []
        for date in dates:
            if date in have:
                continue
            time.sleep(3)
            try:
                result, err = s.query(code, date, debug_dir=out)
            except Exception as exc:  # noqa: BLE001
                result, err = None, f"{type(exc).__name__}: {exc}"[:200]
                s.start()
            if result is None:
                errors.append((date, err))
                continue
            have[date] = {"date": date, "code": code, **result}
        with open(path, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(sorted(have.values(), key=lambda r: r["date"]))
        print(f"{code}：{len(have)} 週已存；本次失敗 {len(errors)} 週" + (f"（例：{errors[:2]}）" if errors else ""))
    return 0


if __name__ == "__main__":
    mode = sys.argv[1]
    if mode == "latest":
        sys.exit(latest(sys.argv[2]))
    if mode == "history":
        sys.exit(history([c for c in sys.argv[2].split(",") if re.fullmatch(r"[0-9A-Z]{4,6}", c)], sys.argv[3]))
    raise SystemExit("mode 要是 latest 或 history")
