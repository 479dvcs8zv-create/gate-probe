"""
pipeline.py
===========
這是「還標的物就能自行抓資料跑完」的主體。

流程：
  1. 給定 ticker
  2. 依序呼叫 adapter 的每個 fetch_xxx（抓不到的會丟 DataSourceNotConnected，
     pipeline 攔截後繼續跑，不中斷）
  3. 組成 TickerInputBundle
  4. 丟進 gates.run_all_gates 取得每個 Gate 的結果
  5. 輸出成人類可讀報告 + 結構化 JSON（供你的 v227 讀回）

重點：pipeline 本身完全不知道資料是怎麼抓的，只認 adapters.base.BaseAdapter
這個介面。你要把 GPT 處理網站接進來，只要讓它的輸出符合
adapters/json_file_adapter.py 預期的 JSON 格式（已有示範），
或自己寫一個新的 adapter class 繼承 BaseAdapter。
"""

import json
import os
from datetime import datetime, timezone
from typing import Optional

from adapters.base import BaseAdapter, DataSourceNotConnected
from schema import TickerInputBundle
from gates import run_all_gates, GateResult

# 報告輸出契約版本。Python 與 Worker 一致性比對時，先比對這個欄位，
# 版本不同的報告不直接逐欄比較。
REPORT_CONTRACT_VERSION = "gate-report/v4.8"


def build_bundle(ticker: str, adapter: BaseAdapter, peg_target_year: Optional[int] = None) -> TickerInputBundle:
    bundle = TickerInputBundle(ticker=ticker)
    peg_year = peg_target_year or (datetime.now().year + 1)

    def safe(label, fn, default):
        try:
            return fn()
        except DataSourceNotConnected as e:
            print(f"  [未接線] {label}: {e}")
            return default
        except Exception as e:
            print(f"  [錯誤] {label}: {e}")
            return default

    bundle.moat_items = safe("Gate4 護城河", lambda: adapter.fetch_moat_comparisons(ticker), [])
    bundle.psr_history = safe("PSR", lambda: adapter.fetch_psr_history(ticker), None)
    bundle.peg_consensus = safe("PEG", lambda: adapter.fetch_peg_consensus(ticker, peg_year), None)
    bundle.capacity_risk = safe("產能風險", lambda: adapter.fetch_capacity_risk(ticker), None)
    bundle.cb_records = safe("CB", lambda: adapter.fetch_cb_records(ticker), [])
    bundle.holder_concentration = safe("大戶籌碼", lambda: adapter.fetch_holder_concentration(ticker), None)
    bundle.guidance_records = safe("Gate5A", lambda: adapter.fetch_guidance_records(ticker), [])
    bundle.pre_earnings_snapshots = safe("Gate5B", lambda: adapter.fetch_pre_earnings_snapshots(ticker), [])
    bundle.peer_qualifications = safe("Gate8同業", lambda: adapter.fetch_peer_qualifications(ticker), [])
    bundle.peer_consensus_2yr = safe("Gate8共識", lambda: adapter.fetch_peer_consensus_2yr(ticker), [])

    return bundle


def run_pipeline(ticker: str, adapter: BaseAdapter, output_dir: str = "outputs",
                 gate5b_verifier=None, gate5b_announcement_verifier=None) -> dict:
    print(f"=== 開始跑 {ticker} ===")
    bundle = build_bundle(ticker, adapter)
    results = run_all_gates(bundle, gate5b_verifier=gate5b_verifier,
                            gate5b_announcement_verifier=gate5b_announcement_verifier)

    overall_status = "pass" if all(r.status == "pass" for r in results) else "partial"

    report = {
        "contract_version": REPORT_CONTRACT_VERSION,
        "ticker": ticker,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall_status,
        "gates": [
            {
                "gate": r.gate_name,
                "status": r.status,
                "reject_codes": r.reject_codes,
                "reasons": r.reasons,
                "raw_count": r.raw_count,
                "evidence_count": r.evidence_count,
                "evidence_trail": r.evidence_trail,
            }
            for r in results
        ],
    }

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{ticker}_gate_report.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"\n整體狀態：{overall_status}")
    for r in results:
        print("  " + r.summary())
    print(f"\n報告已存至：{out_path}")

    return report


if __name__ == "__main__":
    import argparse
    from adapters.json_file_adapter import JSONFileAdapter

    parser = argparse.ArgumentParser(description="標的巡檢自動管線")
    parser.add_argument("--ticker", required=True, help="例如 8299.TW")
    parser.add_argument("--raw-dir", default="outputs/raw", help="GPT處理網站輸出的 JSON 存放目錄")
    parser.add_argument("--output-dir", default="outputs", help="報告輸出目錄")
    args = parser.parse_args()

    adapter = JSONFileAdapter(raw_dir=args.raw_dir)
    run_pipeline(args.ticker, adapter, output_dir=args.output_dir)
