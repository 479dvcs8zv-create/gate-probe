"""
contract_fixtures.py (v4.5)
============================
Python ↔ Worker 跨語言一致性用的 Gate5B 契約案例。

  python3 contract_fixtures.py build   產生 contract/gate5b_cases_v4.5.json
  python3 contract_fixtures.py check   只讀 JSON 重建輸入與驗證器回應，重跑 Python 判定並逐案比對

JSON 自足：每個案例包含 adapter 輸入、兩個獨立驗證器（官方公告、封存證據包）的回應
（原始位元組以 base64 保存）與預期輸出。另一種語言的實作（例如 Worker 端的 Gate 引擎）
只要讀同一份 JSON、把驗證器回應當作模擬回應，輸出 normalize_result() 定義的欄位，
就能逐欄比對。

比對欄位（文字訊息 reasons 不比對，只比代碼）：
  status、reject_codes（排序後的多重集合）、raw_count、evidence_count、
  每筆快照的 final_tier / failure_codes / 官方截止點 cutoff_at、
  兩種驗證器的查詢次數（證明公告每季只查一次、非官方來源不發出查詢）

注意：預期輸出是由 Python v4.5 參考實作產生的。它定義了契約，
但不能證明任何其他實作（包括正式網站的 Gate 引擎）已經符合。
"""

import base64
import json
import os
import sys

from schema import DataPoint, PreEarningsConsensusSnapshot, Provenance, TickerInputBundle
from independent_verifier import IndependentVerifier, VerifiedEvidenceBundle
from announcement_verification import (AnnouncementEvidence, AnnouncementQueryRecord, AnnouncementQueryResult,
                                       AnnouncementVerifier)
from gates import eval_gate5b_pre_earnings
from pipeline import REPORT_CONTRACT_VERSION

HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURE_PATH = os.path.join(HERE, "contract", f"gate5b_cases_{REPORT_CONTRACT_VERSION.split('/')[-1]}.json")


# ------------------------------------------------------------ JSON <-> 物件

def _b64(b: bytes) -> str:
    return base64.b64encode(bytes(b)).decode("ascii")


def _dp_value(dp):
    return getattr(dp, "value", None) if dp is not None else None


def snapshot_to_json(s) -> dict:
    prov = s.snapshot_date.provenance if s.snapshot_date is not None else None
    return {
        "ticker": s.ticker,
        "fiscal_quarter": s.fiscal_quarter,
        "consensus_eps": _dp_value(s.consensus_eps),
        "source_url": prov.source_url if prov else None,
        "claimed_evidence_tier": prov.claimed_evidence_tier if prov else None,
        "adapter_snapshot_time": _dp_value(s.snapshot_date),
        "adapter_earnings_announcement_time": _dp_value(s.earnings_announcement_date),
        "adapter_declared_pre_earnings": bool(s.snapshot_taken_before_earnings),
        "claimed_archive_timestamp": _dp_value(s.claimed_archive_timestamp),
        "claimed_content_hash": s.claimed_content_hash,
    }


def snapshot_from_json(d: dict) -> PreEarningsConsensusSnapshot:
    def dp(value, url=None, tier=None):
        return DataPoint(value=value, provenance=Provenance(
            source_name="contract-fixture", source_url=url, fetched_at="", as_of_date=None,
            claimed_evidence_tier=tier))
    return PreEarningsConsensusSnapshot(
        ticker=d["ticker"], fiscal_quarter=d["fiscal_quarter"],
        snapshot_date=(dp(d["adapter_snapshot_time"], d["source_url"], d["claimed_evidence_tier"])
                       if d["source_url"] is not None else None),
        earnings_announcement_date=(dp(d["adapter_earnings_announcement_time"])
                                    if d["adapter_earnings_announcement_time"] is not None else None),
        consensus_eps=dp(d["consensus_eps"]),
        consensus_revenue=dp(None),
        snapshot_taken_before_earnings=d["adapter_declared_pre_earnings"],
        claimed_archive_timestamp=(dp(d["claimed_archive_timestamp"])
                                   if d["claimed_archive_timestamp"] is not None else None),
        claimed_content_hash=d["claimed_content_hash"],
    )


def _response_to_json(v, encode_item):
    if v is None:
        return None
    if isinstance(v, Exception):
        return {"error": f"{type(v).__name__}: {v}"}
    if isinstance(v, list):
        return [encode_item(x) for x in v]
    return encode_item(v)


def _bundle_to_json(b: VerifiedEvidenceBundle) -> dict:
    return {"source_url": b.source_url, "archive_url": b.archive_url, "snapshot_id": b.snapshot_id,
            "captured_at": b.captured_at, "content_b64": _b64(b.content_bytes), "sha256": b.sha256,
            "hash_algorithm": b.hash_algorithm, "content_type": getattr(b, "content_type", "")}


def _announcement_to_json(a: AnnouncementEvidence) -> dict:
    return {"source_url": a.source_url, "document_id": a.document_id, "content_b64": _b64(a.content_bytes),
            "sha256": a.sha256, "hash_algorithm": a.hash_algorithm, "content_type": getattr(a, "content_type", "")}


def _query_to_json(q: AnnouncementQueryRecord) -> dict:
    return {"event_type": q.event_type, "request_url": q.request_url, "page": q.page,
            "response_b64": _b64(q.response_bytes), "response_sha256": q.response_sha256,
            "hash_algorithm": q.hash_algorithm, "content_type": getattr(q, "content_type", "")}


def _announcement_response_to_json(v):
    """官方公告回應：{queries:[每頁原始回應], documents:[原文], declared...}；
    舊式只有文件清單的回應保留為 list（會被判涵蓋不足）。"""
    if isinstance(v, AnnouncementQueryResult):
        return {"queries": [_query_to_json(q) for q in v.queries],
                "documents": [_announcement_to_json(d) for d in v.documents],
                "declared_coverage_start": v.coverage_start, "declared_coverage_end": v.coverage_end,
                "declared_searched_event_types": list(v.searched_event_types or []),
                "sources": list(v.sources or [])}
    return _response_to_json(v, _announcement_to_json)


def _announcement_from_json(a: dict) -> AnnouncementEvidence:
    return AnnouncementEvidence(source_url=a["source_url"], document_id=a["document_id"],
                                content_bytes=base64.b64decode(a["content_b64"]), sha256=a["sha256"],
                                hash_algorithm=a["hash_algorithm"], content_type=a.get("content_type", ""))


class FixtureVerifier(IndependentVerifier, AnnouncementVerifier):
    """只依據 JSON 回應運作的驗證器；{"error": ...} 會被當成驗證器拋出例外。"""

    def __init__(self, bundles: dict, announcements: dict):
        self.bundles, self.announcements = bundles, announcements
        self.bundle_calls, self.announcement_calls = 0, 0

    @staticmethod
    def _raise_if_error(v):
        if isinstance(v, dict) and "error" in v and len(v) == 1:
            raise RuntimeError(v["error"])

    def fetch_verified_bundle(self, source_url, captured_before=None):
        self.bundle_calls += 1
        v = self.bundles.get(source_url)
        self._raise_if_error(v)
        if v is None:
            return None
        return VerifiedEvidenceBundle(
            source_url=v["source_url"], archive_url=v["archive_url"], snapshot_id=v["snapshot_id"],
            captured_at=v["captured_at"], content_bytes=base64.b64decode(v["content_b64"]),
            sha256=v["sha256"], hash_algorithm=v["hash_algorithm"], content_type=v.get("content_type", ""))

    def fetch_announcement_evidence(self, ticker, fiscal_quarter):
        self.announcement_calls += 1
        v = self.announcements.get(f"{ticker}|{fiscal_quarter}")
        self._raise_if_error(v)
        if v is None:
            return None
        if isinstance(v, list):  # 舊式回應：只有文件、沒有涵蓋範圍
            return [_announcement_from_json(a) for a in v]
        return AnnouncementQueryResult(
            documents=[_announcement_from_json(a) for a in v["documents"]],
            queries=[AnnouncementQueryRecord(
                event_type=q["event_type"], request_url=q["request_url"], page=q["page"],
                response_bytes=base64.b64decode(q["response_b64"]), response_sha256=q["response_sha256"],
                hash_algorithm=q["hash_algorithm"], content_type=q.get("content_type", ""))
                for q in v.get("queries", [])],
            coverage_start=v.get("declared_coverage_start"), coverage_end=v.get("declared_coverage_end"),
            searched_event_types=v.get("declared_searched_event_types"), sources=v.get("sources"))


# ------------------------------------------------------------ 執行與正規化

def normalize_result(r, verifier: FixtureVerifier) -> dict:
    """跨語言比對的正規化輸出。另一種語言的實作必須產生同樣結構。"""
    return {
        "status": r.status,
        "reject_codes": sorted(r.reject_codes),
        "raw_count": r.raw_count,
        "evidence_count": r.evidence_count,
        "trail": [{
            "fiscal_quarter": t["fiscal_quarter"],
            "final_tier": t["final_tier"],
            "failure_codes": sorted(t.get("failure_codes", [])),
            "cutoff_at": (t.get("announcement") or {}).get("cutoff_at"),
            "captured_before": t.get("captured_before"),
        } for t in r.evidence_trail],
        "queries": {"announcement": verifier.announcement_calls, "bundle": verifier.bundle_calls},
    }


def run_case(case_input: dict) -> dict:
    verifier = FixtureVerifier(case_input["bundles"], case_input["announcements"])
    bundle = TickerInputBundle(ticker=case_input["snapshots"][0]["ticker"])
    bundle.pre_earnings_snapshots = [snapshot_from_json(s) for s in case_input["snapshots"]]
    r = eval_gate5b_pre_earnings(bundle, verifier=verifier, announcement_verifier=verifier)
    return normalize_result(r, verifier)


# ------------------------------------------------------------ 產生案例

def _build_cases():
    # 只有 build 需要測試輔助函式；check 只讀 JSON
    import test_adversarial as T

    def case(case_id, description, snaps, verifier):
        inp = {
            "snapshots": [snapshot_to_json(s) for s in snaps],
            "bundles": {u: _response_to_json(b, _bundle_to_json) for u, b in verifier.bundles.items()},
            "announcements": {f"{t}|{q}": _announcement_response_to_json(a)
                              for (t, q), a in verifier.announcements.items()},
        }
        return {"id": case_id, "description": description, "input": inp, "expected": run_case(inp)}

    cases = []
    v, s = T._one()
    cases.append(case("pass_single_verified", "官方公告與封存證據都成立，adapter 欄位一致", [s], v))

    v, s = T._one(snap="2026-01-12T08:00:00+08:00", earn="2026-01-25T13:30:00+08:00",
                  official_announced_at="2026-01-10T14:30:00+08:00")
    cases.append(case("core_attack_adapter_postdates_announcement",
                      "adapter 把公告時間填晚；官方 1/10 已公布、1/12 才封存 → 擋下", [s], v))

    v, s = T._one()
    s.snapshot_date.value, s.earnings_announcement_date = None, None
    cases.append(case("adapter_times_missing_still_verified", "adapter 沒填任何時間，仍由官方證據判定通過", [s], v))

    v, s = T._one()
    s.snapshot_taken_before_earnings = False
    cases.append(case("adapter_flag_wrong_audit_only", "adapter「財報前」旗標填錯，只稽核", [s], v))

    v, s = T._one(announcements=None)
    cases.append(case("announcement_unavailable_fail_closed", "官方公告查不到 → 不取封存證據包", [s], v))

    v, s = T._one(announcements=RuntimeError("mops timeout"))
    cases.append(case("announcement_verifier_error", "官方公告驗證器出錯 → fail-closed", [s], v))

    docs = [T.make_announcement("T43", "2026Q1", "2026-01-20T13:00:00+08:00"),
            T.make_announcement("T43", "2026Q1", "2026-01-08T16:00:00+08:00",
                                event_type="self_reported_results", sha256="b" * 64)]
    v, s = T._one(announcements=docs)
    cases.append(case("announcement_one_bad_document", "兩份公告其中一份雜湊錯誤 → 整季不放行", [s], v))

    docs = [T.make_announcement("T43", "2026Q1", "2026-01-20T13:00:00+08:00", event_type="financial_report"),
            T.make_announcement("T43", "2026Q1", "2026-01-08T16:00:00+08:00", event_type="self_reported_results")]
    v, s = T._one(snap="2026-01-10T08:00:00+08:00", announcements=docs)
    cases.append(case("earliest_disclosure_cutoff", "自結 1/8、財報 1/20，1/10 封存 → 以 1/8 為截止點擋下", [s], v))

    v, s = T._one(tamper_observed_hash="a" * 64)
    cases.append(case("bundle_hash_mismatch", "封存證據包回報的 SHA-256 與內容不符", [s], v))

    v, s = T._one(records=[{"ticker": "9999.TW", "fiscal_quarter": "2026Q1", "consensus_eps": 10.0}])
    cases.append(case("content_issuer_mismatch", "封存內容的 EPS 屬於別家公司", [s], v))

    v, s = T._one(snap="2026-01-19T23:00:00+00:00", announcements=[T.make_announcement("T43", "2026Q1", "2026-01-20")])
    cases.append(case("date_only_announcement_ambiguous", "官方只有日期，封存落在當日可能區間內", [s], v))

    v = T.FakeIndependentVerifier()
    snaps = [T.make_verified_snapshot(v, "T17", "2026Q1", "2026-01-05T08:00:00+08:00", "2026-01-20T13:00:00+08:00", 8.0),
             T.make_verified_snapshot(v, "T17", "2026Q1", "2026-01-06T08:00:00+08:00", "2026-01-20T13:00:00+08:00", 9.5)]
    cases.append(case("same_quarter_conflicting_eps", "同季兩筆都驗證成立但 EPS 不同 → 整季排除；公告只查一次", snaps, v))

    v, s = T._one()
    s.snapshot_date.provenance.source_url = T.PLAIN_URL
    cases.append(case("non_official_source_no_queries", "非官方來源 → 不發出任何查詢", [s], v))

    # ---- v4.6 官方公告完整性 ----
    doc = [T.make_announcement("T43", "2026Q1", T.BASE_EARN)]
    v, s = T._one(announcements=doc)
    v.announcements[("T43", "2026Q1")] = doc  # 舊式：只回文件清單
    cases.append(case("announcement_coverage_undeclared", "驗證器沒有宣告查詢範圍 → 不放行", [s], v))

    v, s = T._one(announcements=T.full_coverage(doc, coverage_start="2026-02-15"))
    cases.append(case("announcement_coverage_starts_late", "查詢起點晚於期間第一天 → 可能漏抓，不放行", [s], v))

    v, s = T._one(announcements=T.full_coverage(doc, searched_event_types=["financial_report"]))
    cases.append(case("announcement_event_types_missing", "沒有搜尋自結損益等事件類型 → 不放行", [s], v))

    corr = [T.make_announcement("T43", "2026Q1", "2026-01-22T10:00:00+08:00", event_type="financial_report",
                                doc_id="MOPS-T43-CORR", records=[{
                                    "ticker": "T43", "fiscal_quarter": "2026Q1", "event_type": "financial_report",
                                    "announced_at": "2026-01-22T10:00:00+08:00", "is_correction": True,
                                    "corrects_document_id": "MOPS-T43-ORIG"}])]
    v, s = T._one(announcements=corr)
    cases.append(case("correction_without_original", "只有更正公告、缺原始公告 → 不放行", [s], v))

    # ---- v4.7 可稽核的查詢證據 ----
    early = T.make_announcement("T43", "2026Q1", "2026-01-08T16:00:00+08:00", event_type="self_reported_results")
    late = T.make_announcement("T43", "2026Q1", "2026-01-20T13:00:00+08:00", event_type="financial_report")
    v, s = T._one(snap="2026-01-10T08:00:00+08:00", announcements=[late])
    v.announcements[("T43", "2026Q1")] = T.full_coverage([late], ticker="T43", extra_listing={
        "self_reported_results": [{"document_id": early.document_id, "fiscal_quarter": "2026Q1",
                                   "announced_at": "2026-01-08T16:00:00+08:00"}]})
    cases.append(case("listed_earlier_document_withheld",
                      "官方清單列出 1/8 自結公告，驗證器卻沒提供原文（只給 1/20 財報）→ 不放行", [s], v))

    v, s = T._one(announcements=T.full_coverage(doc, pages_per_type=2, drop_pages={("financial_report", 2)}))
    cases.append(case("announcement_page_missing", "財報申報清單共 2 頁只取得第 1 頁 → 不放行", [s], v))

    v, s = T._one(announcements=T.full_coverage(doc, truncated_types={"self_reported_results"}))
    cases.append(case("announcement_listing_truncated", "官方回應標示結果被截斷 → 不放行", [s], v))

    v, s = T._one(announcements=T.full_coverage(doc, tamper_query_hash=True))
    cases.append(case("announcement_query_hash_mismatch", "查詢回應的雜湊與原始位元組不符 → 不放行", [s], v))

    # ---- v4.8 依宣告字元集解碼 ----
    v, s = T._one(announcements=[T._big5_announcement("application/json; charset=big5")])
    cases.append(case("announcement_big5_declared", "公告原文是 Big5 且有宣告 → 依宣告解碼、通過", [s], v))
    v, s = T._one(announcements=[T._big5_announcement("")])
    cases.append(case("announcement_big5_undeclared", "同一份 Big5 原文但未宣告字元集 → 不悄悄改編碼、不放行", [s], v))
    return cases


def build(path=FIXTURE_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    doc = {
        "contract_version": REPORT_CONTRACT_VERSION,
        "generated_by": "gate_pipeline Python reference implementation",
        "note": "預期輸出由 Python 參考實作產生，定義契約；不代表其他實作已符合。",
        "compare_fields": ["status", "reject_codes(sorted multiset)", "raw_count", "evidence_count",
                           "trail[].final_tier", "trail[].failure_codes(sorted)", "trail[].cutoff_at",
                           "queries.announcement", "queries.bundle"],
        "cases": _build_cases(),
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(doc, f, ensure_ascii=False, indent=2, sort_keys=True)
    return doc


def check(path=FIXTURE_PATH) -> list:
    """只讀 JSON 重跑每個案例，回傳不一致的案例清單（空清單代表全部一致）。"""
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    if doc["contract_version"] != REPORT_CONTRACT_VERSION:
        return [f"contract_version 不符：檔案 {doc['contract_version']}，程式 {REPORT_CONTRACT_VERSION}"]
    mismatches = []
    for c in doc["cases"]:
        actual = run_case(c["input"])
        if actual != c["expected"]:
            mismatches.append(f"{c['id']}: expected={c['expected']} actual={actual}")
    return mismatches


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "check"
    if cmd == "build":
        d = build()
        print(f"已產生 {len(d['cases'])} 個案例 → {FIXTURE_PATH}")
    else:
        bad = check()
        print("全部一致" if not bad else "\n".join(bad))
        sys.exit(1 if bad else 0)
