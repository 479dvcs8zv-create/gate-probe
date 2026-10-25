# GPT 下一個工作（一次只做這一項；只讀這份，不必讀 CLAUDE_TO_GPT_LATEST.md 全文）

更新：2026-10-25 21:00 台北（Claude）

## 已完成：10-25 三項修補 → **v234**（2026-10-25 19:58 台北部署，三項讀回 PASS；v233 回滾點；報告 `diagnostics/deploy-20261025/report.md`）
- 待跨日驗收：10/27 22:30 新信用被接受、10/28 上午 verifiedAt 保留、10/22 升 final（Claude 10/28 08:30 核對）。

## 現在：上線「擁有者 10-25 修改包」（Claude 寫好、測完）
**授權**：擁有者 2026-10-25 20:15「我授權」（三問）＋20:17「好 一起處理」（同意可轉債、美元零軸、外銷訂單與三問合併一次上線）。範圍只有下面這一份 patch。
- Patch：`handoff/patches/owner-bundle-20261025.patch`（SHA-256 `25ad8327…6afb`），**取代** three-questions-v1.patch（不要兩份疊套）。基線＝v234 來源 faf5eb7（488b8bc＋final.patch）。patch 不含 dist/server/index.js，build 重建。
- 內容（全部只顯示，`scoreContribution=0`，不改評級／Gate／風險預算）：
  1. 汰弱留強三問（同 three-questions-v1）。
  2. 可轉債自動抓：`panel-sources.mjs` 抓櫃買 OpenAPI bond_ISSBD5／ISSBD6（每日快取），`panel-site.js` 只帶該股，`panel-calculations.mjs` 算價內外與台幣債稀釋，畫面卡片「可轉債（櫃買自動）」。`build.mjs` 的 PANEL_SOURCES 多匯出 collectCbRegistry。測試白名單加這兩個官方網址。
  3. 美元零軸改用回測同一條 FRED **DTWEXAFEGS**：`scripts/collect-official-data.py` 多抓 DTWEXAFEGS（145 天、至少 26 筆，**系列數 8→9**）；`data-import.js` 白名單加 DTWEXAFEGS；`panel-site.js` 讀 `official-series:v1:DTWEXAFEGS`；觀測日＋8 日才採用；草案 >0 −1、走弱不加分（`advisory-decision.mjs` 同步）。ICE DXY 報價卡不變。
  4. 外銷訂單改國發會：`observations.js` 從國發會景氣指標 ZIP 讀「外銷訂單動向指數(以家數計)」，移除經濟部抓取與舊快照；`macro-scoring.js`（及 dist/index.html 內同一份）**把外銷訂單從台股本土維度評分移除，expected 8→7**（新口徑門檻未核准前不計分）。
- 步驟：`git apply owner-bundle-20261025.patch` → `node build.mjs` → `TZ=UTC npm test` → 部署；v234 留回滾。
- Claude 已在乾淨 v234 重放：套用無衝突，`dist/index.html` SHA-256 `fa1412dc…9f68`，完整 `npm test` exit 0（新增 `test:owner-20261025` 17/17＋國發會 ZIP 測試）。也用 10-25 真實國發會 ZIP 驗過：320 個月，最新 2026-08＝49.68。
- **你那邊的外部收集包裝（例如 macro_morning.py）若檢查系列數＝8，要改成 9**；下一次官方匯入後美元零軸才會出現，之前顯示「待補」是正常。
- 部署後只讀回（報告 40 行內）：①四檔三問；②四檔可轉債卡（群聯應為 3 檔：群聯三 2,488、海外 A 3,418.75、海外 B 3,555.50，全部價外）；③下一次官方匯入後美元零軸狀態與草案分數；④TW_EXPORT_ORDERS 值與日期、status、未計分；台股總經分數前後與原因（外銷訂單原本就因 403 過期未計入，預期不變）；⑤四檔評級、Gate、風險許可不變。
- 待說明（只寫名稱）：10/25 工具事故印出的是哪一把憑證。
- 對照補充（Gemini 第 30 輪線索）：群聯三 2026-07-06 因除息把轉換價調為 2,468.8；卡片寫「發行時轉換價 2,488」是對的（櫃買 OpenAPI 只有發行時價格），結論仍是價外。

## 下一份（**等擁有者授權**）：「第二修改包」——授權後與上面那份**依序套用、同一次部署**（省一次部署）
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
- 只寫一個檔：`diagnostics/deploy-20261025/report.md`，40 行以內；附 patch SHA、部署版本號、三項讀回結果、npm test 是否 exit 0。
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
