# Claude 接續用（gate-probe 工作狀態）

最後更新：2026-10-19 22:20 台北（v4.39）。新的對話開始時先讀這份，再讀 `DECISIONS_PENDING.md`。

## 已完成並存檔（v4.37，`gate_pipeline_v4.37.zip`）

| 項目 | 檔案 | 測試 |
|---|---|---|
| 參考讀取器比照 v228：每季一致性＋來源檔 SHA-256／逐欄比對 | `gate_pipeline/docs/gate5b_reader.py`、`.js` | `test_v437_reader.py`（Python 與 Node 同一組情境） |
| TradingView 台灣版逐季 EPS／營收預估解析（季度由「下一份收益報告日期」推定；2454 上一季 15.28＝官方 2026Q2） | `ops/consensus_parsers.py` `parse_tradingview` | `test_v437_tradingview.py` |
| 法說會簡報官方財測 vs 實際（3034、3711、5347、5274） | `ops/slide_guidance.py`、`workflows/gate-pipeline-slide-guidance.yml` | `test_v437_slide_guidance.py`（3034、3711 固定文字） |
| 年報探測（doc.twse.com.tw t57sb01 年報類；**尚未實際執行**） | `ops/annual_report_probe.py`、`workflows/gate-pipeline-annual-report-probe.yml` | `test_v437_annual_report.py` |

全部 30 個測試檔在新資料夾解壓後通過；v4.37 重算真實 results 的界線，2330、2454 仍各 15 季 MATCH。

## 官方財測（簡報）目前結果（本機以 v4.37 跑 gate-probe 已下載的官方簡報）

- 3034 聯詠：2023Q1–2026Q2 共 14 季 VERIFIED（2025Q2 三項都低於財測；其餘多為在區間內或高於）；2026Q3 等實際。
- 3711 日月光投控：投控合併財測 2025Q3 起才有，2025Q3–2026Q2 共 4 季 VERIFIED；2023Q1–2025Q2 只有事業別財測（SEGMENT_ONLY_GUIDANCE，不比較）。
- 5347 世界先進（v4.38）：2023Q1–2026Q2 共 14 季 VERIFIED，每季「報告實際數字的簡報重列的財測」都和原財測相同；2023 年版面（營收億元＋兩率）與「季持平」都已支援。
- 5274 信驊（v4.39；全是受邀法說簡報、版面多種）：2024Q4、2025Q1、2026Q1、2026Q2 VERIFIED；2025Q2 公司季中「更新營運展望」→ GUIDANCE_UPDATED；2024Q3 兩份簡報數字不同 → GUIDANCE_CONFLICT；2024Q1、Q2、2025Q4 簡報裡沒有損益表 → 缺實際；只剩 2023-03 簡報寫法不認得。

## 進行中（接手時先檢查）

1. （已完成）法說會簡報補抓民國 112–114 年：gate-pipeline-conference-probe 依序 3034（39255734752 完成）、3711（39257183724 完成）、
   5347（39259749526 完成，v4.38 已納入）、5274（之後一個 run）。完成後：
   - `python gate_pipeline/ops/slide_guidance.py --co-id 5347 --conference results/5347/conference --out …`，5274 同；
     有 `format_unknown` 就看原文頁面補寫法（不猜）。
   - 用 `tools/make_slide_fixtures.py <代號>`（在 repo 根目錄、已解壓 gate_pipeline 時執行；逐頁 pdftotext＋一覽表原始回應 → `gate_pipeline/contract/mops_real/slides/<代號>/`）加 5347、5274 測試。
   - （已完成）gate-pipeline-slide-guidance run 39266608774（v4.39，pdftotext 24.02），結果與本機一致。
2. 年報探測：已完成（run 39262137932，step=9 送法正確）；三項頁碼已寫在 `handoff/8299_annual_report_FY2025.md`。舊的待辦說明如下僅供參考：，看 step=9 送法是否正確；下載到年報後查
   生產據點、10% 以上客戶、市占率的頁碼（給正式網站 Gate 4）。

## 本次蒐證結論（已寫進 DECISIONS_PENDING B1）

2303、3034、3711（上市）與 5274（上櫃）都沒有用重大訊息公告月營收 → 各 15 季只有季末規則（研究用）；
目前 11 檔只有 2330、2454 有 Gate 5B 界線。

## 交接管道

- Claude → GPT：`handoff/CLAUDE_TO_GPT_LATEST.md`（覆寫）。
- GPT → Claude：`https://raw.githubusercontent.com/wcr0936531039-png/macro-relay-service/main/diagnostics/latest.md`
  （公開；clone 到 `/home/claude/wcr0936531039-png/macro-relay-service` 後 `git fetch`）。
- Gemini：題目 `handoff/GEMINI_TASK_LATEST.md`（Gemini 打不開網址，需使用者貼上）；回答由使用者附檔或匯出到 Google 文件。
- 不讀、不改 `479dvcs8zv-create/AI_GATEWAY_KEY`。

## Gemini

第 9 輪題目已出（`handoff/GEMINI_TASK_LATEST.md`，五題），等使用者附回答。
