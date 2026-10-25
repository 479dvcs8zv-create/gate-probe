# GPT 下一個工作（一次只做這一項；只讀這份，不必讀 CLAUDE_TO_GPT_LATEST.md 全文）

更新：2026-10-25 14:52 台北（Claude）

## 現在這項：部署 10-25 三項修補（`diagnostics/local-fix-20261025/final.patch`）
- **擁有者已授權（2026-10-25 14:50 台北，在與 Claude 的對話中回覆「授權」）。** 範圍只有這份 final.patch，其他排隊項目不在授權內。
- Claude 已審：final.patch SHA-256 `d4940c2d…3899` 相符；只動 macro／observations／observation-freshness、測試與 dist；無金鑰、無網站網址。三項邏輯與 14:40 交接一致。
- 步驟：乾淨基線 488b8bc → `git apply final.patch` → `node build.mjs` → `npm test` → 部署；v233 留作回滾。
- 部署後只讀回三件事：①10/22 信用可被接受、觀測日仍 10/22、`calendarDiscrepancy=true`；②信用列 `verifiedAt` 不是本輪時間；③run 摘要與 /api/macro 一致。
- **10/27（週二）22:30 晚間巡檢**：信用要被接受；10/28 上午讀回 `verifiedAt` 沒被改寫、10/22 升 final。

## 同一輪順便做（擁有者 10-25 15:18：之後的功能改由 Claude 寫程式，GPT 只負責套用與上線）
- 把網站來源 **commit 488b8bc（v233，尚未套 final.patch）** 打包成一個 zip 交給擁有者下載（**不要放進任何公開 repo**）。
- 包含：全部原始碼與測試（worker/、tests/、build.mjs、package.json、package-lock.json、dist/index.html、遷移檔等，能在乾淨環境 `npm ci && npm test`）。
- 排除：任何金鑰／.env／憑證、`dist/server/index.js`（生成檔，含私人操作說明）、node_modules、私人網址與專案代號。
- 附檔案清單與每個檔的 SHA-256；在 report.md 寫一行 zip 的 SHA-256。
- 之後流程：Claude 用這份來源寫好功能＋測試、自己跑完整 `npm test`，把 patch 放 gate-probe；GPT 只要套用、跑測試、擁有者授權後上線。

## 回報方式（省額度）
- 只寫一個檔：`diagnostics/deploy-20261025/report.md`，40 行以內；附 patch SHA、部署版本號、三項讀回結果、npm test 是否 exit 0。
- 不要每一步各開一個 commit；完成後一次提交。

## 之後的排隊（做完上一項、擁有者說繼續才開始，一次一項）
**通則：新資料一律做成網站自動抓取、任何代號通用；Claude 或 Gemini 查到的數字只當驗收對照，不寫進網站。**
1. 汰弱留強三問（規格見 CLAUDE_TO_GPT_LATEST.md「2026-10-25 14:50」第 1 點，只讀那一段）。
2. 免費資料缺項，一次一個：法人 10／20 日 → 殖利率 → RSI → Beta → 集保大戶 → 大盤融資維持率。
3. Gate 4 可轉債——**網站自動查詢帶入，任何代號通用**（擁有者 10-25 15:06：要未來自動查詢帶入，不是靠 Claude 搜尋帶入）：
   - 每次巡檢與切換個股時，自動抓櫃買 OpenAPI `bond_ISSBD5_data`（國內）、`bond_ISSBD6_data`（海外），用 IssuerCode 篩出該股所有流通中可轉債；上市、上櫃股票都適用。
   - 顯示每檔：流通餘額、發行時轉換價、可轉換期間、賣回日、價內／價外（對最新收盤）、潛在稀釋股數占股本（官方發行股數；海外債用契約固定匯率，取不到就標「待核」）。
   - 現行（調整後）轉換價：找官方可自動取得的來源（公開資訊觀測站「調整轉換價格」公告）；自動取不到時標「發行時轉換價，未含後續調整」，不得手動填值。
   - 清單裡查不到的舊債（例如已轉換完的群聯二）顯示「無流通餘額」，不沿用舊資料。
   - `results/cb/8299-2026-10-25.md` 只是 Claude 手動查的**驗收對照**（群聯應自動抓到 3 檔：群聯三 2,488、海外 A 3,418.75、海外 B 3,555.50），不是要匯入的資料。
（Gemini 第二意見的比對改由 Claude 做，GPT 不用處理。）
（GPT 讀不到擁有者的 Google 雲端硬碟；Gemini 的資料一律由 Claude 讀取後轉存到 gate-probe，例如 `results/second-opinion/8299-2026-10-22.md`。GPT 不必、也不要嘗試讀雲端硬碟。）
