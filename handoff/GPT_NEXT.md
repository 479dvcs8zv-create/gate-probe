# GPT 下一個工作（一次只做這一項；只讀這份，不必讀 CLAUDE_TO_GPT_LATEST.md 全文）

更新：2026-10-27 06:40 台北（Claude）

**目前狀態**：①～⑤ 已完成（v239；`hotfix3.md`，Claude 已核對：D／C／E 的 SHA、數字都對）。**只剩 ⑥**：G 中繼美元指數 → F2 網站（美元零軸自動化＋你 v239 讀回的 3 個缺口，部署一次）→ 讀回寫 `diagnostics/deploy-20261026/hotfix4.md`。巡檢那行照舊等排程跑完寫 `patrol-enabled.md`。

## 現在：⑥ G＋F2（**已授權**：擁有者 10-27 04:56「好」＝美元；另 3 項是 v239 讀回缺口的修正，不改任何規則、門檻、評級、Gate、風險預算）
### G. 中繼：keyless 多抓 FRED DTWEXAFEGS（未變）
- `handoff/patches/relay-dollar-20261027.patch`，SHA-256 `564ccd5e02d74901007d8c8c41f146f8eecbeb79e22dee46ec044d89a3bf0fd6`（1 個 commit）。Claude 06:30 在最新 main `cc3ac0a` 重放 `git am` 無衝突、35/35 通過。
- 推上 main（keyless 工作流程自動跑）→ 確認 `data/keyless_snapshot.json` 有 DTWEXAFEGS（status ok、40 筆）。

### F2. 網站（一次部署，v239 留回滾）
- Patch：`handoff/patches/v239-dollar-fixes-20261027.patch`，SHA-256 `3f4f587755179970fd58b828b9f62717f4c919fa687c2c336737a5774ae4f73a`；**取代 F（009479c5…，不要再套）**。基線＝v239 來源（你的 e954f6b＝Claude tag e-patch-head）。不含 dist/server/index.js。
- 內容：
  1. 美元零軸（原 F）：外部匯入沒有或超過 36 小時 → 讀中繼的 DTWEXAFEGS（中繼也過期就不用，維持「待補」）；卡片註明「GitHub 排程代抓的 FRED 官方檔」。
  2. 可轉債代抓註記（你回報的缺口）：`panel-site.js` 組裝個股資料時把清單與月報的 `capturePath` 丟掉了，所以「清單代抓、月報直連」時畫面不寫代抓。改為帶到個股資料；卡片寫出哪一份是代抓：「櫃買清單：…」「觀測站月報：…」或「櫃買清單、觀測站月報：…網站直連失敗，改用 GitHub 排程代抓的同一份官方檔（保存 SHA-256）」。
  3. IORB 被拒（你回報的缺口）：收集程式用**本機日期**判斷「不得晚於今天」，網站匯入用 **UTC 日期**；台北凌晨跑時 FRED 已列出 10/27 的 IORB，收集程式放行、網站整筆 `invalid_series_history`。收集程式改用 UTC 日期（FRED 序列、核心 CPI、上市日期同一處理），UTC 明天的觀測不送。網站的檢查不放寬。
  4. 舊快取（你回報的「除權息資料未接入（舊快取）」）：E 之前存的個股快照沒有 `exRightsEvents`，6 小時內仍算新，所以均線排列、出場訊號沒還原除權息。現在這種舊版快照照樣先顯示，但背景重抓一次；巡檢也把它當成需要更新。Claude 用網站同一個函式核對：你回報的 5009 數字（5/10/20/120 日 33.89／33.86／33.2125／34.06625）正是**未還原**值；5009 在 2026-06-29 除息（官方參考價推得現金約 1.2 元），還原後半年線約 33.63，5、10 日線都在 20 日線與半年線之上 → 排列強 → 應回到「可進場」。
- 測試：新增 `tests/v239-fixes.test.mjs` 3 項（舊程式 3 項都失敗）＋`tests/v239-collector-utc.test.mjs` 1 項（選一個本機日期≠UTC 日期的時區，跑真的收集程式；舊程式失敗），併入 `test:v235-hotfix`；`site-automation` 測試的個股快照改成新版格式（含 `exRightsEvents`）。Claude 在乾淨「v237＋C＋E」重放無衝突、完整 `TZ=UTC npm test` exit 0；`dist/index.html` SHA-256 `05c731ec5cece149e4c68daa25f7906b029bec17f0fc4455da25d0c13e874334`。
- 步驟：G 推上並確認 DTWEXAFEGS → `git apply` F2 → `node build.mjs` → `TZ=UTC npm test` → 部署一次 → 用 patch 裡的新版 `scripts/collect-official-data.py` 跑一次官方資料收集並匯入。

### 讀回（15 行內，`diagnostics/deploy-20261026/hotfix4.md`）
- G：工作流程 success；`keyless_snapshot.json` 的 DTWEXAFEGS status、筆數、最新日期。
- 美元：8299 美元零軸卡有數值與圖；來源註記（官方匯入或 GitHub 代抓）。
- 可轉債：8299 卡片依當次實際來源寫出「櫃買清單／觀測站月報：網站直連失敗，改用 GitHub 排程代抓…」（全部直連就不寫）；群聯三 2,468.8 不變。
- IORB：新版收集程式匯入後被接受（最新日期 ≤ UTC 今天），不再 `invalid_series_history`。
- 舊快取：清單上每檔開一次、約 1 分鐘後再開一次：不再出現「除權息資料未接入（舊快取）」；5009 進場條件與均線排列（預期可進場／排列強，寫出還原後半年線）；8299／5289／2404 出場訊號與還原後 20 日線。
- 每檔評級、Gate 狀態、風險預算與部署前相同。

## 已完成（00:48）：啟用每日巡檢（2026-10-26 21:25 擁有者授權）
- 擁有者 21:25「好開啟」：可轉債只顯示、不影響評級／Gate，**不再等②通過**；現在就把「台股整站每日巡檢」改為 is_enabled=true（06:30／22:30 時段不變）。
- 啟用後下一次排程跑完，回報一行到 `diagnostics/deploy-20261026/patrol-enabled.md`：runId、完成時間、狀態、Gate 審計 N/N、`watchlistSource` 與檔數（擁有者打開網站後應為 `latest_synced`）。
- 可轉債改由 GitHub 代抓：已寫好（下方 D＋C），已授權。

> 23:30：22:55 擁有者追加的籌碼提示、財報警示、5／10／20 日強弱與趨勢已併進 C（SHA 如下），可以開始。

## 已完成（v238，10-27 01:0x；hotfix3.md）：D 中繼＋C 網站 v237 補修＋兩條核准規則
順序：先 D（中繼）並手動跑一次，確認 `data/cb_snapshot.json` 有資料，再做 C（網站）。

### D. 中繼：可轉債官方檔由 GitHub 代抓
- Patch：`handoff/patches/relay-cb-snapshot-20261026.patch`（`git format-patch`，1 個 commit），SHA-256 `7b7eff0d2a2b8c652a5287bf7b97771a6025dc06202fa847d3c21baf6e1953cd`。在 macro-relay-service `git am` 後推上 main。只新增檔案（`scripts/sync_cb.py`、`tests/test_cb_snapshot.py`、4 個真實官方檔 fixture、`.github/workflows/cb_snapshot.yml`），不改既有程式與資料。
- 內容：每天台北 08:47、17:47 抓櫃買 bond_ISSBD5／ISSBD6（只留網站用到的 15 欄）與 cbnote 索引列出的最新觀測站 CBTRN 月報（解析成 債券代號→發行公司、轉換價、重設日），保存原始回應 SHA-256；某部分失敗就沿用上次那份並保留原抓取時間。輸出 `data/cb_snapshot.json`（約 150 KB）。
- 測試：Claude 在最新 main 51b089c 上 `git am` 後 `python -m unittest discover -s tests` 34/34 通過（新增 3 項，用 10-26 真實官方檔；群聯三 2,468.80、115/07/06 重設）。
- 推上後到 Actions 手動執行「CB registry relay」一次。

### C. 網站 v237 補修（一次部署，v237 留回滾）
- Patch：`handoff/patches/v237-fixes-20261026.patch`，SHA-256 `1c99ff63a66363524f62387dd1829088a4f6babb84e67199e90723ce3abf5fd0`（取代 5845b908…、ccc0cd4f…）；基線＝v237 來源（＝Claude 的 cb1472d）。不含 dist/server/index.js。
- 內容：
  1. 可轉債：櫃買／觀測站直連失敗（或 20 分鐘內失敗過）就讀 `raw.githubusercontent.com/wcr0936531039-png/macro-relay-service/main/data/cb_snapshot.json`；來源網址必須是官方原網址、抓取時間 36 小時內、有 SHA-256，否則不用。卡片註明「網站直連失敗，改用 GitHub 排程代抓的同一份官方檔」。仍只顯示、不計分。
  2. 缺收盤分類：外部收集程式 `scripts/collect-official-data.py` 送出 `notQuotedRows`；匯入時驗證（不得帶價格、不得與有行情者重複），`missingBreakdown` 由網站重算、不信任送來的計數。
  3. M1B−M2：網站有效天數 75 → 95 天，與中繼一致（你回報的快取重讀誤判過期）。
  4. **大盤持股（擁有者 21:51 核准「看方向」，第 33 輪 D10）**：65% 為基準；台股總經分數 20 日平均比 60 個交易日前高 5 分以上 → 75%，低 5 分以上 → 55%，其餘 65%。網站每天（加權指數交易日、總經資料齊時）記錄分數到 `macro-score-daily:v1`；累積不足 80 天的部分用第 31 輪重建的 100 天分數（程式內常數，已標明），同一天以網站實際記錄為準。顯示在個股決策區「大盤持股建議」，取代原本「待門檻核准」。以 10-22 的重建分數算：20 日平均 64.5、60 日前 60.1，差 +4.4 分 → 65%。
  5. **個股進場條件（擁有者 21:51 核准，第 33 輪）**：技術強（三問技術過且均線強弱 ≥ +3）＋近 3 個已公布月份營收年增率平均 > 10% → 可進場；技術不過 → 避開；其餘 → 觀望；資料不足（含最新營收超過 75 天未更新）→ 不判斷。新卡片「進場條件（擁有者核准）」；巡檢 Gate 審計每檔多記 `entry` 與 `holdingTarget`。**不改評級、Gate、風險預算**。
  6. **進場卡提示（擁有者 22:53 核准）**：投信 20 日淨買 ÷ 20 日成交金額 > 0.3% → 加分提示；借券賣出餘額 20 日增加 × 收盤 ÷ 20 日成交金額 > 1.1% → 警示（門檻＝第 32 輪每個評估日前 1/5 界線的中位數）；營業現金流／淨利為負、自由現金流為負 → 財報警示；短線強弱（5、10 日線）與趨勢（20 日線）狀態；觸發否決紅線 → 進場條件改「避開」。提示與警示不改「可進場／避開／觀望」。借券 20 日變化要網站累積滿 21 個交易日的借券紀錄才會出現（目前顯示資料不足）。
- 測試：新增 `tests/v237-cb-relay.test.mjs` 3 項（fixture＝中繼程式用真實官方檔產生的輸出）＋`tests/v237-fixes.test.mjs` 2 項＋`tests/v237-rules.test.mjs` 4 項，併入 `test:v235-hotfix`；`financial-analysis` 加檢查決策區用 D10、個股有進場條件；`official-collector`、`convertible-bonds` 測試已同步。Claude 在乾淨 v237 重放無衝突、完整 `npm test` exit 0；`dist/index.html` SHA-256 `8c6835709cffcd58898b4604736a6cacc7b72a5fb085aad54c81b8eaa386f377`。
- **外部收集程式要用新版**：部署後照 OPERATIONS.md 跑收集程式時，用這份 patch 裡的 `scripts/collect-official-data.py`。

### 讀回（報告 20 行內，`diagnostics/deploy-20261026/hotfix3.md`）
- D：工作流程 success；`cb_snapshot.json` 的 domestic／overseas 列數、monthly 月份與檔數、errors。
- C：開 8299 最多 3 次（間隔 30 秒）：可轉債 3 檔、群聯三「目前轉換價 2,468.8（觀測站 2026-09 月報，2026-07-06 重設）」、海外兩檔「未含後續調整」；卡片是否寫 GitHub 代抓。
- 下一次匯入官方行情後：市場摘要 `missingBreakdown` 不是 null（寫出三類數字）、巡檢文字有「當日無收盤價 N 檔」。
- M1B−M2：快取重讀仍是 ok／snapshot，不變 stale。
- 大盤持股：開任一檔，決策區顯示「大盤持股建議：65%」與 20 日平均、60 日前、變化分數，及「重建分數 N 天、網站實際記錄 M 天」；`macro-score-daily:v1` 有當天（加權指數日期）一筆。
- 進場條件：四檔各自的「進場條件」狀態與理由（可進場／避開／觀望／資料不足），短線／趨勢狀態、投信 20 日數字、出現的提示與警示；巡檢 Gate 審計的 `entry`、`holdingTarget`。

## 已完成（v239，10-27 05:58；hotfix3.md）：E 出場訊號＋均線排列
- Patch：`handoff/patches/v238-exit-signal-20261026.patch`，SHA-256 `c3d95887d273c33b6aa2142261e07bf1cd9aae4b3ca2140805f7ffcb538232f1`（取代 0cd967c4…）；基線＝**套完 C 之後**的來源（Claude 的 tag c-patch-head）。不含 dist/server/index.js。
- 內容：進場卡加「出場訊號」：收盤跌破 20 日線 → 「▼ 出場訊號：若持有，出場」，否則「續抱」（第 34 輪：每筆平均 +1.25%、平均抱 13 天、最差 5% 交易 −9.7%）。20 日線用**還原除權息**的收盤（股票資料新增 `exRightsEvents`：FinMind TaiwanStockDividend 的現金／股票除權息日與金額，近兩年），避免除息當天被誤判成跌破；舊快取沒有這欄時註明「除權息資料未接入」。巡檢 Gate 審計的 `entry` 多記 `exit`。只顯示，不改評級、Gate、風險預算。
- 另含（第 35 輪，擁有者 23:28 核准）：**均線排列**——強＝5、10 日線都在 20 日線與半年線（120 日）之上；弱＝都在 20 日線下或都在半年線下；中＝其餘（還原除權息）。「可進場」改為**技術強＋營收成長＋排列強**；排列弱或中 → 觀望，排列弱另顯示警示；半年線不足 120 筆 → 資料不足。進場卡**分成兩個區塊**：「進場條件」（可進場／避開／觀望、技術、營收、排列、籌碼與財報提示）與「持有與強弱」（出場訊號、均線排列與 5／10／20／半年線數值、短線強弱、趨勢）。
- 測試：新增 `tests/v238-exit.test.mjs` 3 項（含除息 5 元不誤判），`tests/v237-rules.test.mjs` 改成要求排列強並新增排列弱→觀望、半年線不足→資料不足；Claude 在「乾淨 v237＋C」重放無衝突、完整 `npm test` exit 0；`dist/index.html` SHA-256 `a59e8f6ec8508ec2a71d4fbf1785cb53d2d0be0b38ef3018cbe9815a6321ba53`。
- 步驟：C 讀回完成後 → `git apply` → `node build.mjs` → `TZ=UTC npm test` → 部署一次（留上一版回滾）。
- 讀回（併入 `hotfix3.md` 末尾，6 行內）：四檔畫面是否分成兩個區塊；各檔進場條件、均線排列（強／中／弱）、出場訊號狀態與理由（收盤、還原後 20 日線）、是否有「已還原…」或「除權息資料未接入」註記。

## 已被 F2 取代（保留供對照，F 不要再套；G 照用）：美元零軸自動化
- 原因：擁有者 10-27 04:49「美元圖片也沒有出來」。美元零軸只讀外部匯入的 `official-series:v1:DTWEXAFEGS`，且只用 36 小時內的；外部收集程式沒跑就整張圖消失。
- **臨時處理（現有例行作業，不改程式）**：照 OPERATIONS.md 跑一次官方資料收集程式並匯入（C 部署後用 patch 裡的新版 `scripts/collect-official-data.py`），DTWEXAFEGS 就會回來。
- G（中繼）：`handoff/patches/relay-dollar-20261027.patch`，SHA-256 `564ccd5e02d74901007d8c8c41f146f8eecbeb79e22dee46ec044d89a3bf0fd6`（1 個 commit）：keyless 每 6 小時多抓 FRED DTWEXAFEGS，保留 40 筆（max_age 12 天）。Claude 在最新 main 上 `git am` 後 35/35 通過。
- F（網站）：`handoff/patches/v238-dollar-relay-20261027.patch`，SHA-256 `009479c5c2c4f438040fa9e6a6659baf5e526a9bd2457881b744e8d66db2ae9c`；基線＝**套完 C、E 之後**（Claude tag e-patch-head）。外部匯入沒有或超過 36 小時 → 讀中繼的 DTWEXAFEGS（中繼也過期就不用，維持「待補」）；卡片註明「GitHub 排程代抓的 FRED 官方檔」。新增 `tests/v238-dollar.test.mjs` 2 項；乾淨「v237＋C＋E」重放 `npm test` exit 0；`dist/index.html` SHA-256 `c07faa71ff2015999621a7b72b98a932cff1c0004974afedbd7b1108b14605b4`。
- 順序：G 推上 main（keyless 工作流程會自動跑）→ 確認 `keyless_snapshot.json` 有 DTWEXAFEGS 40 筆 → F 部署 → 讀回：8299 美元零軸卡有數值與圖、來源註記。

## 已完成：10-25 三項修補 → **v234**（2026-10-25 19:58 台北部署，三項讀回 PASS；v233 回滾點；報告 `diagnostics/deploy-20261025/report.md`）
- 待跨日驗收：10/27 22:30 新信用被接受、10/28 上午 verifiedAt 保留、10/22 升 final（Claude 10/28 08:30 核對）。

## 已完成：兩包 → **v235**（10-26 05:34 部署；SHA 全對、npm test exit 0；報告 `diagnostics/deploy-20261026/report.md`）
- 讀回 ①③⑤ PASS；②④ FAIL、⑥ PARTIAL；手動巡檢 partial、Gate 審計 4/4 step_timeout；每日巡檢保持停用（正確）。

## 已完成：v235 修補 → **v236**（10-26 08:0x；報告 `diagnostics/deploy-20261026/hotfix.md`）
- ① Gate 審計 4/4 recorded、無逾時 PASS；③ 國發會 49.68 PASS；② 可轉債仍 `CB_REGISTRY_STILL_LOADING` FAIL；每日巡檢保持停用（正確）。

## 已完成（v237，10-26 夜）：兩份修補 A、B（保留供對照，不要重套）
**授權**：擁有者 2026-10-26 08:49「授權」（可轉債修補）＋08:55「m1 資料來源補齊、小項也處理」＋09:13「好」（IORB 未來日期、巡檢模組 pending）＋09:30「好」（產業研究來源、缺收盤分類、重大訊息識別）＋09:55（巡檢要自動跟著追蹤清單，持股會變成 1 檔或 5 檔）＋10:02「剩下的做完」（EIA、日圓時效統一）。**擁有者 10-26 19:28：GPT 已有額度，可以開始做 A、B。**

### A. 網站 v236 修補（一次部署）
- Patch：`handoff/patches/v236-fixes-20261026.patch`，SHA-256 `f6479e9ed71886fd3f878252db42fcb8917abb3ea5953fe02641a4e40a7fa25f`（**取代**先前的 0563b78c…、f610cbc4…、39f976bf… 與 v236-cb-keepalive；同檔名已覆蓋）。基線＝v236 來源（你的 88f5f89＝Claude 重放 3c2a5e0）。不含 dist/server/index.js。
- 內容：
  1. 可轉債：7 秒沒趕上的來源交給 `ctx.waitUntil` 跑完並寫快取（巡檢 Gate 步驟傳 `{panelWaitUntil}`，只給面板來源用）；櫃買／觀測站／集保／證交所面板請求帶瀏覽器式 User-Agent；櫃買本文中斷重試一次。（實測：無 UA 5.3 秒、有 UA 1.1 秒；連續第二次請求本文傳到一半中斷。）
  2. C2 估值分歧分兩種說法（仍未評、風險限制不變）：當期來源彼此在 2 倍內、差距只來自歷史常態 → 「獲利遠高（低）於過去常態，屬景氣高峰（谷底）位置的風險」；否則 → 「各來源 EPS 互相分歧，需用財報與法說核對」。新增欄位 `divergenceKind`、`currentRatio`。
  3. 巡檢模組狀態：快照在本次巡檢開始後更新過，即使背景又開始下一次更新，也記為已更新（`refreshedThisRun:true`）；快照早於本輪才維持 pending。（你兩次報告「市場／貴金屬 pending 36/36、美股指數 pending 3/3」：資料齊全，但快取只有 5 分鐘，巡檢跑到最後讀回時又開始下一次背景更新。）
  4. 產業研究（TrendForce）：請求帶 User-Agent（不帶或 Node 預設 "node" 會 403，GitHub 實測帶上就 200；8299 半導體來源的 403 就是這個）；分類頁日期「8 October 2026」改用 UTC 解析（原本 `Date.parse` 依執行環境時區，台北時區會差一天、網址日期對不上而整頁 0 筆；消費電子 RSS 目前 0 則，全靠分類頁）。
  5. 全市場快照缺收盤分三類保存、不補價：`noTradeRows`（零成交）、`volumeRows`（只有零股成交）、新增 `notQuotedRows`（名冊有、當日行情表沒有，多為停止買賣）＋`missingBreakdown`；巡檢文字多一句「當日無收盤價 N 檔，皆為官方狀態…」。（10/22 實查：零成交 26、只有零股 5（1341、1441、1538、1583、2321）、未列入 5（1516、1589、6142、4804、8047）。）
  6. 重大訊息識別：官方 t187ap04_L／O 沒有「序號」欄，原本退回用標題當識別；改用官方欄位 公司代號＋發言日期＋發言時間（6 碼），另存 `announcement_time`、`fact_date`、`clause`、`official_key`、`id_basis`。官方沒給時間才用標題並註明。
  7. 巡檢清單自動跟隨追蹤清單：原本沒有登入身分的巡檢（排程用服務憑證）一律用內建 4 檔，網站狀態列也寫「私人清單與後台巡檢清單分開」。現在擁有者每次同步追蹤清單（搜尋加股、刪股）時另存 `site-watchlist:v1:latest-synced`（只有代號、名稱、產業），沒有登入的巡檢讀這份；從沒同步過才用內建。這版上線前就存好的清單，擁有者打開網站讀一次清單就會補存。巡檢紀錄新增 `watchlistSource`（`signed_in_user`／`latest_synced`／`built_in_default`）與 `watchlistSyncedAt`，狀態列顯示來源。仍是每次最多 6 檔輪替。
  8. 時效規則統一：**EIA 原油庫存**從官方發布日起有效、到官方「下一期發布日」為止（EIA 頁面同時寫 Release Date／Next Release Date；只有發布日時＋7 天、假日再 1 天；FRED／中繼沒附發布日時按排程「週末日後的週三」推算並標 `releaseDateBasis`）。即時抓取、中繼快照、快取重讀都用同一個 `eiaWeeklyCurrent`（原本分別是觀測日＋12 天、中繼 14 天）。例：10/15 是哥倫布日延後的週四發布，舊規則 10/15 當天會誤判過期。**日圓代理**：ECB 參考匯率三處上限統一為 5 天（原本 7／5／7）；Frankfurter 只是轉載 ECB、非官方網域，改為只顯示匯率（`officialSource:false`），不算日圓波動率、不計分；FRED 與 ECB 官方來源不受影響。
- 測試：新增 `tests/v236-sources.test.mjs` 3 項（用 10-26 真實 TrendForce 分類頁與 t187ap04 官方資料；台北時區下舊寫法確認 0 筆、新寫法 5 筆）＋`tests/v236-watchlist.test.mjs` 3 項＋`tests/v236-time-rules.test.mjs` 4 項（用 10-26 真實 EIA 頁面），都併入 `test:v235-hotfix`；`tests/macro-market-state.test.mjs` 的 Frankfurter 波動率與 EIA 到期日斷言已改成新規則。
- Claude 在乾淨 v236 重放：無衝突、完整 `npm test` exit 0；`dist/index.html` SHA-256 `0e7f91e68ce7cd08a1bc143f99179f17f8218414d30342ded460ac1b829c07b2`。
- 步驟：`git apply` → `node build.mjs` → `TZ=UTC npm test` → 部署一次（v236 留回滾）。

### B. 中繼 macro-relay-service：M1B−M2 改由排程代抓（不用部署網站）
- Patch：`handoff/patches/relay-cbc-m1b-20261026.patch`（`git format-patch`，SHA-256 `65e8150fad72099b7d3bd699bc81aa19e49d58140d2a915e58054daea7bc9ddb`，**三個 commit**，取代 1852ccc6…），在 macro-relay-service 用 `git am` 套用後推上 main；推送會觸發 keyless 工作流程（先跑 unittest 再發布）。
- 內容：`sync_keyless.py` 新增 `TW_M1B_M2`：抓央行「貨幣總計數」頁（M1B、M2 日平均年增率）＋同頁 `ms.ods` 歷史互相核對，發布近 24 個月 M1B−M2（max_age 95 天）；網站 `loadExpandedSeries` 會先讀這份中繼。網站 Worker 直連央行常被擋、目前停在舊快照 −0.14。另外**移除經濟部外銷訂單**抓取（每輪 403；網站已改國發會），並從快照刪掉舊值。第二個 commit：IORB 是聯準會提前公布的下一營業日利率，FRED 會列未來日期；原本 `validate` 把未來日期當過期（快照裡 IORB 一直 stale），改成 IORB 允許最多 4 天後。第三個 commit：EIA 原油庫存另存 `release_date`、`next_release_date`、`raw_thousand_barrels`、`page_sha256`（從同一頁解析；日期不合理就不寫）。
- 測試：新增 `tests/test_cbc_money.py` 4 項（用 10-26 的真實央行頁面）＋IORB 1 項；新增 `tests/test_eia_release.py` 2 項（10-26 真實 EIA 頁面）；Claude 在乾淨 850e87e 上 `git am` 後 `python -m unittest discover -s tests` 31/31 通過；patch 不改 `data/` 資料檔（舊的 TW_EXPORT_ORDERS 由程式在發布時移除），19:35 已在最新 main d337fad 重放 `git am` 無衝突、31/31 通過；也用真實 ms.ods 驗過：1983-01～2026-08 共 524 個月，2026-08 = −0.14（6.65 − 6.79）。

### 讀回（報告 25 行內，`diagnostics/deploy-20261026/hotfix2.md`）
- A 部署後手動巡檢一次，然後開 8299 最多 3 次（間隔 30 秒）：① Gate 審計 N/N recorded、無逾時（N＝本次巡檢檔數，跟著追蹤清單，最多 6）；② 可轉債 3 檔、群聯三「目前轉換價 2,468.8（觀測站 2026-09 月報，2026-07-06 重設）」、海外兩檔「未含後續調整」，失敗就寫 reason／errors；③ 外銷訂單仍是國發會 49.68；④ 8299 估值分歧文字出現「類型：」，評級仍未評；⑤ 巡檢最終讀回的市場／貴金屬、美股指數若快照是本輪更新，狀態為 ok 並有 `refreshedThisRun`；⑥ 8299 產業研究來源不再 403（TrendForce 半導體有筆數）、消費電子來源 ok；巡檢文字有「當日無收盤價 N 檔」那句（寫出三類數字）；⑦ 總經 WCESTUS1 有 `validThrough`（應為官方下一期發布日）與 `releaseDateBasis`；日圓若走 Frankfurter，JPY_HV20／60 為 `unofficial_source`（走 FRED／ECB 則照常）；⑧ 請擁有者部署後打開網站一次，下一次排程巡檢的 `watchlistSource` 應為 `latest_synced`、`watchlist` 等於擁有者的追蹤清單（寫出檔數與代號）。
- B 推送後：keyless 工作流程通過；`data/keyless_snapshot.json` 有 `TW_M1B_M2`（status ok、最新月份與值）、IORB 為 ok，沒有 `TW_EXPORT_ORDERS`；WCESTUS1 有 `release_date`／`next_release_date`；網站總經 TW_M1B_M2 改讀中繼、不再是舊快照。
- ①②③ 都通過就啟用每日巡檢（擁有者 10-26 01:01 已授權）；②失敗就保持停用，由 Claude 改用 GitHub 排程代抓可轉債。

## 已完成（v235）：第二修改包內容（保留供對照，不要重套）
- Patch：`handoff/patches/owner-bundle2-20261025.patch`（SHA-256 `f5068830…c334`），**疊在 owner-bundle-20261025.patch 之後**，不含 dist/server/index.js。
- 內容（全部只顯示，`scoreContribution=0`，不改評級／Gate／風險預算）：
  1. 法人買賣超 5／10／20 日（用既有法人資料）。 2. 殖利率歷史區間（同 P/B 的 FinMind PER 資料，需 250 筆）。 3. RSI(14)（Wilder，需 60 個交易日）。 4. Beta（對加權指數，近 120 個共同交易日；用既有跨市場 TAIEX 歷史）。
  5. 集保千張以上大戶（集保 open data `getOD.ashx?id=1-5` 每週；全市場一份快取約 340KB/12 小時，每檔保留 12 週；**從上線起累積，滿 4 週才有 4 週變化**）。
  6. 大盤融資維持率（上市，估算）＝Σ融資今日餘額×1000×同日收盤÷融資金額；證交所 STOCK_DAY_ALL＋MI_MARGN 必須同一日，否則顯示上一筆（10 日內）或待補。
  7. 金價改看漲跌（C3）：標題「金價漲跌｜交叉確認」，顯示 1／5／20 日漲跌，金銀比降為輔助。
  8. 可轉債**目前轉換價**自動抓：櫃買 `www/zh-tw/bond/cbnote?response=json` 取最新月份連結 → 觀測站 `mopsov.twse.com.tw/nas/t120/CBTRNyyyymm.htm`（Big5 月報，全市場約 395 檔國內債）；國內債改用月報轉換價計算價內外與稀釋，海外債仍用發行時轉換價並標「未含後續調整」。卡片標題改「可轉債（櫃買＋觀測站自動）」。
- 新增官方網址（測試白名單已加）：opendata.tdcc.com.tw、openapi.twse.com.tw STOCK_DAY_ALL、twse MI_MARGN、tpex bond/cbnote、mopsov /nas/t120/CBTRN*.htm。
- Claude 已在「v234＋owner-bundle」乾淨重放上再套本包：無衝突，`dist/index.html` SHA-256 `2b707b79…7544`，完整 `npm test` exit 0（新增 `test:owner-bundle2` 9/9）。用 10/22 真實官方檔驗算融資維持率＝**176.99%**（與凱基、財經M平方、愛玩股公布值一致）；集保 8299 千張大戶＝**26.79%**（10/22）；觀測站 9 月報群聯三＝**2,468.80**（115/07/06 重設），395 檔全數解析。
- 讀回（併入同一份報告）：⑥四檔新卡片都出現；8299 集保 26.79%（2026-10-22，1 週）；融資維持率在 10/27 收盤前部署應為 176.99%（2026-10-22）；金價卡標題與 1／5 日漲跌；8299 可轉債卡：群聯三「目前轉換價 2,468.8（觀測站 2026-09 月報，2026-07-06 重設；發行時 2,488）」、海外兩檔「發行時轉換價…（未含後續調整）」、全部價外；四檔評級、Gate 仍不變。

## 已完成：來源 zip（taiwan-master-v233-488b8bc-source.zip，SHA-256 0a49b604…7673，私下交付擁有者）
（以下為當時要求，保留供對照）
- 把網站來源 **commit 488b8bc（v233，尚未套 final.patch）** 打包成一個 zip 交給擁有者下載（**不要放進任何公開 repo**）。
- 包含：全部原始碼與測試（worker/、tests/、build.mjs、package.json、package-lock.json、dist/index.html、遷移檔等，能在乾淨環境 `npm ci && npm test`）。
- 排除：任何金鑰／.env／憑證、`dist/server/index.js`（生成檔，含私人操作說明）、node_modules、私人網址與專案代號。
- 附檔案清單與每個檔的 SHA-256；在 report.md 寫一行 zip 的 SHA-256。
- 之後流程：Claude 用這份來源寫好功能＋測試、自己跑完整 `npm test`，把 patch 放 gate-probe；GPT 只要套用、跑測試、擁有者授權後上線。

## 回報方式（省額度）
- 只寫一個檔：`diagnostics/deploy-20261026/report.md`，40 行以內；附兩份 patch SHA、部署版本號、讀回①～⑥結果、npm test 是否 exit 0、dist/index.html SHA。
- 不要每一步各開一個 commit；完成後一次提交。

## 之後的排隊——**由 Claude 寫程式，GPT 不要自行開始**（Claude 拿到來源 zip 後逐項寫好、測完，放 patch 並更新本檔，GPT 只套用與上線）
**通則：新資料一律做成網站自動抓取、任何代號通用；Claude 或 Gemini 查到的數字只當驗收對照，不寫進網站。**
1. ~~汰弱留強三問~~、~~可轉債~~、~~美元零軸~~、~~外銷訂單~~ → 已併入「擁有者 10-25 修改包」。
2. ~~免費資料缺項（法人、殖利率、RSI、Beta、集保大戶、融資維持率）~~ → 已寫成「第二修改包」。
3. Gate 4 可轉債——**網站自動查詢帶入，任何代號通用**（擁有者 10-25 15:06：要未來自動查詢帶入，不是靠 Claude 搜尋帶入）：
   - 每次巡檢與切換個股時，自動抓櫃買 OpenAPI `bond_ISSBD5_data`（國內）、`bond_ISSBD6_data`（海外），用 IssuerCode 篩出該股所有流通中可轉債；上市、上櫃股票都適用。
   - 顯示每檔：流通餘額、發行時轉換價、可轉換期間、賣回日、價內／價外（對最新收盤）、潛在稀釋股數占股本（官方發行股數；海外債用契約固定匯率，取不到就標「待核」）。
   - 現行（調整後）轉換價：找官方可自動取得的來源（公開資訊觀測站「調整轉換價格」公告）；自動取不到時標「發行時轉換價，未含後續調整」，不得手動填值。（已找到並寫入第二修改包：櫃買 cbnote → 觀測站 CBTRN 月報。）
   - 清單裡查不到的舊債（例如已轉換完的群聯二）顯示「無流通餘額」，不沿用舊資料。
   - `results/cb/8299-2026-10-25.md` 只是 Claude 手動查的**驗收對照**（群聯應自動抓到 3 檔：群聯三 2,488、海外 A 3,418.75、海外 B 3,555.50），不是要匯入的資料。
（Gemini 第二意見的比對改由 Claude 做，GPT 不用處理。）
（GPT 讀不到擁有者的 Google 雲端硬碟；Gemini 的資料一律由 Claude 讀取後轉存到 gate-probe，例如 `results/second-opinion/8299-2026-10-22.md`。GPT 不必、也不要嘗試讀雲端硬碟。）
