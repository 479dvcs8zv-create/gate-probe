# GPT 下一個工作（一次只做這一項；只讀這份，不必讀 CLAUDE_TO_GPT_LATEST.md 全文）

更新：2026-11-11 23:58 台北（Claude；重新核對 patch 仍可套用）

## ★ 本輪工作（11/09 21:18 更新、11/10 21:10 補 U-6、11/11 23:58 重新核對；只讀這一段就夠，下方各節是細節備查）
**等每週額度恢復（週三 11/11 23:19 後）再做。** 擁有者 2026-11-09 21:12 已在 Claude 對話說「好」；開始前請擁有者在你的對話裡再確認一次。**部署一律要擁有者授權。**

**省額度規則（這輪起一直適用）**
- 只讀這一段和下面點名的檔案，不要重新瀏覽整個 repo。
- 每做完一步，就在 `diagnostics/deploy-20261026/hotfix13.md` 加一行（commit／SHA／結果）並提交。中斷後從還沒完成的那一步接續，已完成的不要重做。
- 完整測試 `TZ=UTC npm test` 只跑一次；失敗時只重跑失敗的那一個檔。

**原因**：Claude 量到，巡檢每查一次 status，網站都回整包資料（網站測試資料實測：一次 23～29 萬字元，一輪 36 次約 930 萬字元）。你的紀錄是每輪 40～61 次，再加上約 9 萬字元的證據 JSON、每輪提交 5 次。每週額度大多花在這裡。

1. **網站 v255：查進度加 `?compact=1`**
   - 檔案：`handoff/patches/v255-compact-status.patch`，SHA-256 `20fc9d2ee2914be3c9d8db31cf9e968665de99247bda053d5ca37924d4d2fbde`，基線＝v254（Claude tag v254-patch-head）。
   - 內容：POST `/api/automation/refresh-all?compact=1` 和 GET `/api/automation/status?compact=1` 照樣推進同一步，但只回 `runId`、`status`、`checkpoint`、`completedAt`、`summary`、`problems`。`summary`＝history 那一列，再加 `gateAuditTotal`、`stockBatch`；`problems`＝不是 ok／automatic／not_used 的覆蓋列。不帶參數時回應完全不變。
   - 新增 `tests/v255-compact-status.test.mjs` 2 項：在 v254 上失敗、套用後通過。每次回應都在 4 千字元內，摘要和 history 逐欄相同。
   - Claude 已在乾淨 v254 上重放：無衝突，完整 `TZ=UTC npm test` exit 0。
   - 和第 1b 項的 v256 一起部署一次。套用後 HTML 仍是 `de5a6d6b…`。匿名化核對的後台：只套 v255 是 `029de2cc…`；v255＋v256 是 `e5d736dc7c026c2768147d4f5256dbd52917ac92b634b97c18a0ccafaf11cd42`。現行版本留作回滾。
   - 部署後只驗一件事：GET `/api/automation/status?compact=1` 的回應有 `"compact":true`，且長度在 4 千字元內。
1b. **網站 v256＋中繼 U-6（擁有者 2026-11-10 21:01 已在 Claude 對話說「好」）**：擴展總經多一列「美國 U-6 廣義失業率」，只顯示，不進任何評分或門檻。
   - 中繼：`handoff/patches/relay-u6rate.patch`，SHA-256 `0e06a67d7d55361723c01b8bcbc80eade7adfda61e3c5de5db3d5bfae3aa023c`。在中繼 main `git am` → push；本機 git 連不到時，用連接器提交，核對 blob：`scripts/sync_keyless.py` → `48aba82986a7a6a3bfa12fa9be8606c5086b23ef`、`tests/test_keyless.py` → `482a09b57372fe8c05e88bfd8c65c9f3d936ef67`。
     - Claude 11/11 23:58 在中繼目前的 main `dd9489b` 上重新套用：無衝突、62 項測試全過。
     - Claude 11/10 21:04 已在 GitHub 上試跑（不推送）：U6RATE＝9 月 7.6%、10 月 7.9%（FRED），61 項全成功，加上 U-6 共 62／62；中繼測試 62 項全過。
   - 網站：`handoff/patches/v256-u6rate.patch`，SHA-256 `979bdf669db8453a3b51835a9e738578f5e3b95bab29c63832e8273a758fc576`，基線＝v255。新增 `tests/v256-u6rate.test.mjs` 3 項（在 v255 上失敗、套用後通過）。
     - Claude 已在乾淨 v254 上依序套 v255、v256：無衝突，建出來和 Claude 的完全相同，完整 `TZ=UTC npm test` exit 0（末組 94／94）。
   - 部署後擴展總經會變成 13 項（原 12 項）。這是正常的，不是異常。
2. **部署驗證通過後，把排程巡檢指令換成精簡版**（只改指令，不改 06:30／22:30 時段與開關）。全文在 `handoff/patrol_prompt_v255.md`。保留你現有指令裡「怎麼連到網站」那一段（私人網址、驗證方式都不要寫進任何 repo），其餘換成這份。
3. **報告** `diagnostics/deploy-20261026/hotfix13.md`（逐步追加，最後 8 行內）：
   - v255＋v256、中繼 U-6 是否獲授權，部署結果（commit、SHA）；
   - compact 讀回長度；
   - 排程指令已換成精簡版；
   - 第一次精簡巡檢的 3 行紀錄；
   - 確認 patch 5 沒有套用、v254 驗收結案（理由見下方 11/08 23:55 版）。

**資訊（不用處理）**：11/08 06:48 之後沒有巡檢紀錄（額度用完），部署完成後照新的精簡版指令恢復即可，不用補做。Claude 第 39～42 輪回測（季線站回買回、外資買賣超、集保大戶、424 分批）都不改網站規則，結果在 gate-probe `results/backtests/`，這輪不用讀。

<details><summary>11/08 23:55 版工作區塊（併入本輪報告 hotfix13，備查）</summary>

**不用改任何程式、不用部署。** 這輪只有巡檢和一份短報告。

1. **今晚 22:30 的巡檢沒有紀錄**（看門狗 23:47 提醒：最後一筆是 11/08 06:48）。請現在補做一次夜間巡檢，照平常的方式做：POST `/api/automation/refresh-all`，再 GET status／history。另外查一下 22:30 排程為什麼沒跑或沒寫紀錄（是平台 run 失敗、自動核准審查、使用量限制，還是其他原因），照實寫。不要改時段與開關。
2. **中繼 patch 5 撤回，不要套用**（`relay-night-wait.patch` 留在資料夾裡備查）。理由：你 11/07 22:55 的紀錄顯示，網站自己在 22:51 直接抓到了 11/06 的信用，而且符合 22:30 規則。網站的匯入值只要還沒過期，就會優先於直接抓取（`loadTaiwanDashboard` 先用 `importedTaiwanStatistics`）。所以如果中繼每晚 22:31 收、隔天早上匯入，隔天晚上 22:30 巡檢反而會用前一天的匯入值，不去抓當天的，信用資料會慢一天。不套 patch 5，網站每晚自己抓，比較快。
3. **v254 驗收：可以結案。** v254 的範圍只是「匯入的信用七列要帶 `previousDate`／`capturedAt`／`captureDeferred=false`」。這已在你 11/06 夜間巡檢的實際匯入驗證過：statistics=imported，`previousDate=11/04`、`capturedAt` 有值、`captureDeferred=false`。那次擷取時間不合規是中繼的問題，已由 patch 4 修正，不屬於 v254。
   - 另外，網站直接抓到的新值本來就不帶 `captureDeferred` 欄；只有 22:30 前沿用舊值時才標 `true`。這是正常的，不算錯，也不用補。
4. **報告**：寫 `diagnostics/deploy-20261026/hotfix13.md`（6 行內）：第 1 項補做結果與 22:30 沒跑的原因；第 2 項確認沒有套用 patch 5；第 3 項 v254 結案。

</details>

<details><summary>11/07 16:09 版工作區塊（patch 5 已撤回，備查）</summary>

**Claude 已核對 hotfix12 與 11/06 夜間、11/07 晨間紀錄**：中繼 `5304729`、`c0c1efe` 和 Claude 的兩包逐檔相同；VIX 已是 Cboe 11/05＝28.18；全市場已到 11/06（81 交易日、1,964／1,990 檔）。你把 09:50 的信用照實標為「不合規、驗收未完成」是對的。
**改程式一律先經擁有者在你的對話裡親口授權**；這次只改中繼，網站程式不用動、不用部署。

1. **新發現：昨晚完全沒有收到夜間信用統計。** 原因不是 patch 4 的規則，而是 GitHub 排程在這個 repo 嚴重延後。Claude 用公開 API 查到 Official data collector 的實際開始時間（台北）：11/06 23:59、11/07 04:33、04:49、05:01、09:19，沒有一次落在 22:30～23:59。之前 11/05～11/06 也一樣（00:32、05:13、05:26、09:50）。所以現在的套件是 `morning-no-statistics`，`carryNote`＝「上一份套件沒有信用統計」。
2. **中繼 patch 5（新，等擁有者授權）：提早排隊、等到 22:31 再收**。`handoff/patches/relay-night-wait.patch`，SHA-256 `95bb7e65b85100deda5d472025f4a06e8751b15fe059866ca85317dcb255e350`。
   - 新增每天 18:05、20:05（台北）兩個排程。新的 `wait-night` 工作若還沒 22:31 就等到 22:31（最多 330 分鐘；已過 22:31 或離 22:31 太久就不等），接著原本的收集工作照常跑。因為已在 22:30～23:59 內，會收信用統計。
   - 手動執行可用新輸入 `night=true` 達到同樣效果。
   - 等待的工作不佔排隊位置；排隊（`official-collector`）從整個 workflow 移到收集工作上，等待時其他時段的收集照常跑。
   - 週末也跑：週五晚上沒收到時，週六晚上照網站規則收週五的信用統計。
   - 規則不變：22:30 前擷取的照樣不發布；白天照樣原檔沿用前一晚那份。
   - Claude 已做的核對：在中繼 main `1becede` 上 `git am` 無衝突，測試 65/65 過（61＋新 4 項），actionlint 1.7.7 檢查 workflow 通過。
**本機 git 連不到 github.com 時（你 11/07 16:18 回報）**：照 hotfix11、hotfix12 的做法，用 GitHub 連接器直接在中繼 main 提交 patch 5 的 3 個檔案（patch 4 也改過 workflow 檔，同一方式成功過），內容以 patch 為準。提交後核對 blob SHA：
   - 新增 `scripts/wait_night_capture.py` → `82c3d827c4e5f6c4f29462fcf019362447bd4fff`
   - 新增 `tests/test_night_wait.py` → `45537c228c716a29022dc748c33500669487ee22`
   - 修改 `.github/workflows/official_collector.yml`（原 `ca2283d9…`）→ `85e73f53ef2898fe408ba3ce3d0f3f88427936da`

3. **套用後今晚就要用上**：push 後請到中繼的 Actions → Official data collector → Run workflow，`night` 填 `true`，其他維持預設，手動跑一次。17:01 以後任何時間按都可以，它會自己等到 22:31。手動執行會馬上開始，不像排程會延後。今晚會收到週五 11/06 的信用統計。你的工具不能觸發 workflow 的話，請告訴擁有者自己按一次。**patch 5 今晚來不及推上去也沒關係**：擁有者在今晚 22:30～23:59 之間手動按一次 Run workflow（全部用預設值）就會收到信用統計，因為 patch 4 已經在線上了。
4. **讀回（明早 11/08 06:30 巡檢）**：
   - 套件：`statistics.json` 的 `capturedAt` 在 11/07 22:30～23:59（台北），`date`＝2026-11-06。若是早上的套件，就看 `carried`。
   - 網站：信用七列的觀測日＝11/06、`previousDate`＝11/05、`captureDeferred=false`、`capturedAt` 是那次夜間擷取的時間。**這一次就是保留中的「v254 合規新匯入七列驗收」**，請照實標完成或未完成。
   - 今晚 22:30 的巡檢早於 22:31 的擷取，所以收不到，正常，不要另建 run。

**報告**：寫 `diagnostics/deploy-20261026/hotfix13.md`（10 行內）：是否獲授權、中繼 commit、手動執行的 run 與開始／收集時間、明早讀回結果。

</details>

<details><summary>11/06 18:20 版工作區塊（hotfix12 已交，備查）</summary>

**Claude 已核對 hotfix11（11/06 12:20）與今晨紀錄**：三包 SHA、中繼 `e8b3759`、Sites 原生 250、HTML `de5a6d6b…`、匿名化後台 `99f2ce82…` 都相符；信用七列 `previousDate=11/03`、`capturedAt`、`captureDeferred=false` 欄位讀回正確。你指出「重讀舊快照不算新匯入驗收」「早上 05:26 的信用不能拿來湊」都是對的；你發現的中繼信用時段缺口，下面第 2 項就是修正。
**改程式一律先經擁有者在你的對話裡親口授權**；兩包都只改中繼，網站程式不用動、不用部署。

1. **中繼 patch 3：VIX 改抓 Cboe 官方收盤＋FRED 連線修正（擁有者 11/06 17:27 已在 Claude 對話說「好」；請等擁有者在你的對話裡再確認一次）**：`handoff/patches/relay-vix-fred.patch`，SHA-256 `41536a3d717ad7e418f9560a552ff48fe65b820cf02e316842cb3a06e3b5dea3`。
   - 內容：`sync_keyless.py` 的 VIXCLS 先讀 Cboe 官方 `VIX_History.csv`（當天美股收盤後就有），讀不到才用 FRED VIXCLS（約晚一天）；所有 FRED 下載先用 Python 預設連線方式、中斷最多重試 4 次（和網站 v253 同一套）；`sync_cross_market.py` 的 FRED 下載同樣先用預設方式。
   - 原因：現行中繼今天 14:59 那次 61 項只成功 17 項（44 項失敗，其中 38 項是 FRED 逾時）；VIX 停在 11/04 16.61，但 Cboe 已公布 11/05 收盤 28.18。
   - Claude 已在 GitHub 上試跑（不推送）：61 項成功 55 項，剩下 6 項是證交所 11/06 信用／當沖（當時 17:30 還沒公布，正常）；VIXCLS 來源＝Cboe，11/03 20.83、11/04 16.61、11/05 28.18；DGS10、SOFR、DTWEXAFEGS 由 FRED 正常取得。
2. **中繼 patch 4：信用統計只在台北 22:30～23:59 收（新，修你今晨回報的缺口；等擁有者授權）**：`handoff/patches/relay-credit-window.patch`，SHA-256 `9a72b4595bd05015a98cd9bf4f019988420271579a9d4bcfbe4b82c07e797b48`。
   - `run_official_collector.sh` 的 auto 改成只在 22:30～23:59 收信用統計（和網站 `taiwanCreditCaptureAllowed` 同一條規則）；`publish_official_import.py` 不論模式，22:30 前擷取的 `statistics.json` 一律不發布（寫進 errors）。
   - 沒有新的夜間信用統計時（早上、下午、或夜間抓失敗），沿用上一份套件的 `statistics.json`：**原檔一個位元組都不改**（同 SHA、保留原觀測日與原 capturedAt），只沿用 22:30 後擷取、30 小時內的；清單 `carried` 列出沿用了什麼，不沿用就在 `carryNote` 寫原因。這樣 06:30 巡檢才收得到前一晚 22:40／23:10 的信用（22:30 巡檢比收集早，收不到當晚的）。
   - 夜間排程多加 23:35 一次（GitHub 排程常延後或略過）。
   - Claude 已用網站 v254 的真實匯入程式離線核對：沿用的信用統計可正常匯入，`capturedAt` 保持原值。
   - Claude 11/06 17:39 已在 GitHub 上試跑（不推送）：auto 正確略過信用統計、讀到上一份套件；現在那份是今早 09:50 擷取的，`carryNote` 寫明「早於 22:30」所以不沿用；11/06 行情、名冊、總經、CPI、產業來源、新聞照常收到。
3. **套用順序**：中繼 main 依序 `git am relay-vix-fred.patch relay-credit-window.patch` → push。Claude 已在中繼 main `02c559a` 上依序重放：兩包都套得上、測試 61/61 過（47＋VIX 9＋信用時段 5）。
4. **讀回**：
   - 第 1 項：下一次免金鑰中繼（`data/keyless_snapshot.json`）的 coverage 明顯高於 17/61；VIXCLS 最新日期＝Cboe 最新收盤日、provider 寫 Cboe。
   - 第 2 項：之後的早上／下午清單 `window` 帶 `-no-statistics`，`carried` 裡的 `capturedAt` 落在前一晚 22:30～23:59（台北）；**套用後第一次 06:30 巡檢匯入的那份夜間信用，就是你保留的「v254 合規新匯入七列驗收」**（`capturedAt` 在前一晚 22:30 後、`previousDate`＝前一交易日、`captureDeferred=false`）。
   - 套用前的過渡期：若巡檢自動匯入了早上擷取的信用統計，照實記錄原 `capturedAt`，不算合規驗收；不要為此另建 run。

**報告**：寫 `diagnostics/deploy-20261026/hotfix12.md`（10 行內）：1、2 是否獲授權、中繼 commit、測試結果、兩項讀回。

</details>

<details><summary>11/05 23:05 版工作區塊（hotfix11 已交，備查）</summary>

**Claude 已核對 hotfix10（11/05 22:44）**：v249～v252 部署正確——HTML `de5a6d6b…` 相符、匿名化核對後台 `ff8dfc94…` 相符（證實差異只在 OPERATIONS.md 的專案 ID）、完整測試 exit 0、環境變數已設、`relayImport=ok`、五類 imported、`market=not_in_bundle`（09:52 那份清單本來就缺行情）、Gate 5／8 不採用、股災參考價五檔原文都正確。辛苦了。
**改網站程式一律先經擁有者授權，再部署；不要自行修改後部署。** 下面 1、2 項要等擁有者在你的對話裡親口授權後才做。

1. **中繼 patch 2＋網站 v253（擁有者 11/05 21:54 已在 Claude 對話說「好」；請等擁有者在你的對話裡再確認一次）**：`handoff/patches/relay-collector-retry.patch`（SHA-256 `3767e66c69c1062e28002fa6638c9718ec7656333756c56938b0fd2edeb83011`）在中繼 main `git am` → push；`handoff/patches/v253-collector-retry.patch`（SHA-256 `89d4971f4c192746178ffb78154968e83369084569570d6d8582e0bc1b5b4e50`）。Claude 11/05 22:04 已在 GitHub 上試跑 patch 2（不推送）：上市櫃 1990 檔 5 天行情（含 11/05）、名冊、總經、11/05 信用、CPI、產業來源、新聞全部收到，再用網站匯入驗證 7 類全過。
2. **網站 v254（新，等擁有者授權）：你回報的「信用七列缺 previousDate」**——原因是 v250 以後信用七列改從 GitHub 收集套件匯入（`importedTaiwanStatistics` 優先），這條路的 `validateTaiwanStatistics` 沒有這幾個欄位；v249 只修了網站自己直接抓的那條路。v254 在匯入路補上 `capturedAt`、`capturedAtBasis='external_collector_capture'`、`captureDeferred=false`、`previousDate`（同一份官方成交日表裡早於信用日的最近一天；表裡沒有就留空、標 `unknown`）。`handoff/patches/v254-imported-credit.patch`，SHA-256 `9f5da93cb360a3cd78d72a29e35c6bfb1bd0d72be77801590885e6acdbabea98`，基線＝v253（Claude tag v253-patch-head）；新增 `tests/v254-imported-credit.test.mjs` 2 項（在 v253 上失敗、套用後全過）；Claude 在乾淨 v253 重放無衝突、完整 `TZ=UTC npm test` exit 0。
   - v253＋v254 一起部署一次（現行 v249～v252 留回滾）。套完後 HTML 仍 `de5a6d6b…`；匿名化核對的後台應為 `99f2ce82f426493402e5bd6784f989e6f2396d022d9c9aa7113e1ef22abf5944`（只套 v253 時為 `4113671d…`）。
   - 讀回：下一次信用匯入後，信用七列 `previousDate`＝前一交易日、`capturedAt` 有值、`captureDeferred=false`。
3. **排程巡檢（最重要，不需改網站程式）**：今晨排程成功、22:30 平台 run 6 秒 failed、手動 22:41 成功。請比對失敗那次與手動那次：失敗時是否卡在「自動核准審查」或使用量限制（你這次推中繼 main 也是被自動核准審查擋下）。如果是，請在排程指令裡寫明「擁有者 2026-10-26 21:25 授權每日 06:30／22:30 自動巡檢：只做 POST `/api/automation/refresh-all` 與 GET status／history」，讓審查能認得授權；只改排程指令，不改時段與開關。寫出比對結果與修改內容。
4. **已知、先觀察**：GitHub 的 Official data collector 排程很不準（11/05 05:55 拖到 09:52，16:20、22:40 都還沒跑）。清單超過 36 小時網站就不匯入、照舊自己抓；Claude 的看門狗會在 30 小時時提醒擁有者手動按 Run workflow。你不用處理。

**報告**：寫 `diagnostics/deploy-20261026/hotfix11.md`（10 行內）：1、2 是否獲授權與部署結果（commit、SHA）、信用七列讀回、第 3 項比對與修改。

</details>

<details><summary>11/04 23:55 版工作區塊（hotfix10 已交，備查）</summary>

### 11/04 23:55 版（11/05 22:10 補 v253）
**已授權**：v249～v252、中繼 patch（擁有者 11/03 00:36／03:11／06:48／07:20）；**新增 11/05 21:54「好」＝收集程式下載中斷重試（網站 v253＋中繼 patch 2）**。**改網站程式一律先經擁有者授權，再部署；不要自行修改後部署。**
**Claude 已讀你的 hotfix9.md（11/04 23:30），核對結果**：
- 中繼 patch：你推的 fe9b5a1 九個檔與 Claude 的版本逐一相同（含執行權限），✅。
- 網站四包：HTML `de5a6d6b…` 完全吻合，✅。

**新增（11/05）：收集程式下載中斷重試**——11/05 第一次 Official data collector（排程 05:55 被 GitHub 拖到 09:52 才跑）抓證交所上市公司名單時兩次下載中斷（`http.client.IncompleteRead`），名冊與 5 天行情都沒收到（其他 5 類正常，Claude 已用網站 v250 匯入驗證離線核對通過）。改法：下載中斷（IncompleteRead、連線被重設）最多試 4 次、間隔 5／10／20 秒；逾時、HTTP 錯誤照舊最多 2 次、不等待。
- 中繼 patch 2：`handoff/patches/relay-collector-retry.patch`，SHA-256 `3767e66c69c1062e28002fa6638c9718ec7656333756c56938b0fd2edeb83011`，在中繼 main 上 `git am` → push（只改 vendored 收集程式、單元測試 +3、README／腳本註解的版本號）。Claude 在 GitHub 現在的 main（261bc2a）上重放，樹完全相同，47/47 通過。
- 網站 v253：`handoff/patches/v253-collector-retry.patch`，SHA-256 `89d4971f4c192746178ffb78154968e83369084569570d6d8582e0bc1b5b4e50`，基線＝v252（Claude tag v252-patch-head），只改 `scripts/collect-official-data.py`（和中繼那份逐字相同）。Claude 在乾淨 v252 重放無衝突、完整 `TZ=UTC npm test` exit 0（11/05 08:00 後，v237 那項也過了）。HTML 仍 `de5a6d6b…`；Claude 版後台檔 `4113671d9830f9ee413ef70060e1aea3f02e0b632ee96e87201685d2ffcb9892`。
- **部署鏈改為 v249→v250→v251→v252→v253，一樣只部署一次。**

**你列的三個阻擋，處理方式：**
1. **後台 SHA 不同（39c50457… vs 交接 ff8dfc94…）＝預期中，不是問題。** 後台檔會把 OPERATIONS.md 原文包進去；Claude 手上的 OPERATIONS.md 第 5 行把專案 ID 換成字面 `REDACTED_PROJECT_ID`（公開 repo 不能寫專案 ID），所以只差這一處。核對法（只在本機、做完還原，**不要把專案 ID 寫進任何公開檔或報告**）：把 OPERATIONS.md 裡的專案 ID 暫時換成 `REDACTED_PROJECT_ID` → `node build.mjs` → 後台檔 SHA 應為 `ff8dfc94f54fa4aa0673dbe6f7d0ee69fdfe0c019da3e2a3dd627258d704a0c3`（v252 為止；套完 v253 後應為 `4113671d9830f9ee413ef70060e1aea3f02e0b632ee96e87201685d2ffcb9892`）→ `git checkout OPERATIONS.md` → 再 `node build.mjs`，回到你自己的 SHA，**部署用這一份**。若換完對不上，停下並把 `git diff` 的檔名（不含內容）寫進報告。
2. **v237-fixes.test.mjs:30 失敗＝測試本身的日期邊界，不是網站錯誤。** 網站把「觀測月 2026-08-01」算到當天 23:59:59，測試的預期值從 00:00 起算，兩者差 1 天；只有在台北 11/04 08:00～11/05 08:00 這 24 小時會不一致（網站 94.7 天＝仍有效，測試算 95.7 天＝預期過期）。**台北 11/05 08:00 以後重跑完整 `TZ=UTC npm test` 就會 exit 0**；不要改程式或測試。
3. **official-import 清單：已經有了**（11/05 09:52 第一次排程建立；擁有者也可在 GitHub 網頁按 Run workflow）。**部署也不必等清單齊全**：缺的類別巡檢只記「這次沒收到」並照舊自己抓，不會出錯。

**接下來（11/05 08:00 以後）：**
- A. 先套中繼 patch 2 並 push；網站依序套 v249～v253 → 重跑完整 `TZ=UTC npm test`（應 exit 0）＋上面第 1 點核對 → **部署一次**（現行 v248 留回滾），同時設 `RELAY_OFFICIAL_IMPORT_ENABLED=true`。
- B. **巡檢排程壞了，請查清楚並修好（這是最重要的一件）**：11/01～11/04 每天 06:30／22:30 的排程都沒有產生網站 run，11/04 22:30 那次 3 秒就 `no_update` 結束。請讀出排程任務的設定與最近幾次的輸出，寫出「為什麼沒呼叫 refresh-all」；修正排程指令讓它每次都 POST `/api/automation/refresh-all` 並輪詢到 `completedAt`（巡檢已於 10/26 授權啟用；只改排程指令，不改網站程式）。修好後手動觸發一次排程驗證。
- C. 部署後第一次巡檢讀回（同上一版第 3 項）：`relayImport`／`officialImport`、信用 `previousDate`、Gate N/N 與 `retried`、5 檔 Gate 5／8「不採用」、5 檔部署前後評級、股災參考價那一行原文。
- D. 之後例行同上一版第 4 項：晨晚各一次 `officialImport` 正常後，停止手動收集＋匯入；每天只觸發巡檢、有異常才詳細回報。

**報告**：寫 `diagnostics/deploy-20261026/hotfix10.md`（12 行內）：中繼 patch 2 的 commit、第 1 點核對結果（只寫 SHA，不寫專案 ID）、完整測試結果、部署版本與 SHA、環境變數、B 的原因與修正、C 的讀回。

</details>

<details><summary>11/03 07:35 版工作區塊（hotfix9 已交，備查）</summary>

### 11/03 07:35 版
**已授權**：擁有者 11/03 00:36「好」＝網站 v249；**11/03 03:11「第二項照做」＝官方資料收集搬到 GitHub 中繼排程、網站巡檢自己匯入（中繼 patch＋網站 v250）**；**11/03 06:48「第一條我同意」＝分析師共識、EPS surprise、法說指引不列入評級（網站 v251）**；**11/03 07:20「好」＝估值區加「股災本益比參考價」（網站 v252，只作參考）**。**提醒：改網站程式一律先經擁有者授權，再部署；不要自行修改後部署。**
**目的**：之後你每天只要觸發巡檢、讀結果、有異常才回報；不必再手動跑官方收集程式和匯入。
**背景（不用做）**：擁有者 11/03 也看過第 38 輪回測（gate-probe `results/backtests/round38/`）：成長率不設上限、改用股災本益比當評級區間都沒有比現行好，估值算法維持；均線扣級有效，保留。股災本益比改成 v252 的「參考價」，只看不評。Claude 另設了巡檢看門狗（每天 08:47、23:47 只讀檢查，異常才通知擁有者）。
**最新巡檢紀錄停在 10/31 22:42（run f2a63289… 還在 stocks 階段）**，11/01、11/02 沒有任何紀錄。請先補記：10/31 晚間那次是否完成（completedAt、Gate N/N），以及 11/01～11/03 每天 06:30／22:30 排程是否有跑（平台 runId、網站 runId、狀態）；沒跑就寫 HTTP 與原因。

1. **中繼 patch（先做；只改公開中繼 repo，不動網站）**：`handoff/patches/relay-official-collector.patch`，SHA-256 `242b02a3033bc96996e854430209f9932742a5989f05ca5404f4232fdbe7de6b`。在 macro-relay-service 的 main 上 `git am` → push。
   - 內容：新工作流程 Official data collector（台北 05:55 每天、16:20／22:40／23:10 週一至週五）在 GitHub 跑網站同一份官方收集程式（`vendor/site-collector/`，只有官方公開網址與解析，沒有金鑰、沒有網站網址），把部分檔＋`manifest.json`（每個檔的類別、大小、SHA-256、收集失敗項目）強制推到 `official-import` 分支，只留最新一份。格式不符、超過 3.9MB、只有失敗紀錄的 CPI／新聞不發布。
   - Claude 已在乾淨 main 上 `git am` 重放（樹完全相同）、中繼全部單元測試通過；GitHub 試跑（gate-probe 的 relay-collector-dryrun，不推送）：上市 1093＋上櫃 897 檔 5 個交易日、名冊、總經 9 條、信用統計、核心 CPI 兩來源（BLS 走官方 API 備援）、產業來源、官方新聞全部收到；套件約 3.4MB，每檔都在網站單次上限內。再用網站 v250 真正的匯入驗證離線跑這份套件：7 組全部通過並寫入（掃描 11/02、覆蓋 98%；CPI BLS＋FRED 一致；IORB 含發布日核對；信用 11/02），匯入過程沒有任何對外連線。
   - push 後：Actions → Official data collector → Run workflow（publish 用預設 true）跑一次；確認 `official-import` 分支有 `manifest.json`，記下 parts 與 errors。
2. **網站 v249＋v250＋v251＋v252（都已授權，依序套用、只部署一次，現行版留回滾）**：
   - v249：`handoff/patches/v249-credit-gate-20261102.patch`，SHA-256 `c938cf2a4a52161dd278c99e7bb67f2724644b3f3afc42e63f297b437b63f55f`（內容同上一版交接：晚上信用 `previousDate` 改前一交易日；Gate 審計單步逾時重試一次）。
   - v250：`handoff/patches/v250-relay-import.patch`，SHA-256 `34ac240175ff6fdbd7ac27827244b037e088a661cab83c2767551f10075d1896`，基線＝v249（Claude tag v249-patch-head）。只改後台、說明與測試。
   - v250 內容：巡檢開頭（scanner 之前）讀 `official-import` 清單（超過 36 小時、格式不符就不匯入）→ 每次輪詢匯入一組（行情＋名冊、總經序列、信用統計、核心 CPI、產業來源、官方新聞），走和 `/api/official-data-import` 完全相同的驗證；雜湊不符不送、內容沒變不重匯、失敗只記錄並在下次巡檢重試，不擋掃描與 Gate。巡檢紀錄多 `relayImport` 與覆蓋列 `officialImport`。收集程式多 `--skip-statistics`；抓 FRED 時第一次改用 Python 預設 User-Agent（GitHub 實測：FRED 只讓這個字串通過，其他逾時或中斷），第二次仍用原本字串。
   - **環境變數**：部署時設 `RELAY_OFFICIAL_IMPORT_ENABLED=true`（沒設＝與 v249 完全相同；要停用就移除）。
   - 測試：新增 `tests/v250-relay-import.test.mjs` 6 項（未啟用的那項在基線上也過，其他 5 項在基線上失敗、套用後全過）。Claude 在乾淨基線重放 v250 無衝突、完整 `TZ=UTC npm test` exit 0、HTML 與後台檔都相同。
   - v251：`handoff/patches/v251-analyst-not-used.patch`，SHA-256 `209106b7cfccfd6e04c2fa56fcdfbadf7daa5073d455ddf3b2e01483c47a343a`，基線＝v250（Claude tag v250-patch-head）。內容：Gate 5（法說指引／EPS surprise）、Gate 8（分析師共識／同業共識）改列「不採用（擁有者決定）」——不阻擋、評級不再因缺這些資料壓在 B+、取消 0.85 共識係數、共識不參與估值分歧；原本讀到的狀態保留在 `collectedStatus`，資料與來源照舊列出只作參考。巡檢覆蓋列 guidance／epsConsensus 改 `not_used`（不再讓巡檢永遠 partial）。估值（自身 EPS × 歷史本益比）、財報品質、否決、均線扣級、估值分歧 2 倍規則都不變。
   - v251 測試：新增 `tests/v251-analyst-not-used.test.mjs` 4 項（在 v250 上全部失敗、套用後全過）；更新 7 個舊測試裡「Gate 5／8 阻擋、B+ 上限、0.85」的斷言。Claude 在乾淨 v250 重放無衝突、完整 `TZ=UTC npm test` exit 0、HTML 與後台檔都相同。
   - v252：`handoff/patches/v252-crash-reference.patch`，SHA-256 `4ba668916c9516f50fa8dce8a800bb6ca30764bc933f48cf9427271e12e6893b`，基線＝v251（Claude tag v251-patch-head）。內容：估值區多一行「股災本益比參考價（左側交易參考，不影響評級）」＝今年模型 EPS × 這檔股票在股災日的本益比 P20／中位／P80；並列現價位置、大盤距前一年高點幾 %（是否股災）、今年 EPS 超過過去常態 2 倍時的「景氣高峰」提醒。股災日來自 gate-probe 公開檔 `exports/market-crash/latest.json`（證交所 MI_5MINS_HIST；規則：加權指數 ≤ 前 250 交易日最高 × 85%；gate-probe 平日 14:45、21:40 自動更新；網站存 D1 12 小時）。個股快照多存近 5 年每日本益比（`panelInputs.perHistory`），所以**每檔要等下一次個股更新後才出現參考價**，之前會顯示「下次個股更新後出現」。評級、Gate 都不受影響（測試逐欄比對）。
   - v252 測試：新增 `tests/v252-crash-reference.test.mjs` 7 項（在 v251 上失敗、套用後全過）；`financial-analysis` 測試把這個公開檔加入允許清單、`cross-market-live` 版面鎖定排除新標記的那一行。Claude 在乾淨 v251 重放無衝突、完整 `TZ=UTC npm test` exit 0、HTML 與後台檔都相同。
   - **四份都套完後**：`dist/index.html` SHA-256 應為 `de5a6d6bd6b55b777985fb05b50b455b0db7c6ec8b4c476a6e8905211da37deb`，後台檔 `ff8dfc94f54fa4aa0673dbe6f7d0ee69fdfe0c019da3e2a3dd627258d704a0c3`。
3. **部署後第一次巡檢讀回**：`relayImport.status`、各組 status（imported／unchanged／not_in_bundle／error 與原因）、`officialImport` 覆蓋列；再直接讀 `/api/market-scanner`（場次數、最新日）、`/api/macro`（9 條序列觀測日）、`/api/core-cpi-history`，和匯入結果比對。另照上一版交接讀回 v249：信用七欄 `previousDate` 是否為前一交易日；Gate N/N 與有無 `retried`。v251：5 檔的 Gate 5、Gate 8 卡都顯示「不採用（擁有者決定）」、不再是阻擋；列出 5 檔部署前後的評級（預期只有原本被 B+ 上限壓住的會變）。v252：巡檢更新個股後，5 檔估值區的「股災本益比參考價」那一行原文（低／中／高、股災日天數、大盤距高點 %）。
4. **之後的例行（讀回正常後開始）**：晨間＋晚間各有一次巡檢 `officialImport` 為 automatic（或只有 not_in_bundle）之後，**停止手動跑官方收集程式和匯入**。每天只做：照原排程 POST `/api/automation/refresh-all` → 輪詢到 `completedAt` → 寫一筆簡短紀錄；**只有異常才詳細回報**（Gate n<m、`officialImport` 為 source_error、巡檢卡住、中繼套件超過 30 小時沒更新）。`officialImport` 連續兩次失敗時，才改回手動收集＋匯入當備援。
5. **SLOOS 換期（11/03 起的晨間巡檢核對）**：你的 SLOOS 發布窗到 11/03 03:00（台北）到期；Fed 11/02 14:00（美東）公布 10 月調查。請讀回 SLOOS 那一列的觀測日、數值、status、reason：應換成 2026-10-01 新一期且 ok；若變 stale，寫出原因，不要延長舊窗。

**報告**：寫 `diagnostics/deploy-20261026/hotfix9.md`（15 行內）：上面「補記」；中繼 patch 與第一次 Official data collector 的 run 與清單摘要；v249～v252 版本、HTML 與後台檔 SHA、環境變數；第 3 項讀回（含 5 檔評級前後、參考價那一行）；第 5 項。

</details>

<details><summary>10/29 的工作區塊（已完成，備查）</summary>

### 10/29 工作區塊（10/29 16:10 更新；只讀這一段就夠，下方各節是細節備查）
**已授權**：擁有者 10/29 06:23「好」＝網站 v246（美元卡畫面）；14:41「收起來好了」＝網站 v247（Gate 卡只顯示一句結論）；15:35「好」＝網站 v248（來源修正）。**v246、v247、v248 依序套用、只部署一次**（v245 留回滾）。部署後 `dist/index.html` SHA-256 應為 `878292cd516b7c424757bc8af8db69f122a0a3f70a66e2bdd301ecb5063bc5ce`（取代 1、1b 寫的中間值）。
**已完成，不用再做**：v245 已上線（你的 hotfix7.md，HTML `7a5fabb1…`）；v234 信用 ①③ 通過；② 的 27 仟元差是證交所自己修正了 10/27 的融資餘額（10/28 報表前日餘額 623,386,833），網站 10/28 數字和官方一致，不用再查；手機畫面你那邊不能設定視窗大小，**不用再試**（由擁有者用手機看）。

1. **網站 v246**：你上次讀到的是 06:00 版交接，還沒套 v246。`handoff/patches/v246-dollar-channel-20261029.patch`，SHA-256 `84372778256934bced08321e63cb730ff9c9bc9095a35b93b22967a88741bb5a`，基線＝v245（就是現在正式站）→ `git apply` → `node build.mjs` → `TZ=UTC npm test`（exit 0）→ 部署。部署後 `dist/index.html` SHA-256 應為 `7c12dd6dd462d38ec8a245855e1e31b6b3128350afbb0d5a3a8c3caacda0de35`。
   - 只改總經區美元卡畫面（後台、規則、分數都不變）：零軸圖上方多一張「美元指數＋前 20 日最高（紅）／最低（綠）」通道圖，兩張圖日期對齊、突破日 ▲▼；卡片多兩行（距前 20 日最高 %、高低差；和上一筆比，這次是美元在動還是高低線在動）；數字表 8 欄。
   - 讀回（桌面即可）：版本、HTML SHA；美元卡兩張圖、▲▼、兩行新文字、數字表 8 欄；10/21 那筆零軸仍是 −57.82。
1b. **網站 v247（接在 v246 後，和 v246 同一次部署）**：`handoff/patches/v247-gate-fold-20261029.patch`，SHA-256 `e37febe4cd6bdfeea9c6b97e399b9aa40354d374171ecf09127f032d81ab8a69`，基線＝v246（Claude tag v246-patch-head）。兩份都 `git apply` → `node build.mjs` → `TZ=UTC npm test`（exit 0）→ 部署一次。部署後 `dist/index.html` SHA-256 應為 `03942e32f23bfc341eb037b3229489b937760f6b2c09c0f48833c351e83b3fd6`（取代上面 v246 的 `7c12dd6d…`）。
   - 內容（就是你上次報的「去重」）：每個 Gate 卡只顯示一句結論（例如 Gate 6「財報品質有警訊：營業現金流為負…（數字見財報品質卡）」）；含數字的判讀說明與替代規則收進「完整判讀說明（含數字）」，點開才看。進場條件的財報警示、退避評級的主情境說明不再重抄 CFO／淨利倍數與 Base 情境價；三問技術題不再重抄收盤價（改寫收盤在 60 日線上／下，60 日線數值保留）。評級、Gate、門檻、風險預算都不變；舊的存檔結果沒有結論句時照舊顯示。
   - 測試：新增 `tests/v247-gate-fold.test.mjs` 與 `dashboard-interactions` 一段（10 個 Gate 都有結論句、結論句不含數字、說明收在 details 裡）；更新 `v237-rules`、`phison-panel`（比較時略過新欄位 headline）、`dashboard-interactions` 原本的情境數字斷言。Claude 在乾淨 v246 重放無衝突、完整 `TZ=UTC npm test` exit 0、HTML 與後台檔都相同；桌面 1200px、手機 390px 截圖無錯誤。
   - 讀回：開 8299，10 個 Gate 卡都只看到一句結論＋「完整判讀說明（含數字）」等摺疊；點開 Gate 6 看得到 ROIC／CFO／FCF 數字；評級、進場、出場、Gate 狀態與部署前相同。
1c. **網站 v248（接在 v247 後，和 v246、v247 同一次部署）**：`handoff/patches/v248-sources-20261029.patch`，SHA-256 `9c5d2947a760c88ab680230b20077435f046692a7e422757f809f77fcedaa469`，基線＝v247（Claude tag v247-patch-head）。內容（你 10/29 讀回的三項）：
   - ① 貴金屬第三來源 GoldPriceZone 10/29 起 HTTP 404 → 改 **Swissquote 公開報價**（`forex-data-feed.swissquote.com/public-quotes/bboquotes/instrument/XAU|XAG/USD`，取點差最小一檔的買賣價中間價、伺服器時間戳；GitHub 10/29 實抓 HTTP 200）。三來源 2/3 規則不變。
   - ② 信用七欄：延後抓取時也列出 `capturedAt`（與依據 `capturedAtBasis`）；晚上直接抓取也標 `capturedAt`；巡檢摘要逐列保存 `verifiedAt`／`capturedAt`／`captureDeferred`，可以和直接讀回逐欄比。
   - ③ 新股 6898 程曦資訊、6938 藍新資訊：TPEx 名冊上櫃日期 2026-10-23，但名冊 10/28 才收錄，所以 10/23、10/27 行情沒收進來（只有 1/21）。程式現在會列出缺的日期（`missingDates`）與補抓方法；規則不放寬。
   - 測試：新增 `tests/v248-sources.test.mjs` 3 項（含 Swissquote 實抓格式 fixture；在 v247 上全部失敗、套用後全過）；`macro-market-state` 的第三來源替身改 Swissquote。Claude 在乾淨 v247 重放無衝突、完整 `TZ=UTC npm test` exit 0、HTML 與後台檔都相同。
   - **部署後一次性補抓（③ 需要）**：官方收集器跑一次 `--market-only --sessions 5` 並照常匯入（會用目前名冊重抓 10/22～10/28，6898、6938 補上 10/23、10/27）。之後**每天跑收集器都改用 `--sessions 5`**（多抓的幾天會覆蓋成同一份官方資料，新股名冊晚收錄時自動補齊）。不改排程時段與開關。
   - 讀回：金價、銀價三來源可用數與 Swissquote 那筆；信用七欄的 `capturedAt`；6898、6938 觀測數與是否列為新股暖機、Gate 3 產業 RVOL 覆蓋（應不再卡在 37/39）。
2. **今晚 22:30 巡檢讀回（照你已加的一次性指示）**：5 檔個股摘要與直接讀回是否一致（`refreshedThisRun`／`stepStatus`）；擴展總經、市場／貴金屬、美股指數的 status、usable/total、`refreshState`、`finalizeWaits`；貴金屬三行判讀原文。
3. **「去重」**：擁有者已決定收起來，就是上面的 v247；部署後照 1b 的讀回核對即可。
4. **5289**：Gate audit 摘要的 `status`（valuation_divergence）和 `auditStatus`（blocked）是同一次計算的兩個欄位，同欄位比才算。

**報告**：寫 `diagnostics/deploy-20261026/hotfix8.md`（15 行內）：v246＋v247＋v248 版本與 HTML SHA、美元卡讀回、Gate 卡讀回、1c 讀回；第 2 項（22:30 跑完後補）。


</details>

<details><summary>上一輪（10/28 04:00～10/29 00:40）的工作區塊，已完成，備查</summary>

### 上一輪工作區塊
**全部已授權**（擁有者 10/28 03:37「好」＝中繼；03:39「個股那邊要做整合…不要重複顯示」＝網站 v243；**10/29 00:08「好」＝網站 v244**；巡檢 10/26 已授權啟用）。依序做，最後只寫一份報告。

1. ~~**中繼（不用部署網站）**~~（**已完成**：你已推上 dbb74bf；10/27、10/28 類股指數與信用都已讀到，不用再做）：`handoff/patches/relay-twse-sector-credit-20261028.patch`，SHA-256 `c0acfc540376edb4250f7e66a02c93ec7e07e2f94473ab9b97944e65da7142e7` → macro-relay-service `git am` → `python -m unittest discover -s tests`（應 38/38）→ 推上 main（keyless 工作流程自動跑）。內容：類股指數改讀證交所日報（OpenAPI 停在 10/22）；每個交易日台北 22:50 多跑一次收融資融券。
2. **網站 v243（部署一次，v242 留回滾）**：`handoff/patches/v243-stock-integration-20261028.patch`，SHA-256 `ef550038f6600346ff869d239c3b7520dcc25843481a21060e24d92c42a93c40`，基線 v242 → `git apply` → `node build.mjs` → `TZ=UTC npm test`（exit 0）→ 部署。部署後 `dist/index.html` SHA-256 應為 `7a5fabb193d7c85b95079a98bc3f0b99f1fde252233937bd0bdb9d65a60cbd60`（`SITE_BUILD_ID` 會和 Claude 的不同，屬預期）。內容：個股區同一件事只在後台算一次、同一數字只顯示一處（細節見下方 ⑩）。
2b. **網站 v244（接在 v243 後；兩份可一起套用、同一次部署，v242 留回滾；若 v243 已上線就只套這份再部署一次，v243 留回滾）**：`handoff/patches/v244-patrol-summary-20261029.patch`，SHA-256 `13d4c74c7e537c9ccc721f1bde6070deeb40dbc308cd40357dca18ec520201ca`，基線＝v243（Claude tag v243-patch-head）→ `git apply` → `node build.mjs` → `TZ=UTC npm test`（exit 0）→ 部署。**只改後台與測試，網頁不變**：`dist/index.html` SHA-256 仍是 `7a5fabb193d7c85b95079a98bc3f0b99f1fde252233937bd0bdb9d65a60cbd60`。內容（你 10/28 夜間巡檢讀回的三個問題）：
   - ① **個股摘要**：巡檢結束時讀回每檔個股快照一次；本次巡檢開始後才存好的快照記為本輪已更新（`ok`／`partial`，帶 `refreshedThisRun`、`stepStatus`、`summaryScope:final_readback`）；快照仍早於本輪就維持 `pending` 並註明「背景更新仍未完成」。巡檢中快取仍新的 `fresh` 不動。
   - ② **模組摘要**：手上有真實快照、只是背景下一次更新還沒落地 → 依各項官方觀測日重新判斷後的可用數給狀態（擴展總經 11/12＝`partial`、市場／貴金屬 36/36＝`ok`、美股指數 3/3＝`ok`），另標 `refreshState:background_refreshing` 與 `snapshotCheckedAt`；只有完全沒有快照或快照超過 36 小時才維持 `pending`。過期項目照樣不算可用。另修兩個根因：擴展總經、美股指數的本機記憶體舊快照不再蓋住 D1 裡別的執行個體存好的新快照；背景更新卡住超過 3 分鐘會重新開始（市場／貴金屬也是）。
   - ③ **貴金屬判讀**：來源數只寫核對紀錄裡真的有的數字（金銀比改寫「金價 x/3、銀價 y/3 來源可用」），不再補預設值，不會再同時出現「核對通過」和「0/2 可用」。
   - 不改任何計算規則、評級、Gate、門檻、風險預算、時段。新增 `tests/v244-patrol-summary.test.mjs` 4 項（在 v243 上全部失敗、套用後全過）；`v236-keepalive` 的舊規則斷言改成新規則。Claude 在乾淨 v243 重放無衝突、完整 `TZ=UTC npm test` exit 0、後台檔與 Claude 建置完全相同。
3. **巡檢排程（只查、不改設定）**：06:30、22:30 兩次都 3 秒結束、網站沒有 run。用和排程**完全相同的指令與工具**手動跑一次，記下第一個失敗的步驟、HTTP 狀態、錯誤訊息；若是排程環境拿不到網站工具，寫「平台限制」就停（細節見下方 ⑧）。

4. **（只讀回，不改程式）v234 跨日驗收**（原定 10/28 08:30 由 Claude 核對，但昨晚 22:30 與今早 06:30 巡檢都沒有網站 run，無法核對）：讀網站 `/api/macro-market` 的 7 項信用欄位，寫出①觀測日是否已是 10/27（證交所 10/27：融資金額今日餘額 623,386,860 仟元＝6,233.87 億、前日餘額 633,880,174 仟元）、是否還有 `statistics_not_latest_session`；②10/22 那筆是否升為 final 且數值不變（10/27 報表前日餘額＝10/22 今日餘額 633,880,174）；③verifiedAt 是否保留原擷取時間；④run 摘要與直接讀回是否一致。若網站還沒擷取 10/27 信用，就寫「未擷取」與原因，不另跑手動匯入充數。

**報告**：只寫 `diagnostics/deploy-20261026/hotfix6.md`（15 行內）：
- 中繼：工作流程 success；`keyless_snapshot.json` 的 5 個類股指數日期與值；融資融券 5 項的日期（22:50 那次後應為當天）。
- 網站：版本、HTML SHA；開 8299（手機也看）個股區順序正確、沒有「畫面呈現未完成」；收盤價只在追蹤清單卡、20 日線只在「持有與強弱」、估值情境只在估值區、ROIC／CFO／FCF 只在財報品質卡；五檔評級、進場、出場、Gate 與部署前相同。
- v234 跨日：上面第 4 項的 ①～④。
- 巡檢：手動測試的實際結果（失敗步驟／HTTP／訊息，或「平台限制」）；今晚 22:30 那次的平台 runId、網站 runId、狀態、Gate N/N（沒有就寫 HTTP 與 reason）。
- v244（部署後第一次巡檢）：5 檔個股摘要狀態與直接讀回是否一致（`refreshedThisRun`／`stepStatus`）；擴展總經、市場／貴金屬、美股指數三個模組的 status、usable/total、`refreshState`；貴金屬三行判讀原文（不應同時有「通過」和「0/2」）。


</details>

## 現在 ⑨（**已授權**：擁有者 2026-10-28 03:37「好」）：中繼修正——證交所類股指數改讀日報、晚上 22:50 多跑一次收信用統計（只改中繼，不動網站）
- 原因（擁有者 10/28 03:15 截圖：融資餘額等信用卡片、類股指數停在 10/22）：
  - 10/23、10/26 證交所沒有交易（FMTQIK 交易日 10/22 → 10/27；10/26 為光復節補假），所以 10/22 之後第一筆是 10/27。
  - 信用統計：證交所當天晚間才公布；網站只在台北 22:30～24:00 自己抓，靠 22:30 巡檢觸發（沒跑）；中繼每 6 小時一次（20:23 太早、02:23 那次還沒跑完）→ 一直沒拿到 10/27。Claude 10/28 03:20 用 GitHub 實抓：10/27 信用已公布（融資金額 633,880,174 → 623,386,860 仟元）。
  - 類股指數：中繼讀的 OpenAPI `openapi.twse.com.tw/v1/exchangeReport/MI_INDEX` 10/28 03:20 仍停在 10/22，被「與加權指數同日」檢查擋下；證交所日報 `www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=20261027&type=IND&response=json` 已有 10/27（電子 2,867.31、半導體 1,529.82、金融 3,770.57、航運 217.51、鋼鐵 126.74）。
- Patch：`handoff/patches/relay-twse-sector-credit-20261028.patch`（`git format-patch`，1 個 commit），SHA-256 `c0acfc540376edb4250f7e66a02c93ec7e07e2f94473ab9b97944e65da7142e7`。在 macro-relay-service `git am` 後推上 main。
- 內容：① `twse_sector_metric` 先讀證交所日報（指定日期、stat OK、日期必須等於加權指數日），失敗才用 OpenAPI（仍要同日）；兩者都不同日就不收、沿用舊值標過期（不補值）。② `keyless.yml` 加 `cron: '50 14 * * 1-5'`（台北週一至週五 22:50），信用統計當晚就收到，不靠網站巡檢。不改其他序列與既有排程。
- 測試：新增 `tests/test_twse_sector.py` 3 項（10/28 實抓的日報與 OpenAPI 原始回應）；Claude 在最新 main 07f5002 上 `git am` 後 `python -m unittest discover -s tests` 38/38 通過。
- 讀回（併入上方「本輪工作」的 `hotfix6.md`）：工作流程 success；`keyless_snapshot.json` 的 TWSE_ELECTRONIC／SEMICONDUCTOR／FINANCIAL／SHIPPING／STEEL 日期與值（應為最新交易日）；TWSE_MARGIN_BALANCE_NTD 等 5 項的日期（當晚 22:50 那次後應為當天）；網站其他市場卡片的融資餘額與類股指數日期。

## ⑩（**已授權**：擁有者 2026-10-28 03:39「我是說個股那邊 要做整合 同一只做一次計算 還有不要重複顯示」）：v243 個股區整合（一次部署，v242 留回滾）——⑨ 之後做
- Patch：`handoff/patches/v243-stock-integration-20261028.patch`，SHA-256 `ef550038f6600346ff869d239c3b7520dcc25843481a21060e24d92c42a93c40`；基線＝v242（你的 c9e2577＝Claude tag v242-patch-head）。不含 dist/server/index.js。只改網頁（dist/index.html）與測試，後台程式不變。
- 內容：
  1. **只算一次**：瀏覽器原本在後台結果到之前，自己用未還原的均線、本機紀錄另算一份 10 個 Gate、四象限、整體檢驗報告、「收盤高於／低於 20／60 日均線」趨勢列；全部拿掉，後台還沒算完就顯示「後台正在計算」。整體檢驗報告的「機會訊號」改用後台 `report.positives`。
  2. **不重複顯示**：個股區改成 搜尋 → 追蹤清單 → Master Model（評級、大盤持股與個股決策、進場條件、持有與強弱，接著 10 個 Gate、整體檢驗報告，人工補登工具放最後）→ 今年 EPS × 歷史 P/E → 財報品質與估值輸入 → 財報解讀 → 資料來源與自動資料池。拿掉的重複：個股資料區的收盤／月營收／估值摘要三格、四象限、Master Model 明細格裡的收盤價／今年 EPS／目前本益比／歷史 P/E 區間／情境價／20 日線／ROIC／CFO／FCF（各自在追蹤清單卡、估值區、持有與強弱、財報品質卡已有）；財報資料來源區只留三張財報的筆數與期別；整體檢驗報告的已核實證據與風險只列 Gate 名稱，不再重抄每個 Gate 全文。月營收（金額、年增、月增）改放在「財報品質與估值輸入」。
  3. 估值文字遇到缺欄位不再讓整段畫面出錯（`forecastEps?.basis`）。
- 不改任何計算規則、評級、Gate、門檻、風險預算；所有表單與控制項都保留。
- 測試：新增 `tests/v243-stock-dedup.test.mjs` 2 項＋`dashboard-interactions` 1 段（後台還沒到時不另算 Gate／四象限／報告）；`cross-market-live` 的版面指紋：個股區新順序記在 `layout-v212.json` 的 `stockSectionV243`（原 v212 指紋保留）。Claude 在乾淨 v242 重放無衝突、完整 `TZ=UTC npm test` exit 0、10 組獨立腳本全過；`dist/index.html` SHA-256 `7a5fabb193d7c85b95079a98bc3f0b99f1fde252233937bd0bdb9d65a60cbd60`。`SITE_BUILD_ID` 會與 Claude 的 4454ee67… 不同（你的 OPERATIONS.md 有私人內容），屬預期。
- 步驟：`git apply` → `node build.mjs` → `TZ=UTC npm test` → 部署一次（v242 留回滾）。
- 讀回（併入上方「本輪工作」的 `hotfix6.md`）：① 版本、SHA；② 開 8299（手機也看一次）：個股區順序、畫面沒有「畫面呈現未完成」；③ 同一數字只出現一次（收盤價只在追蹤清單卡、20 日線只在「持有與強弱」、估值情境只在估值區、ROIC／CFO／FCF 只在財報品質卡）；④ 五檔評級、進場、出場、Gate 狀態與部署前相同；⑤ 後台還沒算完時（切到新股票的頭幾秒）顯示「後台正在計算」而不是另一份評級。

## 之後 ⑧（巡檢已授權啟用；本項只查原因與做一次測試，不改時段與開關）：為什麼排程 3 秒就結束、網站沒有 run
- 事實：06:30（34405943…）與 22:30（079f2599…，22:32:28～22:32:31）兩次都在 **3 秒內**結束、`no_update`、網站沒有新 run。真正的巡檢要 POST＋每 10 秒輪詢到 completedAt，至少要幾分鐘；3 秒代表排程那一輪**根本沒有呼叫網站**（或一開始就放棄）。指令補強後仍一樣，所以問題不在指令文字。
- 請查（寫進 `patrol-enabled.md`，6 行內，不寫私人入口／識別／憑證）：
  ① 排程執行時能用哪些工具：有沒有呼叫網站的那個工具／連接器？（若排程環境沒有網站工具，就一定 3 秒 no_update）
  ② 指令裡「網站入口」從哪裡來：是寫在指令裡，還是要讀「站內保存說明」？排程那一輪讀得到嗎？
  ③ 用**和排程完全相同的指令與工具**手動執行一次（平台若有「立即執行／測試」就用它；沒有就開新對話貼同一段指令），把該輪實際輸出（第一個失敗的步驟、HTTP 狀態、錯誤訊息）照實寫下；這次手動測試不算排程驗收。
  ④ 若確定是排程環境拿不到網站工具，寫「平台限制」並停在這裡，由 Claude 與擁有者決定替代做法；**不要自己改排程或加新排程**。

## 已完成（10/27 21:15）⑦-0（**已授權**：擁有者 2026-10-27 17:57「好」）：補強每日巡檢的排程指令——**請在今晚 22:30 之前完成**
- 照你在 `patrol-enabled.md` 提的補強，把「台股整站每日巡檢」排程的儲存指令改成明確三步，其餘設定（06:30／22:30、is_enabled=true、服務存取身分）不變：
  「每輪明確 POST /api/automation/refresh-all → 每 10 秒 GET /api/automation/status，直到同一 runId 出現 completedAt → GET /api/automation/history 核對完成時間與各檔 Gate 快照；即使沒有建立 run，也要回報 HTTP 狀態與 reason，不可靜默省略或回報 no_update。」
- 私人入口網址、專案代號、憑證不要寫進任何公開 repo；`patrol-enabled.md` 只記「已改指令（時間）」與改後的三步摘要。
- 22:30 跑完後照原格式補一行：平台 runId、網站 runId、completedAt、狀態、Gate N/N、watchlistSource、檔數；若沒建立 run，寫出 HTTP 狀態與 reason。

## 已完成（v241 讀回，10/27 21:11）⑦-2（**已授權**：擁有者 16:30「好我授權」＋16:30「把它拉出來放大放在這裡」）：v241 讀回（若還沒部署就先部署）
- Patch：`handoff/patches/v241-shares-dollar-20261027.patch`，SHA-256 `d66ab28b0b1dee76937cb0b89bdc45678f1bcb202f57db233615e75ebb1dd4c4`（與 16:50 同一份，已放回）；基線＝v240（d871583）。部署後 `dist/index.html` SHA-256 `10ebd5bcbb23cc52f53aceaf615f176e1109969179ac0f0b0acee8fb1268a5e3`。
- 內容：① 上市、上櫃股數名冊各自存 D1、某份失敗沿用 7 天內同一份官方名冊（註明沿用）、15 分鐘重試、等待 10 秒、缺股數快照只留 1 小時；② 美元大卡移到總經區（`GET /api/dollar-index`）。
- 先確認正式站目前的版本與 HTML SHA：是 `10ebd5bc…` 就只做讀回；還是 v240（`05c731ec…`）就先照常 `git apply` → `node build.mjs` → `TZ=UTC npm test` → 部署一次。
- 讀回（寫 `diagnostics/deploy-20261026/hotfix5.md`，6 行內）：版本與 SHA；8299／5289／5009 發行股數與來源（直連或「沿用」）；三檔 Gate 9（預期回到 v240 前：8299／5009 conditional、5289 partial，不同寫原因）；美元大卡位置與 `/api/dollar-index` 的 axis.value；評級與風險預算不變。

## 已完成（v242，10/27 21:20；hotfix5.md）⑦-3（**已授權**：擁有者 17:02「好一次處理」＋17:21「看不出來哪裏是0軸」）：v242＝後台只算一次＋美元零軸圖（一次部署，v241 留回滾）
- Patch：`handoff/patches/v242-compute-once-zeroaxis-20261027.patch`，SHA-256 `f1c8f4a890e886d051365f806e0f08d3291dc6045b933285eb2d86bf6ecb0071`；基線＝**v241**（Claude tag v241-patch-head）。不含 dist/server/index.js。
- **1. 後台只算一次（擁有者 17:02）**：
  - 總經分數只在後台算一次並存 `macro-scores:v1`（輸入沒變不重算）；新端點 `GET /api/macro-scores`。網頁上方分數卡改顯示這份（**拿掉網頁自己那份計分程式**），個股的大盤持股建議與每日分數紀錄（`macro-score-daily:v1`）也用同一份；分數卡下方寫「後台計算 時間」。計分規則一字未改（Claude 已逐行比對網頁與後台兩份：只差後台多回傳 raw）。
  - 個股結果（評級、Gate、進場出場、估值、持股建議）存 `master-model-result:v1:<代號>:<身分雜湊或 public>`；輸入（個股快照含面板來源、總經分數、新鮮度、證據、台北日期＋小時）與程式版本（建置時產生的 `SITE_BUILD_ID`）都沒變就回存好的那份（回應多 `computedAt`、`reusedSavedResult`），網頁重開、巡檢讀到同一份；有變才重算，且最多每小時重算一次以免沿用跨過時效線的結果。
  - 排程巡檢沒有登入身分：改用擁有者上次同步追蹤清單時的身分讀他的證據（`site-owner:v1`，只存在後台、任何 API 都不回傳；只限內部巡檢呼叫，外部未登入請求不能借用）。
  - 網頁不再自己算「暫時評級」或另選估值（拿掉網頁內嵌的評級引擎與估值分歧規則）；後台還沒算完時顯示「後台正在計算」。
- **2. 美元零軸圖（擁有者 17:21「看不出來哪裏是0軸」）**：圖改畫「零軸值」本身（每筆觀測由後台用同一公式算：(指數 − 前 20 筆最高) ÷ (最高 − 最低) × 100，不含當筆）：白色粗線＝0 軸（前 20 日最高），下方細線＝−100（前 20 日最低）；0 軸以上淡紅區「站上前20日最高（美元轉強）」、−100 以下淡綠區「跌破前20日最低（走弱）」；藍線已採用、灰虛線還沒到「觀測日＋8日」；標出「目前 −40.62」；左邊刻度直接寫「0 軸」。原本的零軸長條拿掉（圖已表達）；數字表多「零軸」欄。最後一筆已採用觀測的零軸值與大數字相同（測試核對）。
- 不改任何評分規則、門檻、Gate、風險預算。
- 測試：新增 `tests/v241-compute-once.test.mjs` 5 項；`tests/v240-dollar-macro.test.mjs` 改成核對每筆零軸值、0 軸／−100 線與標字、表格欄位；`dashboard-interactions`、`fallback-rating`、`master-remediation` 已同步。Claude 在乾淨 v241 重放無衝突：完整 `TZ=UTC npm test` exit 0，另外 10 組獨立測試腳本全過；`dist/index.html` SHA-256 `4211da6b7c69508fa2660f79aa4f49ecf44030102c1d1c8d2fbd3c4309ba226b`；`dist/server/index.js` 第一行應為 `const SITE_BUILD_ID = "a08dcbb68a738079";`。另用真實 98 筆 DTWEXAFEGS 在手機 430px／桌面 1280px 截圖檢查（零軸 −40.62）。
- 步驟：⑦-2 完成後 → `git apply` → `node build.mjs` → `TZ=UTC npm test` → 部署一次 → 擁有者打開網站一次（記下巡檢用身分）。
- 讀回（寫在 `hotfix5.md` 後段，10 行內）：
  ① 版本、SHA、`SITE_BUILD_ID`；② 美元卡：圖上看得到「0 軸」白線與 −100 線、目前值標示，手機也看；`/api/dollar-index` 最後一筆已採用觀測的 `axis` 等於 axis.value；
  ③ `/api/macro-scores` 的 computedAt、TW／US 分數，與網頁分數卡數字、「後台計算」時間一致；隔 1 分鐘再讀 `reused=true`；
  ④ 開 8299 兩次（間隔 1 分鐘）：第二次 `reusedSavedResult=true`、`computedAt` 相同；`macroScoresComputedAt` 等於 ③；大盤持股建議與部署前相同；
  ⑤ 五檔評級、進場、出場、風險預算與部署前相同（因新資料不同就寫出哪個輸入變了）；
  ⑥ 今晚 22:30 巡檢後：Gate 審計各檔 `entry`／評級與擁有者畫面同一份（`computedAt` 相同或註明重算原因）。

## 已完成（v240，10-27 15:42；hotfix4.md）：⑥ G＋F2（**已授權**：擁有者 10-27 04:56「好」＝美元；另 3 項是 v239 讀回缺口的修正，不改任何規則、門檻、評級、Gate、風險預算）
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
