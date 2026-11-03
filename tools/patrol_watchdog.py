#!/usr/bin/env python3
"""台股網站巡檢看門狗（擁有者 2026-11-03 03:04「好」）。唯讀：只讀兩個公開 repo，不改任何東西、不部署、不聯絡 GPT。

用法：python3 -I patrol_watchdog.py <macro-relay-service 資料夾> <gate-probe 資料夾> [現在時間 ISO，測試用]
輸出一行 JSON：{"checkedAt", "alerts": [...], "info": [...]}。alerts 空＝正常。

檢查：
1. 巡檢紀錄：relay diagnostics/ 最後一次 GPT 寫入超過 14 小時（06:30、22:30 各跑一次，加上紀錄時間）→ 異常；
   最新紀錄標題寫 Gate 審計 n/m 且 n<m、或最新一份當輪紀錄停在「進行中」超過 2 小時 → 異常。
2. 中繼資料：data/*.json 的 generated_at 太舊 → 異常（GitHub 排程常延後或略過，門檻放寬）。
3. 交接：GPT_NEXT.md 指定的報告檔（hotfixN.md）在交接更新 24 小時後仍不存在 → 異常。
4. 官方資料收集套件（relay 的 official-import 分支，2026-11-03 起）：清單超過 30 小時沒更新 → 異常（網站超過 36 小時就不匯入）；
   分支還不存在＝尚未啟用，只列資訊。
"""
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

TPE = dt.timezone(dt.timedelta(hours=8))
FRESH_HOURS = {"keyless_snapshot.json": 20, "cb_snapshot.json": 30, "stock_snapshots_v2.json": 80, "cross_market_snapshot.json": 80, "us_sector_history.json": 100}
NAMES = {"keyless_snapshot.json": "免金鑰總經／信用中繼", "cb_snapshot.json": "可轉債中繼", "stock_snapshots_v2.json": "個股中繼", "cross_market_snapshot.json": "跨市場中繼", "us_sector_history.json": "美股板塊中繼"}


def parse_time(text):
    try:
        t = dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
        return t if t.tzinfo else t.replace(tzinfo=dt.timezone.utc)
    except ValueError:
        return None


def last_commit(repo, path, author_filter=None):
    args = ["git", "-C", str(repo), "log", "-1", "--format=%ct%x09%an%x09%s"]
    if author_filter:
        args += ["--author", author_filter]
    out = subprocess.run(args + ["--", path], capture_output=True, text=True).stdout.strip()
    if not out:
        return None
    ts, author, subject = out.split("\t", 2)
    return dt.datetime.fromtimestamp(int(ts), dt.timezone.utc), author, subject


def hours(a, b):
    return (a - b).total_seconds() / 3600


def main(relay, probe, now_text=None):
    relay, probe = Path(relay), Path(probe)
    now = parse_time(now_text) if now_text else dt.datetime.now(dt.timezone.utc)
    alerts, info = [], []

    # 1. 巡檢紀錄（GPT 寫入；bot 的資料更新不算）
    gpt = last_commit(relay, "diagnostics", author_filter="wcr0936531039")
    stale_record = False
    latest = (relay / "diagnostics" / "latest.md")
    heading = next((line.strip("# ").strip() for line in latest.read_text(encoding="utf-8").splitlines() if line.startswith("# 最新")), "") if latest.exists() else ""
    if gpt:
        age = hours(now, gpt[0])
        info.append(f"最後巡檢紀錄 {gpt[0].astimezone(TPE):%m/%d %H:%M}（{age:.0f} 小時前）：{heading[:60]}")
        if age > 14:
            stale_record = True
            alerts.append(f"超過 {age:.0f} 小時沒有巡檢紀錄（最後一筆 {gpt[0].astimezone(TPE):%m/%d %H:%M}）")
    else:
        alerts.append("找不到任何巡檢紀錄")
    # 紀錄已經過期時，舊紀錄裡的 Gate n/m 與「進行中」都併進上面那一則，不再各列一次（2026-11-03 擁有者回報看門狗重複／過時）。
    m = re.search(r"Gate\s*(?:審計|audit|快照)?\s*(\d)\s*/\s*(\d)", heading, re.I)
    if m and int(m.group(1)) < int(m.group(2)) and not stale_record:
        alerts.append(f"最近一次巡檢 Gate 只存 {m.group(1)}/{m.group(2)}")
    runs = sorted((relay / "diagnostics").glob("source-reliability-*/*-run.md"), key=lambda p: p.name)
    if runs:
        newest = runs[-1]
        first = newest.read_text(encoding="utf-8").splitlines()[0] if newest.stat().st_size else ""
        touched = last_commit(relay, str(newest.relative_to(relay)))
        if "進行中" in first and touched and hours(now, touched[0]) > 2:
            text = f"巡檢紀錄停在「進行中」：{newest.stem}（{hours(now, touched[0]):.0f} 小時沒有更新）"
            if stale_record:
                alerts[next(i for i, a in enumerate(alerts) if a.startswith("超過"))] += f"；最後一筆停在「進行中」（{newest.stem}）"
            else:
                alerts.append(text)

    # 2. 中繼資料新鮮度
    for name, limit in FRESH_HOURS.items():
        path = relay / "data" / name
        try:
            generated = parse_time(json.loads(path.read_text(encoding="utf-8")).get("generated_at"))
        except (OSError, ValueError):
            generated = None
        if not generated:
            alerts.append(f"{NAMES[name]}讀不到產生時間")
            continue
        age = hours(now, generated)
        if age > limit:
            alerts.append(f"{NAMES[name]}已 {age:.0f} 小時沒更新（GitHub 排程可能被略過）")

    # 4. 官方資料收集套件。排程用 --depth clone 只會帶 main，所以這裡另外抓這個分支（抓不到＝分支還不存在）。
    subprocess.run(["git", "-C", str(relay), "fetch", "-q", "--depth", "1", "origin", "+refs/heads/official-import:refs/remotes/origin/official-import"], capture_output=True, text=True)
    shown = subprocess.run(["git", "-C", str(relay), "show", "origin/official-import:manifest.json"], capture_output=True, text=True)
    if shown.returncode == 0:
        try:
            manifest = json.loads(shown.stdout)
            generated = parse_time(manifest.get("generatedAt"))
        except ValueError:
            manifest, generated = {}, None
        if not generated:
            alerts.append("官方資料收集套件的清單讀不到產生時間")
        else:
            age = hours(now, generated)
            kinds = sorted({p.get("kind") for p in manifest.get("parts") or []})
            info.append(f"官方資料收集套件 {generated.astimezone(TPE):%m/%d %H:%M}（{age:.0f} 小時前）：{'、'.join(kinds) or '無'}；收集失敗 {len(manifest.get('errors') or [])} 項")
            if age > 30:
                alerts.append(f"官方資料收集套件已 {age:.0f} 小時沒更新（網站超過 36 小時就不匯入）")
    else:
        info.append("官方資料收集套件：分支尚未建立（中繼 patch 還沒套用）")

    # 3. 交接是否有人處理
    handoff = probe / "handoff" / "GPT_NEXT.md"
    if handoff.exists():
        text = handoff.read_text(encoding="utf-8")
        block = text.split("## ★ 本輪工作", 1)[-1].split("<details>", 1)[0]
        updated = last_commit(probe, "handoff/GPT_NEXT.md")
        report = re.search(r"寫\s*`(diagnostics/[^`]+\.md)`", block)
        if report and updated:
            info.append(f"交接更新 {updated[0].astimezone(TPE):%m/%d %H:%M}，等待報告 {report.group(1).rsplit('/', 1)[-1]}")
            if not (relay / report.group(1)).exists() and hours(now, updated[0]) > 24:
                alerts.append(f"GPT 超過 {hours(now, updated[0]):.0f} 小時還沒交 {report.group(1).rsplit('/', 1)[-1]}")

    print(json.dumps({"checkedAt": now.astimezone(TPE).isoformat(timespec="minutes"), "alerts": alerts, "info": info}, ensure_ascii=False))


if __name__ == "__main__":
    main(*sys.argv[1:4])
