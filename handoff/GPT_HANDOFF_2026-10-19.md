# Gate Pipeline（gate-probe）→ GPT 交接　2026-10-19（v4.24 → v4.36）

撰寫：Claude（gate-probe 探測環境維護）　決定者：網站擁有者（使用者本人）　正式網站 v227：GPT 維護
本檔位置：`handoff/GPT_HANDOFF_2026-10-19.md`（公開 repo 479dvcs8zv-create/gate-probe，唯讀即可）

> **整合狀態（GPT 於 2026-10-19 18:19 台北回報，gate-probe 未能開啟網站自行確認）**：v228 已上線，只接 Gate 5B 時間界線，其他 Gate、權重、收集器未改。驗收三步回報通過：2025Q1 2330 14:05:27、2454 16:55:54 與匯出一致（gate-probe 已核對）；竄改測試拒收、重算 MISMATCH 結束碼 1；2330、2454 各 15 季 MATCH 結束碼 0。8299 研究用界線未採用。
> 注意：gate-probe 提供的 `gate5b_reader.js` 只檢查 `verification`，**不會**拒收「保留 MATCH 但改了時間」的本機檔；v228 拒收代表 v228 另有檢查，請 GPT 說明是哪一項。

---

## 0. 一句話與你要做的事

gate-probe 已經能「輸入股票代號 → 自動抓官方資料 → 算出每季官方截止點」，並把**驗證過的時間界線**放在一個固定網址。
請在 v227 做**最小整合**：Gate 5B 判斷「市場共識快照是否早於財報揭露」時，改讀這個網址的時間界線；v227 其他程式、資料、判定規則一律不動。

1. 讀 `https://raw.githubusercontent.com/479dvcs8zv-create/gate-probe/main/exports/gate5b/latest.json`
2. 用現成讀取器（第 1 節）取某檔某季的 `snapshot_boundary_at`；取不到就維持現行結果。
3. 依第 1 節的驗收三步確認後上線。

---

## 1. 整合（請做）

### 1.1 入口檔
- 網址：`https://raw.githubusercontent.com/479dvcs8zv-create/gate-probe/main/exports/gate5b/latest.json`
- schema：`gate-probe/gate5b-export/v1`
- 產生方式：每次蒐證（gate-pipeline-batch／collect）結束後，gate-pipeline-export 自動執行：取每檔最新一次的
  `results/<代號>/<run>/gate5b_boundaries.json` → 用保存的官方原始回應離線重算 → **一致（MATCH）才匯出**；
  不一致標 `STALE`、缺檔標 `MISSING`，兩者的 `quarters` 都是空的。

| 欄位 | 意思 |
|---|---|
| `stocks.<代號>.verification` | 只有 `MATCH` 才能用 |
| `stocks.<代號>.quarters.<YYYYQn>.cutoff_at` | 官方最早揭露時間（MOPS 原文：季末月營收、自結、董事會通過財報、法說會、財報申報，取最早） |
| `stocks.<代號>.quarters.<YYYYQn>.snapshot_boundary_at` | 共識快照必須**嚴格早於**的時間（最早事件是月營收公告時＝公告當日 00:00） |
| `stocks.<代號>.quarters.<YYYYQn>.cutoff_event`／`cutoff_document_id` | 依據的事件與公告識別碼（例 `t05st01:2454:20250410:165554:1`） |
| `stocks.<代號>.research_only` | 季末規則算出的界線（研究用），**不得**用於 Gate |
| `stocks.<代號>.run_id`／`boundaries_file`／`boundaries_sha256`／`pipeline_package` | 來源與雜湊，可回溯原始證據 |

### 1.2 現成讀取器（直接用）
在程式包 `gate_pipeline_v4.36.zip`（repo 根目錄）內：
- `gate_pipeline/docs/gate5b_reader.js`（瀏覽器或 Node 18+）：`loadGate5bBoundaries()`、`gate5bQuarter(data, coId, quarter)`、`snapshotBeforeBoundary(snapshotIso, q)`
- `gate_pipeline/docs/gate5b_reader.py`（Python 標準函式庫）：`load_gate5b_boundaries()`、`gate5b_quarter()`、`snapshot_before_boundary()`
任何一步失敗都回傳 `null`／`None`＝沒有界線。

### 1.3 消費規則（必須遵守）
1. 只用 `verification == "MATCH"` 的股票、`quarters` 裡的季度（狀態 CUTOFF_VERIFIED）。`research_only`、`excluded` 不能當界線。
2. 檔案取不到、該季不在 `quarters`、`verification` 不是 MATCH → **沒有界線**，該季 Gate 5B 維持現行結果；不能解讀為通過。
3. 快照時間 `<` `snapshot_boundary_at` 才算截止點前（等於也不算）；沒有時區的時間不比較。
4. 不讀 `research.json`、`snapshot_audit.json`（`gate_impact = none`，研究紀錄）。
5. 這個檔只提供時間，不提供判定；Python 預驗證通過不等於正式 Gate PASS。

### 1.4 驗收（約 30 分鐘）
1. 取 2330、2454 各一季，到 MOPS 重大訊息核對 `cutoff_document_id` 的發言日期與時間是否等於 `cutoff_at`。
2. 把本機一份 latest.json 的某個時間改掉，確認 v227 不採用（讀取器只認 MATCH；或用下列指令重算）。
3. 自行複驗（不必相信 gate-probe）：
   `python gate_pipeline/ops/replay_evidence.py results/<代號>/<run_id> --reviews gate_pipeline/contract/mops_real/reviews --check-boundaries` → MATCH 結束碼 0。

### 1.5 撤回
移除這一個讀取即可，沒有其他相依。

---

## 2. 目前資料（2026-10-19 18:00 台北）

來源：gate-pipeline-batch run 39230653532（2330、2454，v4.36）、39217359367／39227122552（上櫃四家），export run 39233507569。

| 代號 | 名稱 | 市場 | Gate 界線（quarters） | 研究用（季末規則） | 官方財測模式 |
|---|---|---|---|---|---|
| 2330 | 台積電 | 上市 | 2023Q1–2026Q3 共 **15/15** | 0 | 14 季 VERIFIED；2025Q1 經使用者確認「已更新財測」不比較 |
| 2454 | 聯發科 | 上市 | 2023Q1–2026Q3 共 **15/15** | 0 | 14 季 VERIFIED；2026Q3 實際結果尚未公布 |
| 8299 | 群聯 | 上櫃 | 0（沒有月營收重大訊息） | 15 | 公司不在重大訊息公布量化財測 |
| 6485 | 點序 | 上櫃 | 0 | 15 | 同上 |
| 6488 | 環球晶 | 上櫃 | 0 | 15 | 同上 |
| 5347 | 世界 | 上櫃 | 0 | 15 | 同上 |

官方財測模式（Python 預驗證，非正式 Gate PASS；公司自己上一季公布的財測 vs 實際）：
- 2330（營收／毛利率／營益率）：2023Q1–Q3 營收在區間內、兩率高於；2023Q4 營收高於、毛利率在區間、營益率高於；
  2024Q1 營收高於、兩率在區間；2024Q2–Q3 三項皆高於；2024Q4 營收、毛利率在區間、營益率高於；2025Q2–2026Q3 多數高於。
- 2454（營收／毛利率）：2023Q1–Q2 皆在區間；2023Q3–Q4、2024Q4、2025Q1、2025Q3、2026Q2 營收高於；
  2024Q1 兩項高於；2024Q2–Q3、2025Q2 毛利率高於；2025Q4、2026Q1 皆在區間。
- 2454 一次性項目照實記錄、不調整數字：2024Q1 毛利率含一次性項目（+4.5 個百分點），2025Q2（+1.9 個百分點）。

---

## 3. 使用者決定紀錄（全部在 `gate_pipeline/contract/mops_real/reviews/`）

| 時間（台北） | 決定 | 檔案 |
|---|---|---|
| 10-18 13:45 | 2330 2026Q2 兩則未分類公告不是財務結果 | 2330_2026Q2_unclassified.json |
| 10-18 15:34 | 條款自動排除：第 20、6、8 款（需有詳細頁） | clause_policy.json |
| 10-18 17:47 | 2330 七則不是財務結果（2024Q1 五則、2024Q3、2025Q2 各一） | 2330_2024Q1／2024Q3／2025Q2_unclassified.json |
| 10-18 20:14 | 2330 2024Q1、2024Q2 各一則「沒有更新財測」 | 2330_2024Q1／2024Q2_guidance.json |
| 10-18 21:05 | 2454 子公司減資 2 則不是結果；「財報不可能早於董事會通過」規則 | 2454_2024Q4_unclassified.json |
| 10-18 21:20 | 2330 2025-02-10 地震公告算「已更新財測」，2025Q1 不比較 | 2330_2025Q1_guidance.json |
| 10-19 11:10 | 月營收截止點的快照界線＝公告當日 00:00 | revenue_snapshot_boundary_policy.json |
| 10-19 12:35 | 市場共識研究四條規則（見第 4 節） | consensus_research_policy.json |
| 10-19 15:10 | 季末規則（沒有月營收重大訊息的季度：季度結束隔天 00:00）採用為**研究用**預設 | revenue_quarter_end_policy.json |
| 10-19 16:30 | 2330 2023-10-03 公司債發行條件、2454 2023-07-07 子公司發放股利：不是結果 | 2330_2023Q3／2454_2023Q2_unclassified.json |
| 10-19 17:35 | 2454 三場 Nomura @CES（2024、2025、2026）不是結果：觀測站法說會一覽表附的簡報都是季度結束前已公開的第三季簡報 | 2454_2023Q4／2024Q4（amended）／2025Q4_unclassified.json |
| 10-19 17:35 | 2330 2023-08-21「澄清媒體報導」＝沒有更新財測 | 2330_2023Q3_guidance.json |

---

## 4. 規則與定義（重點）

- **截止點**：該季最早的官方揭露（季末月營收公告、自結每股盈餘、董事會通過財報、法說會、財報申報上傳時間）。
  季末到最早事件之間的未分類公告，必須經人工或條款規則確認不是結果，否則該季暫定（PROVISIONAL）。
- **快照界線**：最早事件是月營收公告 → 公告當日 00:00（月營收申報系統上傳時間未查證）；其他 → 原文公告時間。
- **季末規則（研究用）**：重大訊息沒有季末月營收公告 → 季度結束隔天 00:00，狀態 CUTOFF_QUARTER_END_RULE。
  依據：證券交易法第 36 條第 1 項第 3 款「於每月十日以前，公告並申報上月份營運情形」（只有最晚期限；季末月營收不可能在季度結束前公布）。
  **不進 Gate、不進官方財測模式**；是否用於 Gate 尚待擁有者決定。
- **市場共識研究四條規則**：1 ADR 美元 EPS 只和官方公告的每單位 ADR 美元 EPS 比較，不自行換匯；2 頁面沒寫 GAAP／調整後 → 待確認；
  3 分析師人數只標品質（單一／少量／一般），不設 Gate 最低人數；4 ADR 頁上的新台幣 EPS 未確認每股或每 ADR → 待確認。
- **一致性檢查**：頁面標示幣別與數值矛盾（例：Yahoo 2330.TW 2024-09 頁面標 USD、數值是新台幣）→ 待確認（UNIT_CONFLICT）。
- **截止點狀態檢查**（v4.31 起）：截止點暫定的季度，快照不能列為可採用。

---

## 5. 版本變更（v4.24 → v4.36，全部在 gate-probe，未碰正式網站）

- v4.24–v4.28：董事會規則；月營收當日 00:00 界線；Wayback 自行存檔、歷史補齊、重新下載核對；研究紀錄與逐項快照審查。
- v4.29：修正台積電「以美金計算」與「億 X 千萬」美元營收解析（Gemini 第一輪抓到 3 處：2023Q4 19.62、2024Q1 18.87、2024Q2 20.82）。
- v4.30：單位一致性檢查（UNIT_CONFLICT）。
- v4.31：支援上櫃股；多檔一次跑（gate-pipeline-batch）；季末規則（可選）；`gate5b_boundaries.json`；`--check-boundaries` 複驗；聯發科一次性項目註記。
- v4.32：上櫃清單格式人工比對後列為已驗證；上櫃「董事會通過合併財務報告」寫法；Wayback 停擺時提早停止；季末規則改為研究用預設。
- v4.33：蒐證中途存檔（取消或逾時後可沿用已抓的詳細頁）；批次每檔上限 150 分鐘。
- v4.34：上櫃詳細頁格式驗證（8299 的 107 則）；觀察清單存檔（`watchlist.txt`）；法說會簡報探測；TradingView 存檔來源；同一季多則結果公告數字相同才合併。
- v4.35：上述 CES 與 2330 澄清的審查紀錄；法說會一覽表解析與可重算的 CES 證據。
- v4.36：`exports/gate5b/latest.json` 自動匯出（重算一致才匯出）與 JS／Python 讀取器。
- 測試：255 項（26 檔）全部通過，每版都在新資料夾解壓後重跑；程式包含 MANIFEST.sha256，Actions 執行前逐檔核對。

---

## 6. 市場共識研究現況（gate_impact = none，不影響 Gate）

- 2330 逐項快照審查：可採用 8、待確認 14、不可採用 0（待確認多為「頁面沒寫口徑」，依規則 2）。
- 觀察清單每週一 09:17（台北）自動存檔；1/4/7/10 月 1–15 日每天存。2026-10-19 第一次：上櫃四家 Yahoo `.TWO` 預估頁與 2454 `.TW` 頁都存到並解析成功（每頁 8 筆，代號核對相符）。
- TradingView 頁面已存檔，含「下一季每股盈餘／營收預估」文字，尚無解析器；口徑未寫，依規則 2 會是待確認。
- 2330 本次 Wayback 回應慢未存成，排程會優先補。Zacks 只存到防機器人頁，不採用。

---

## 7. Gemini 查證彙整（第 1–6 輪；只採官方或原始來源，轉載只當線索）

**對 gate-probe 的核對**
- 第 1 輪：台積電 12 季官方數字逐字核對，抓到 3 處美元營收解析錯誤 → v4.29 修正；其餘相符。
- 第 2 輪：各網站口徑說明多為 2026 年版面 → 歷史快照維持規則 2；台積電新聞稿只有日期 → 維持 00:00 界線。
- 第 3 輪：聯發科財測與實際、台積電毛利率／營益率、季末月營收發言時間：可核對者全部相符；聯發科 2025Q2 毛利率含一次性項目 → v4.31 加註記。
- 第 5 輪：群聯 9 則觀測站發言時間（到秒），gate-probe 用官方清單逐則核對 **9/9 相符**。
- 第 7 輪（2023 年數字獨立核對，對照官方新聞稿與 IR 頁）：台積電 2023Q1–Q4 財測與實際**全部相符**（2023Q1 營益率 45.5% Gemini 未取到，由觀測站每股盈餘公告原文「營業利益率為45.5%」補證）；聯發科可核對者全部相符，Gemini 無法核對的 2023Q1–Q3 毛利率、營業費用率、匯率與 2023Q3 實際毛利率 47.4%，由觀測站法說會一覽表附的官方簡報（245420230203／0428／0728／1027M001.pdf）逐項補證。**零不符**。季末月營收公告日期也相符（到秒的時間以官方清單為準）。
- 第 6 輪：證交法第 36 條條文（季末規則依據）；Yahoo 上櫃股 `.TWO` 預估頁存在（6488 有逐季預估、9 位分析師）；TradingView 有上櫃逐季預估（TWD、口徑未寫）。

**給正式網站其他 Gate 的資料（請自行再核對後使用）**
- 日圓兌美元：FRED `DEXJPUS`（聯準會 H.10），CSV `https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXJPUS`；美國假日為「.」，算波動率時略過、不補值。
- 黃金：臺灣銀行黃金存摺歷史牌價（近一年每日，新台幣／公克，買入／賣出）`https://rate.bot.com.tw/gold/chart/ltm/TWD`。
- 白銀：上海黃金交易所白銀基準價（SHAG，人民幣／公斤，早盤／午盤）`https://en.sge.com.cn/data_SilverBenchmarkPrice`。
  LBMA 歷史表需 IBA 授權；CME 公開頁只有 5 天且條款禁止擷取；FRED 已於 2022 年移除 LBMA 序列 → 皆不建議。
- 集保股權分散表：每週（最後營業日），欄位為持股分級、人數、股數、比例 `https://www.tdcc.com.tw/portal/zh/smWeb/qryStock`。
- 群聯 8299 可轉債（發言時間已用官方清單核對）：
  群聯一 82991 於 2024-12-17 到期、12-18 終止櫃買（公告 2024-11-07 14:30:14）；群聯二 82992 贖回、2026-01-23 終止櫃買（櫃買中心公告）；
  群聯三 82993 轉換價 2,488 → **2,468.8**（2026-07-06 起；公告 2026-06-12 14:31:07）；
  海外第一次轉換債訂價 A 券 **3,418.75**、B 券 **3,555.50**（公告 2026-05-18 23:57:23）；到 2026-10-16 官方清單**沒有**海外債轉換價調整公告。
- 群聯年度財測：觀測站重大訊息**沒有**全年量化財測；第三方法說會整理（blog.fugle.tw，轉載）記載「正在發行 ECB，無法提供具體的財務指引」。
- 群聯 FactSet（鉅亨轉載，只當研究線索）：2026-10-12 共 11 位；2026 EPS 中位數 416.97、平均 412.32；
  2027 中位數 362.55、平均 347（區間 132.16–618，分歧大）；2028 中位數 267.92、平均 227.06。
- 點序 6485：過去 12 個月沒有 FactSet 或券商 EPS 預估 → 無法核對。
- 群聯年報（生產據點、10% 以上客戶、市占率）：尚未取得 PDF 原文頁碼 → 無法核對。

---

## 8. 未完成／待決定

1. 季末規則是否用於 Gate（擁有者決定；目前只研究用）。
2. 觀察清單之外的股票：先跑一次 gate-pipeline-batch 再加入 `watchlist.txt`。
3. TradingView 解析器（等累積樣本）；2330 下次存檔補齊。
4. Gemini 第 8 輪（已出題）：下一批公司的量化財測與位置、月營收官方申報時間查詢頁、中文分析師預估頁。2023 年數字核對已完成（第 7 輪）。
5. `479dvcs8zv-create/AI_GATEWAY_KEY`：gate-probe 從未讀取或修改。

---

## 9. 檔案位置速查（gate-probe）

| 用途 | 路徑 |
|---|---|
| 給網站的入口 | `exports/gate5b/latest.json`、`exports/gate5b/<代號>.json` |
| 每次蒐證 | `results/<代號>/<run>/`（manifest.json、summary.json、gate5b_boundaries.json、responses/） |
| 多檔總表 | `results/batch/<run>/batch_report.md` |
| 共識存檔與研究 | `results/<代號>/archive/<run>/`（archive.json、research.json、snapshot_audit.json） |
| 法說會簡報探測 | `results/2454/conference/39227119449/` |
| 程式包 | 根目錄 `gate_pipeline_v4.36.zip`（最新） |
| 審查與規則紀錄 | 程式包內 `contract/mops_real/reviews/` |
| 觀察清單 | `watchlist.txt` |

## 10. 不變的約束

只在 gate-probe 工作；不碰正式網站的 repo（含 main）、不開 PR；不用 API key；Python 預驗證通過不等於正式 Gate PASS；
adapter 不能決定官方公告時間；外部資料取得失敗不能解讀為驗證通過；官方財測與市場共識分離。
