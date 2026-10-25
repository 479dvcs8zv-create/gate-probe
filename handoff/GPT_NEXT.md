# GPT 下一個工作（一次只做這一項；只讀這份，不必讀 CLAUDE_TO_GPT_LATEST.md 全文）

更新：2026-10-25 14:52 台北（Claude）

## 現在這項：部署 10-25 三項修補（`diagnostics/local-fix-20261025/final.patch`）
- **擁有者已授權（2026-10-25 14:50 台北，在與 Claude 的對話中回覆「授權」）。** 範圍只有這份 final.patch，其他排隊項目不在授權內。
- Claude 已審：final.patch SHA-256 `d4940c2d…3899` 相符；只動 macro／observations／observation-freshness、測試與 dist；無金鑰、無網站網址。三項邏輯與 14:40 交接一致。
- 步驟：乾淨基線 488b8bc → `git apply final.patch` → `node build.mjs` → `npm test` → 部署；v233 留作回滾。
- 部署後只讀回三件事：①10/22 信用可被接受、觀測日仍 10/22、`calendarDiscrepancy=true`；②信用列 `verifiedAt` 不是本輪時間；③run 摘要與 /api/macro 一致。
- **10/27（週二）22:30 晚間巡檢**：信用要被接受；10/28 上午讀回 `verifiedAt` 沒被改寫、10/22 升 final。

## 回報方式（省額度）
- 只寫一個檔：`diagnostics/deploy-20261025/report.md`，40 行以內；附 patch SHA、部署版本號、三項讀回結果、npm test 是否 exit 0。
- 不要每一步各開一個 commit；完成後一次提交。

## 之後的排隊（做完上一項、擁有者說繼續才開始，一次一項）
1. 汰弱留強三問（規格見 CLAUDE_TO_GPT_LATEST.md「2026-10-25 14:50」第 1 點，只讀那一段）。
2. 免費資料缺項，一次一個：法人 10／20 日 → 殖利率 → RSI → Beta → 集保大戶 → 大盤融資維持率。
3. Gate 4 可轉債：用櫃買 OpenAPI `bond_ISSBD5_data`／`bond_ISSBD6_data` 顯示每檔流通餘額、發行時轉換價、價內／價外、潛在稀釋股數占股本（用官方發行股數；海外債用契約固定匯率）；現行轉換價以公開資訊觀測站調整公告為準，沒有就標「待核」。Claude 已查好群聯的官方資料：`results/cb/8299-2026-10-25.md`。
（Gemini 第二意見的比對改由 Claude 做，GPT 不用處理。）
（GPT 讀不到擁有者的 Google 雲端硬碟；Gemini 的資料一律由 Claude 讀取後轉存到 gate-probe，例如 `results/second-opinion/8299-2026-10-22.md`。GPT 不必、也不要嘗試讀雲端硬碟。）
