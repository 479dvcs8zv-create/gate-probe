# GPT 下一個工作（一次只做這一項；只讀這份，不必讀 CLAUDE_TO_GPT_LATEST.md 全文）

更新：2026-10-26 10:25 台北（Claude）

## 已完成：10-25 三項修補 → **v234**（2026-10-25 19:58 台北部署，三項讀回 PASS；v233 回滾點；報告 `diagnostics/deploy-20261025/report.md`）
- 待跨日驗收：10/27 22:30 新信用被接受、10/28 上午 verifiedAt 保留、10/22 升 final（Claude 10/28 08:30 核對）。

## 已完成：兩包 → **v235**（10-26 05:34 部署；SHA 全對、npm test exit 0；報告 `diagnostics/deploy-20261026/report.md`）
- 讀回 ①③⑤ PASS；②④ FAIL、⑥ PARTIAL；手動巡檢 partial、Gate 審計 4/4 step_timeout；每日巡檢保持停用（正確）。

## 已完成：v235 修補 → **v236**（10-26 08:0x；報告 `diagnostics/deploy-20261026/hotfix.md`）
- ① Gate 審計 4/4 recorded、無逾時 PASS；③ 國發會 49.68 PASS；② 可轉債仍 `CB_REGISTRY_STILL_LOADING` FAIL；每日巡檢保持停用（正確）。

## 現在：兩份修補，同一次處理（Claude 寫好、測完；**都已授權**）
**授權**：擁有者 2026-10-26 08:49「授權」（可轉債修補）＋08:55「m1 資料來源補齊、小項也處理」＋09:13「好」（IORB 未來日期、巡檢模組 pending）＋09:30「好」（產業研究來源、缺收盤分類、重大訊息識別）＋09:55（巡檢要自動跟著追蹤清單，持股會變成 1 檔或 5 檔）＋10:02「剩下的做完」（EIA、日圓時效統一）。擁有者說要晚點做，等他叫你再開始。

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
- 測試：新增 `tests/test_cbc_money.py` 4 項（用 10-26 的真實央行頁面）＋IORB 1 項；新增 `tests/test_eia_release.py` 2 項（10-26 真實 EIA 頁面）；Claude 在乾淨 850e87e 上 `git am` 後 `python -m unittest discover -s tests` 31/31 通過；若 main 已有新的排程資料 commit，用 `git am -3`；只有 `data/keyless_snapshot.json` 衝突時保留 main 版本、再刪掉其中 `TW_EXPORT_ORDERS` 一項；也用真實 ms.ods 驗過：1983-01～2026-08 共 524 個月，2026-08 = −0.14（6.65 − 6.79）。

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
