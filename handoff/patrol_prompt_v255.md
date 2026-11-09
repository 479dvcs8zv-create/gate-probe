台股 Master Model 每日巡檢（精簡版，v255 部署後使用）
授權：擁有者 2026-10-26 21:25 授權每日 06:30／22:30 自動巡檢，只做 POST `/api/automation/refresh-all` 與 GET status／history；擁有者 2026-11-09 21:12 同意改成精簡版，節省額度。

1. POST `/api/automation/refresh-all?compact=1` 一次。回 202 就記下 runId；如果回應寫 `alreadyRunning: true`，就接續那個 runId，不另建 run。
2. 每 10 秒 GET `/api/automation/status?compact=1`，直到回應有 `completedAt`。最多查 90 次。
   - 每次只看 `runId`、`status`、`checkpoint`、`completedAt`，不要分析其他內容。
   - 回 403、409、503 時，等 10 秒再查；同一種錯誤連續 3 次就停止，照實記錄。
3. 完成後 GET `/api/automation/history` 一次，確認第一筆的 runId、completedAt 和第 2 步相同。
4. 不要做：
   - 逐檔讀回、比對 Gate 格子、檢查分享設定、讀其他頁面；
   - 寫證據 JSON；
   - 修改任何程式、設定或排程。
5. 紀錄：只提交一次，寫到 `wcr0936531039-png/macro-relay-service` 的 `diagnostics/latest.md`。在最上面加 3 行，舊內容保留在下面：
   - `# 最新：MM/DD HH:MM 早巡檢｜晚巡檢 完成｜未完成｜Gate <summary.gateAuditCount>/<summary.gateAuditTotal>`
   - `runId <runId>｜completedAt <completedAt>｜查詢 <次數> 次｜relayImport <summary.relayImport.status>（<各組 id=狀態>）`
   - `異常：<problems 逐項列出；沒有就寫「無」>`
   未完成（超過次數或連續錯誤）時，第 3 行照實寫停在哪一步（checkpoint）和錯誤原文的前 100 字。
