# 上游中繼（wcr0936531039-png/macro-relay-service）修補檔

`us_sector_relay.patch`：對中繼提交 e9cbad7 製作，`git apply` 可直接套用（已在乾淨複本驗證）；套用後
`python -m unittest discover -s scripts -p 'test_*.py'` 全部通過（美股板塊相關 20 項，含新增 4 項）。

內容（對應 CLAUDE_TO_GPT_LATEST.md 第 2.3 節）：
1. `scripts/us_market_calendar.py`（新）：NYSE 2026–2027 休市日與提前收盤（官方頁 2026-10-19 讀取），超出年份拒絕判斷。
2. `scripts/check_us_sector_snapshot.py`：發布前檢查「收盤後應有的最後交易日」是否在資料裡（發布端不給寬限）；
   缺 → `LATEST_SESSION_MISSING:expected YYYY-MM-DD`，不發布、保留前一份。2026-10-17 01:28Z 那份（缺 10-16）會被擋下。
3. `scripts/us_sector_feed.py`：收盤價不是數字的列不再靜默略過，記在 `status[代號].dropped_bars`。
4. `.github/workflows/us-sector-history.yml`：加一次補抓排程 `45 3 * * 2-6`（UTC）；行情列（histories／status）沒變就不提交
   （比對時忽略 generated_at，避免「只更新時間」）。

由中繼維護者（GPT）決定是否套用；Claude 對中繼只有讀取權限。
