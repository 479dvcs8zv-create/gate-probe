"""
test_adversarial.py (v4.8)
===========================
執行：python3 test_adversarial.py（也可用 pytest 收集）
      Wayback 驗證器與連線探測工具的故障注入測試在 test_fault_injection.py

v4.8 新增（test_v48_*）：公告原文、官方查詢清單頁、共識封存內容一律依宣告字元集嚴格解碼；
未宣告時用 UTF-8（容許 BOM）；不支援的編碼或解碼失敗即不放行，不悄悄改用其他編碼。

v4.7 新增（test_v47_*）：官方公告完整性改由實際查詢證據證明——每頁官方回應的原始位元組與雜湊、
分頁齊全、合計筆數、截斷標示、官方網域、清單與原文互相核對、清單時間與原文時間一致。
另以測試如實記錄一項已知限制：清單與原文「一致地」漏掉同一份公告時，本程式無法識破。

v4.6 新增（test_v46_*）：官方公告驗證器必須宣告查詢範圍（起點不晚於期間第一天、
四類揭露事件都有搜尋、最早事件落在範圍內），否則不放行；更正公告必須連同原始公告回傳，
截止點以原始公告為準；傳給封存驗證器的截止點來自官方時間；驗證器例外代碼白名單。

v4.5 新增（test_v45_*）：adapter 時間欄位完全退出判定路徑——不填、填錯、旗標錯、
型別錯都由官方證據判定，只留稽核，且不再產生已停用的前置拒絕代碼；
跨語言契約案例（contract/gate5b_cases_v4.5.json）只讀 JSON 可重現判定，竄改會被抓到。
測試 6/9/13/16 已改為 v4.5 語意（原本斷言的是已停用的前置拒絕代碼）。

v4.4 新增「財報公告時間獨立查證」驗收（test_v44_*）：adapter 把公告時間填晚的核心攻擊
（附採信 adapter 時會通過的對照組）、官方公告各種缺陷、多事件取最早、任一份無效即整季不放行、
只有日期的公告採保守區間、每季只查一次、公告未成立不取封存證據包。

v4.3 新增「原子性證據包」驗收（test_v43_*）：P0-1 注入、P0-2 內容對應、
P0-3 封存時間、P0-4 完整性、P1-1 時間解析、fail-closed、每筆只查詢一次、
驗證軌跡、報告輸出契約。每個情境只製造單一缺陷，確認被對應的 EVIDENCE_* 代碼擋下，
並附對照組確認合理資料不被誤殺。

以下為早期版本的說明（保留）：
原8項反例 + v3 新增：
  9.  Gate5B：同一天但無時分精度 → 應為 UNVERIFIABLE（reject code:
      TIME_PRECISION_INSUFFICIENT），不是直接判過也不是判宣告矛盾。
  10. Gate5B：日期順序正確、宣告也正確，但來源只是普通連結
      （evidence_tier=unverified_link）→ 應為 insufficient
      （reject code: SOURCE_UNVERIFIABLE）。
  11. Gate5B 正向：時分精度足夠 + official_record/immutable_archive
      來源層級 + 8個不同季度 → 應為 pass（VERIFIED_PRE_EARNINGS）。
  12. PEG：EPS 含負值與零值的混合分布 → MAD 方法應能正常運作，
      不因符號或量級而出錯或誤判。

執行：python3 test_adversarial.py
"""

from schema import (
    TickerInputBundle, DataPoint, Provenance, PSRHistory, PEGConsensus,
    AnalystEstimate, GuidanceRecord, PreEarningsConsensusSnapshot,
    PeerQualification, PeerConsensusRecord
)
import dataclasses
import hashlib
import json
from datetime import timezone as _tz

from gates import run_all_gates, eval_gate8_peers, eval_gate5b_pre_earnings
from reject_codes import RC
from independent_verifier import IndependentVerifier, VerifiedEvidenceBundle
from announcement_verification import (AnnouncementVerifier, AnnouncementEvidence, AnnouncementQueryResult,
                                       AnnouncementQueryRecord, REQUIRED_SEARCHED_EVENT_TYPES,
                                       verify_earnings_announcement)
from time_utils import parse_with_precision


class FakeIndependentVerifier(IndependentVerifier, AnnouncementVerifier):
    """測試專用：同時模擬兩個獨立驗證器。
      - 封存證據包：bundles[source_url] → VerifiedEvidenceBundle / None / Exception
      - 官方公告：announcements[(ticker, quarter)] → list[AnnouncementEvidence] / [] / None / Exception
    calls / ann_calls 記錄查詢次數，用來證明每筆快照、每個季度都只查一次。"""

    def __init__(self):
        self.bundles, self.calls, self.captured_before = {}, {}, {}
        self.announcements, self.ann_calls = {}, {}

    def fetch_verified_bundle(self, source_url, captured_before=None):
        self.calls[source_url] = self.calls.get(source_url, 0) + 1
        self.captured_before[source_url] = captured_before
        v = self.bundles.get(source_url)
        if isinstance(v, Exception):
            raise v
        return v

    def fetch_announcement_evidence(self, ticker, fiscal_quarter):
        key = (ticker, fiscal_quarter)
        self.ann_calls[key] = self.ann_calls.get(key, 0) + 1
        v = self.announcements.get(key)
        if isinstance(v, Exception):
            raise v
        return v


def make_announcement(ticker, fiscal_quarter, announced_at, *, event_type="financial_report",
                      doc_id=None, records=None, content_bytes=None, source_url=None,
                      sha256=None, hash_algorithm="sha256", content_type=""):
    """組一份官方公告文件。預設是誠實情境：官方網域、結構化內容、雜湊由位元組實算。"""
    if records is None:
        records = [{"ticker": ticker, "fiscal_quarter": fiscal_quarter,
                    "event_type": event_type, "announced_at": announced_at}]
    if content_bytes is None:
        content_bytes = json.dumps({"records": records}, ensure_ascii=False).encode("utf-8")
    doc_id = doc_id or f"MOPS-{ticker}-{fiscal_quarter}-{event_type}"
    # 記下「官方清單上會怎麼列這份公告」，供 full_coverage 產生查詢回應
    _ANN_META[doc_id] = {"ticker": ticker, "fiscal_quarter": fiscal_quarter,
                         "announced_at": announced_at, "event_type": event_type}
    return AnnouncementEvidence(
        source_url=source_url or f"https://mops.twse.com.tw/announcement/{doc_id}",
        document_id=doc_id, content_bytes=content_bytes,
        sha256=sha256 if sha256 is not None else hashlib.sha256(content_bytes).hexdigest(),
        hash_algorithm=hash_algorithm, content_type=content_type)

NOW = "2026-10-17T10:00:00+08:00"


def dp(value, source="測試來源", url=None, as_of="2026-10-15", fetched_at=NOW, tier=None, excerpt=None):
    """tier 參數對應 claimed_evidence_tier（宣告值，僅供稽核比對，
    不會被 Gate5B 直接採信）。verified_evidence_tier 一律留空，
    交由 evidence_verification.py 每次強制重新算出。"""
    return DataPoint(value=value, provenance=Provenance(
        source_name=source, source_url=url, fetched_at=fetched_at, as_of_date=as_of,
        claimed_evidence_tier=tier, raw_excerpt=excerpt))


_UNSET = object()


_ANN_META = {}


def full_coverage(docs, *, ticker=None, range_start="1990-01-01", range_end="2099-12-31", event_types=None,
                  pages_per_type=1, drop_pages=(), truncated_types=(), drop_listing_ids=(), extra_listing=None,
                  tamper_query_hash=False, query_domain="mops.twse.com.tw", count_delta=0, listing_overrides=None,
                  query_encoding="utf-8", query_content_type="", **legacy):
    """模擬一個「附上實際查詢證據」的官方公告驗證器回應：
    每類事件一次查詢（可分多頁），每頁是一份官方回應（JSON 清單，含範圍、頁碼、總數、列出的公告），
    清單內容由 make_announcement 記下的中繼資料產生，與回傳的公告原文一致。
    其餘參數用來注入故障：缺頁、截斷、漏列、雜湊竄改、非官方網域、範圍不足、缺事件類型。
    legacy：相容 v4.6 的 coverage_start / coverage_end / searched_event_types 參數名稱。"""
    range_start = legacy.pop("coverage_start", range_start)
    range_end = legacy.pop("coverage_end", range_end)
    event_types = legacy.pop("searched_event_types", event_types)
    assert not legacy, f"未知參數 {legacy}"

    metas = [(d.document_id, _ANN_META[d.document_id]) for d in docs
             if isinstance(d, AnnouncementEvidence) and d.document_id in _ANN_META]
    ticker = ticker or (metas[0][1]["ticker"] if metas else "T43")
    types = list(event_types) if event_types is not None else sorted(REQUIRED_SEARCHED_EVENT_TYPES)
    queries = []
    for t in types:
        items = [{"document_id": doc_id, "fiscal_quarter": m["fiscal_quarter"], "announced_at": m["announced_at"]}
                 for doc_id, m in metas
                 if (m["event_type"] if m["event_type"] in REQUIRED_SEARCHED_EVENT_TYPES else "financial_report") == t
                 and doc_id not in drop_listing_ids]
        items += list((extra_listing or {}).get(t, []))
        items = [{**it, **(listing_overrides or {}).get(it["document_id"], {})} for it in items]
        total_pages = max(1, pages_per_type)
        chunks = [items[i::total_pages] for i in range(total_pages)]
        for p, chunk in enumerate(chunks, start=1):
            if (t, p) in drop_pages:
                continue
            listing = {"event_type": t, "ticker": ticker, "range_start": range_start, "range_end": range_end,
                       "page": p, "total_pages": total_pages, "total_count": len(items) + count_delta, "items": chunk,
                       "source_note": "公開資訊觀測站查詢結果（測試）"}  # 含中文，編碼測試才有意義
            if t in truncated_types:
                listing["truncated"] = True
            body = json.dumps(listing, ensure_ascii=False).encode(query_encoding)
            queries.append(AnnouncementQueryRecord(
                event_type=t, request_url=f"https://{query_domain}/query?type={t}&co_id={ticker}&page={p}",
                page=p, response_bytes=body, content_type=query_content_type,
                response_sha256="0" * 64 if tamper_query_hash else hashlib.sha256(body).hexdigest()))
    return AnnouncementQueryResult(documents=docs, queries=queries, coverage_start=range_start,
                                   coverage_end=range_end, searched_event_types=types,
                                   sources=["https://mops.twse.com.tw/(test-fixture)"])


def make_verified_snapshot(verifier: FakeIndependentVerifier, ticker, fiscal_quarter,
                            snapshot_dt_str, earnings_dt_str, eps_value, *,
                            records=None, content_bytes=None, captured_at=None,
                            bundle_overrides=None, registered=_UNSET,
                            tamper_observed_content=False, tamper_observed_hash=None,
                            claimed_hash=_UNSET, official_announced_at=None, announcements=_UNSET):
    """組一筆快照，並在 verifier 註冊「獨立來源一次回傳」的證據包。

    預設是誠實情境：Wayback 封存、快照 ID 與封存時間一致、內容是結構化 JSON
    （含一筆干擾用的別家公司紀錄）、SHA-256 由內容位元組實算。
    各參數用來製造單一缺陷，驗證每種缺陷都會被擋下：
      records / content_bytes   換掉證據內容
      captured_at               換掉封存時間（快照 ID 會跟著同步，除非另外覆寫）
      bundle_overrides          直接覆寫證據包任一欄位（例如假雜湊、錯的快照 ID）
      registered                覆寫驗證器實際回傳值（None 或 Exception）
      claimed_hash              adapter 聲稱的雜湊（只影響稽核，不影響判定）
      official_announced_at     官方公告時間（預設等於 adapter 聲稱的 earnings_dt_str）
      announcements             直接覆寫官方公告驗證器的回傳值（list / [] / None / Exception）
    """
    snap_dt, _ = parse_with_precision(snapshot_dt_str)
    cap_str = captured_at or snap_dt.astimezone(_tz.utc).isoformat()
    cap_dt, _ = parse_with_precision(cap_str)
    sid = cap_dt.astimezone(_tz.utc).strftime("%Y%m%d%H%M%S") if cap_dt and cap_dt.tzinfo else "00000000000000"

    url = f"https://mops.twse.com.tw/consensus/{ticker}/{fiscal_quarter}/{sid}"
    if records is None:
        eps_in_doc = eps_value + 1 if tamper_observed_content else eps_value
        records = [
            {"ticker": ticker, "fiscal_quarter": fiscal_quarter, "consensus_eps": eps_in_doc},
            {"ticker": "9999.TW", "fiscal_quarter": fiscal_quarter, "consensus_eps": 99.9},
        ]
    if content_bytes is None:
        content_bytes = json.dumps({"records": records}, ensure_ascii=False).encode("utf-8")
    real_sha = hashlib.sha256(content_bytes).hexdigest()

    bundle = VerifiedEvidenceBundle(
        source_url=url,
        archive_url=f"https://web.archive.org/web/{sid}/{url}",
        snapshot_id=sid,
        captured_at=cap_str,
        content_bytes=content_bytes,
        sha256=tamper_observed_hash if tamper_observed_hash is not None else real_sha,
    )
    if bundle_overrides:
        bundle = dataclasses.replace(bundle, **bundle_overrides)
    verifier.bundles[url] = bundle if registered is _UNSET else registered
    if announcements is _UNSET:
        announcements = [make_announcement(ticker, fiscal_quarter, official_announced_at or earnings_dt_str)]
    if isinstance(announcements, list):
        announcements = full_coverage(announcements, ticker=ticker)
    verifier.announcements[(ticker, fiscal_quarter)] = announcements

    return PreEarningsConsensusSnapshot(
        ticker=ticker, fiscal_quarter=fiscal_quarter,
        snapshot_date=dp(snapshot_dt_str, url=url, tier="official_record"),
        earnings_announcement_date=dp(earnings_dt_str),
        snapshot_taken_before_earnings=True,
        consensus_eps=dp(eps_value), consensus_revenue=dp(1000),
        claimed_archive_timestamp=dp(cap_str),
        claimed_content_hash=real_sha if claimed_hash is _UNSET else claimed_hash,
    )


def run_gate5b(snaps, verifier=None):
    bundle = TickerInputBundle(ticker=snaps[0].ticker if snaps else "T")
    bundle.pre_earnings_snapshots = snaps
    return eval_gate5b_pre_earnings(bundle, verifier=verifier, announcement_verifier=verifier)


OFFICIAL_URL = "https://mops.twse.com.tw/announcement"   # 會被獨立驗證為 official_record
ARCHIVE_URL = "https://web.archive.org/web/20260310/x"    # 會被獨立驗證為 immutable_archive
PLAIN_URL = "https://blog.example.com/post"               # 會被獨立驗證為 unverified_link


def _assert_insufficient(results, gate_name, msg=""):
    r = next(x for x in results if x.gate_name == gate_name)
    assert r.status != "pass", f"FAIL {msg}: 應擋下但結果為 {r.status} — {r.reasons}"
    return r


# ---- 原有反例 1-6 (schema 相容調整) ----

def test_case_1_psr_null_duplicate():
    series = [dp(None, as_of="2026-01-01") for _ in range(20)]
    bundle = TickerInputBundle(ticker="T1")
    bundle.psr_history = PSRHistory(ticker="T1", basis_definition="測試口徑", quarterly_series=series)
    r = _assert_insufficient(run_all_gates(bundle), "PSR", "反例1")
    print(f"✓ 反例1 PSR: {r.summary()}")


def test_case_2_peg_no_eps_fake_coverage():
    bundle = TickerInputBundle(ticker="T2")
    bundle.peg_consensus = PEGConsensus(ticker="T2", target_year=2027, eps_estimates=[], coverage_count=3)
    r = _assert_insufficient(run_all_gates(bundle), "PEG", "反例2")
    print(f"✓ 反例2 PEG: {r.summary()}")


def test_case_2b_peg_outlier_and_wrong_year():
    bundle = TickerInputBundle(ticker="T2B")
    bundle.peg_consensus = PEGConsensus(
        ticker="T2B", target_year=2027,
        eps_estimates=[
            AnalystEstimate("INST_A", "券商A", 2027, dp(12.5)),
            AnalystEstimate("INST_A", "券商A重複", 2027, dp(12.6)),
            AnalystEstimate("INST_B", "券商B", 2026, dp(13.0)),
            AnalystEstimate("INST_C", "券商C", 2027, dp(9999.0)),
            AnalystEstimate("INST_D", "券商D", 2027, dp(12.9)),
        ],
        coverage_count=5,
    )
    r = _assert_insufficient(run_all_gates(bundle), "PEG", "反例2B")
    print(f"✓ 反例2B PEG多重防護: {r.summary()}")


def test_case_3_single_guidance_basis_match():
    bundle = TickerInputBundle(ticker="T3")
    bundle.guidance_records = [
        GuidanceRecord(ticker="T3", fiscal_year=2026, guidance_text=dp("營收+15%"),
                        guidance_release_date=dp("2026-01-10"), actual_result=dp("+16%"), basis_matches=True)
    ]
    r = _assert_insufficient(run_all_gates(bundle), "Gate5A_年度指引", "反例3")
    print(f"✓ 反例3 Gate5A: {r.summary()}")


def test_case_4_same_quarter_repeated():
    bundle = TickerInputBundle(ticker="T4")
    bundle.pre_earnings_snapshots = [
        PreEarningsConsensusSnapshot(
            ticker="T4", fiscal_quarter="2026Q1",
            snapshot_date=dp("2026-01-05T08:00:00+08:00", url=OFFICIAL_URL, tier="official_record"),
            earnings_announcement_date=dp("2026-01-20T13:30:00+08:00"),
            snapshot_taken_before_earnings=True,
            consensus_eps=dp(None), consensus_revenue=dp(None),
        ) for _ in range(8)
    ]
    r = _assert_insufficient(run_all_gates(bundle), "Gate5B_財報前共識", "反例4")
    print(f"✓ 反例4 Gate5B(重複季度): {r.summary()}")


def test_case_6_gate5b_false_declaration():
    """v4.5 語意：adapter 的宣告與時間只稽核，判定由獨立證據決定，兩個方向都要成立。"""
    # A. adapter 宣告「財報前」，自報時間卻是財報後；獨立證據顯示確實在財報前 → 通過，留稽核
    v, s = _one()
    s.snapshot_date.value = "2026-03-25T09:00:00+08:00"
    s.earnings_announcement_date = dp("2026-03-10T13:00:00+08:00")
    r = run_gate5b([s], v)
    assert r.evidence_count == 1, f"FAIL: 獨立證據成立卻被 adapter 宣告擋下 {r.reject_codes}"
    assert RC.CLAIMED_TIMING_INCONSISTENT in r.reject_codes
    print(f"✓ 反例6A adapter 宣告與自報時間矛盾、證據在財報前 → 通過並稽核 {_codes(r)}")

    # B. adapter 自報時間與宣告完全自洽地說「財報前」，獨立證據卻顯示財報後 → 擋下
    v, s = _one(snap="2026-01-25T08:00:00+08:00")
    s.snapshot_date.value = "2026-01-05T08:00:00+08:00"
    s.earnings_announcement_date = dp("2026-03-10T13:00:00+08:00")
    _expect_blocked("反例6B adapter 自洽地宣稱財報前、證據顯示財報後", v, s, RC.EVIDENCE_ARCHIVED_AFTER_EARNINGS)


def test_case_5_peer_consensus_wrong_company():
    bundle = TickerInputBundle(ticker="T5")
    bundle.peer_qualifications = [
        PeerQualification(peer_name="同業甲", ticker="1234.TW", company_id="C001",
                           revenue_scale_match=True, product_overlap_score=0.8,
                           listing_region="TW", qualifies=True, reason="測試")
        for _ in range(3)
    ]
    bundle.peer_consensus_2yr = [
        PeerConsensusRecord(peer_name="完全不相關的公司", ticker="9999.TW", company_id="C999",
                             year=2026, consensus_value=dp(100)),
        PeerConsensusRecord(peer_name="完全不相關的公司", ticker="9999.TW", company_id="C999",
                             year=2027, consensus_value=dp(110)),
    ]
    r = _assert_insufficient(run_all_gates(bundle), "Gate8_同業", "反例5")
    print(f"✓ 反例5 Gate8(ticker核對): {r.summary()}")


def test_case_5b_gate8_same_ticker_diff_company_id():
    bundle = TickerInputBundle(ticker="T5B")
    bundle.peer_qualifications = [
        PeerQualification(peer_name="同業A", ticker="2330.TW", company_id="REAL_ID",
                           revenue_scale_match=True, product_overlap_score=0.9,
                           listing_region="TW", qualifies=True, reason="測試"),
    ]
    bundle.peer_consensus_2yr = [
        PeerConsensusRecord(peer_name="同業A", ticker="2330.TW", company_id="FAKE_ID",
                             year=2026, consensus_value=dp(50)),
        PeerConsensusRecord(peer_name="同業A", ticker="2330.TW", company_id="FAKE_ID",
                             year=2027, consensus_value=dp(55)),
    ]
    r = eval_gate8_peers(bundle, required_years=[2026, 2027])
    assert r.status != "pass"
    assert RC.COMPANY_ID_MISMATCH in r.reject_codes
    print(f"✓ 反例5B Gate8(company_id矛盾偵測): {r.summary()}")


# ---- 本輪新增：Gate5B 三態驗證 ----

def test_case_9_same_day_no_time_precision():
    """v4.5 語意：同日、只有日期的時間無法判斷先後，這個時間邏輯仍然成立，
    但現在只套用在獨立證據上；adapter 自報的同日日期不再擋下資料。"""
    from time_utils import classify_timing as ct
    d, p = parse_with_precision("2026-03-10")
    assert ct(d, p, d, p) == "SAME_DAY_AMBIGUOUS"

    v, s = _one()
    s.snapshot_date.value = "2026-03-10"
    s.earnings_announcement_date = dp("2026-03-10")
    r = run_gate5b([s], v)
    assert r.evidence_count == 1, f"FAIL: adapter 的同日日期擋下了證據成立的資料 {r.reject_codes}"
    print("✓ 反例9 同日僅日期仍判為無法確定先後；adapter 自報同日日期不影響判定")


def test_case_10_unverified_link_source():
    """反例10：日期順序與宣告都正確，但來源只是普通連結（unverified_link）
    → 不能單憑連結認定歷史資料未被竄改，應為 insufficient。"""
    bundle = TickerInputBundle(ticker="T10")
    bundle.pre_earnings_snapshots = [
        PreEarningsConsensusSnapshot(
            ticker="T10", fiscal_quarter=f"2026Q{i % 4 + 1}",
            snapshot_date=dp("2026-03-10T08:00:00+08:00", url="https://blog.example.com/post",
                              tier="unverified_link"),
            earnings_announcement_date=dp("2026-03-10T13:30:00+08:00"),
            snapshot_taken_before_earnings=True,
            consensus_eps=dp(10.0 + i), consensus_revenue=dp(1000 + i),
        ) for i in range(8)
    ]
    r = _assert_insufficient(run_all_gates(bundle), "Gate5B_財報前共識", "反例10")
    assert RC.SOURCE_UNVERIFIABLE in r.reject_codes
    print(f"✓ 反例10 Gate5B(來源層級不足): {r.summary()}")


def test_case_11_gate5b_positive_verified():
    """正向測試11：有接上真正能回報正確資訊的IndependentVerifier、時分精度
    足夠、8個不同季度 → 應為 pass，證明四層驗證在『真的有獨立查證能力』
    且證據齊全時沒有矯枉過正。"""
    verifier = FakeIndependentVerifier()
    bundle = TickerInputBundle(ticker="T11")
    bundle.pre_earnings_snapshots = [
        make_verified_snapshot(
            verifier, "T11", f"202{5 + i // 4}Q{i % 4 + 1}",
            f"2025-0{(i % 9) + 1}-10T08:00:00+08:00",
            f"2025-0{(i % 9) + 1}-10T13:30:00+08:00",  # 同日但下午公告
            10.0 + i,
        ) for i in range(8)
    ]
    results = run_all_gates(bundle, gate5b_verifier=verifier, gate5b_announcement_verifier=verifier)
    r = next(x for x in results if x.gate_name == "Gate5B_財報前共識")
    assert r.status == "pass", f"FAIL: 正向案例應通過但結果為 {r.status} — {r.reasons}"
    print(f"✓ 正向11 Gate5B(四層驗證+真正獨立來源確認): {r.summary()}")


def test_case_11b_gate5b_no_verifier_always_fails_closed():
    """正向測試的關鍵對照組：即使 adapter 把 claimed_* 全部填得完美一致
    （看起來證據齊全），只要沒有傳入真正的IndependentVerifier（預設走
    NullIndependentVerifier），Gate5B必須依然判定未通過——證明『有欄位』
    不等於『有驗證』，系統預設是fail-closed。"""
    verifier = FakeIndependentVerifier()  # 建立但故意不傳給run_all_gates
    snap = make_verified_snapshot(verifier, "T11B", "2026Q1", "2026-01-05T08:00:00+08:00",
                                   "2026-01-20T13:00:00+08:00", 10.0)
    bundle = TickerInputBundle(ticker="T11B")
    bundle.pre_earnings_snapshots = [snap]
    results = run_all_gates(bundle)  # 注意：沒有傳 gate5b_verifier
    r = next(x for x in results if x.gate_name == "Gate5B_財報前共識")
    assert r.status != "pass", "FAIL: 沒有獨立驗證器時竟然通過了，fail-closed機制失效"
    assert RC.SOURCE_UNVERIFIABLE in r.reject_codes
    print(f"✓ 正向11B Gate5B(無獨立驗證器預設fail-closed): {r.summary()}")


def test_case_11c_gate5b_missing_one_layer_still_blocks():
    """對照組（v4.3 語意）：證據包其他欄位都正確，只有雜湊是空的
    → 證據包不完整，整筆 fail-closed，不會因為其他欄位正確就放行。"""
    verifier = FakeIndependentVerifier()
    snap = make_verified_snapshot(verifier, "T11C", "2026Q1", "2026-01-05T08:00:00+08:00",
                                   "2026-01-20T13:00:00+08:00", 10.0,
                                   tamper_observed_hash="")
    r = run_gate5b([snap], verifier)
    assert r.status != "pass"
    assert RC.EVIDENCE_BUNDLE_INCOMPLETE in r.reject_codes, r.reject_codes
    assert RC.SOURCE_UNVERIFIABLE in r.reject_codes
    print(f"✓ 對照11C Gate5B(證據包缺雜湊即 fail-closed): {r.summary()}")


def test_case_19_forged_claims_disagree_with_independent_source():
    """新增19（本輪最關鍵的測試）：adapter聲稱的claimed_*欄位全部完美
    自洽（內容摘要、時間戳、雜湊都對得上彼此），但『真正的獨立來源』
    （FakeIndependentVerifier模擬的，等同於真的重新抓取/查證）
    回報的內容其實不包含EPS數值（Layer2應判不通過）——證明系統是拿
    observed去判斷，而不是被精心偽造的claimed自洽性騙過。"""
    verifier = FakeIndependentVerifier()
    snap = make_verified_snapshot(verifier, "T19", "2026Q1", "2026-01-05T08:00:00+08:00",
                                   "2026-01-20T13:00:00+08:00", 10.0,
                                   tamper_observed_content=True)  # 獨立來源說內容對不上
    bundle = TickerInputBundle(ticker="T19")
    bundle.pre_earnings_snapshots = [snap]
    results = run_all_gates(bundle, gate5b_verifier=verifier, gate5b_announcement_verifier=verifier)
    r = next(x for x in results if x.gate_name == "Gate5B_財報前共識")
    assert r.status != "pass", "FAIL: adapter偽造的自洽claimed欄位竟然騙過了驗證"
    assert RC.SOURCE_UNVERIFIABLE in r.reject_codes
    print(f"✓ 反例19 Gate5B(偽造自洽claimed被獨立來源戳破): {r.summary()}")


def test_case_19b_claimed_hash_mismatch_audited():
    """新增19B（v4.3 語意）：證據包本身完全正確，但 adapter 聲稱的雜湊不同
    → 記錄 CLAIMED_HASH_MISMATCH 稽核，但判定只依據證據包，該季仍計為有效。
    證明 claimed 欄位既不能讓錯的資料通過，也不會讓對的資料被誤殺。"""
    verifier = FakeIndependentVerifier()
    snap = make_verified_snapshot(verifier, "T19B", "2026Q1", "2026-01-05T08:00:00+08:00",
                                   "2026-01-20T13:00:00+08:00", 10.0,
                                   claimed_hash="sha256:" + "0" * 64)
    r = run_gate5b([snap], verifier)
    assert RC.CLAIMED_HASH_MISMATCH in r.reject_codes, f"FAIL: 應記錄雜湊不一致稽核，實際 reject_codes={r.reject_codes}"
    assert r.evidence_count == 1, f"FAIL: 稽核訊號不應影響判定，實際 evidence_count={r.evidence_count}"
    print(f"✓ 反例19B Gate5B(聲稱雜湊不一致只稽核、不影響判定): {r.summary()}")


def test_case_12_peg_negative_zero_eps_mad():
    """反例/正向混合12：EPS含負值、零值與正常值混合分布，MAD方法應能正確
    識別真正的離群值，不因符號/量級而誤判或出錯。"""
    bundle = TickerInputBundle(ticker="T12")
    bundle.peg_consensus = PEGConsensus(
        ticker="T12", target_year=2027,
        eps_estimates=[
            AnalystEstimate("INST_A", "券商A", 2027, dp(-0.5)),   # 負值但合理
            AnalystEstimate("INST_B", "券商B", 2027, dp(-0.6)),
            AnalystEstimate("INST_C", "券商C", 2027, dp(0.0)),     # 零值但合理
            AnalystEstimate("INST_D", "券商D", 2027, dp(-0.4)),
            AnalystEstimate("INST_E", "券商E", 2027, dp(500.0)),   # 真正離群
        ],
        coverage_count=5,
    )
    results = run_all_gates(bundle)
    r = next(x for x in results if x.gate_name == "PEG")
    assert RC.OUTLIER_REMOVED in r.reject_codes, f"FAIL: 應偵測到離群值但reject_codes={r.reject_codes}"
    # 4家合理負值/零值應該保留（>=3家門檻），離群的500應被剔除
    assert r.evidence_count == 4, f"FAIL: 應有4家合理估值通過，實際 evidence_count={r.evidence_count}"
    print(f"✓ 測試12 PEG(負值/零值MAD穩健性): {r.summary()}")


def test_case_13_same_instant_different_timezones():
    """新增13：快照與公告實際上是「幾乎同一時刻」，但分別用不同時區表示
    （快照UTC、公告台北時間），且公告其實在快照之後30分鐘
    （對應你提供的例子：快照10/12 23:30 UTC，公告10/13 07:00台北=10/12 23:00 UTC，
    公告其實比快照早30分鐘，也就是快照是財報「後」才抓的）。
    這裡刻意用 naive（無時區）字串表示快照時間，模擬「忘記標時區」的真實情境，
    驗證程式不會因為裸日曆日期不同（10/12 vs 10/13）就誤判。
    """
    from time_utils import classify_timing as ct
    naive_dt, naive_p = parse_with_precision("2026-10-12T23:30:00")
    earn_dt, earn_p = parse_with_precision("2026-10-13T07:00:00+08:00")
    assert ct(naive_dt, naive_p, earn_dt, earn_p) == "SAME_DAY_AMBIGUOUS", "無時區時間不得被判出先後"

    # v4.5：同一個例子套用在獨立證據上——封存 10/12 23:30 UTC，官方公告 10/13 07:00 台北（=10/12 23:00 UTC）
    v, s = _one(snap="2026-10-12T23:30:00+00:00", earn="2026-10-13T07:00:00+08:00")
    _expect_blocked("反例13 跨時區：封存其實晚於官方公告30分鐘", v, s, RC.EVIDENCE_ARCHIVED_AFTER_EARNINGS)


def test_case_14_official_tier_forged():
    """新增14：來源「宣告」自己是 official_record，但 URL 其實是普通部落格，
    獨立驗證後應判定為 unverified_link，且記錄 CLAIMED_TIER_OVERSTATED 稽核代碼。"""
    bundle = TickerInputBundle(ticker="T14")
    bundle.pre_earnings_snapshots = [PreEarningsConsensusSnapshot(
        ticker="T14", fiscal_quarter="2026Q1",
        snapshot_date=dp("2026-01-05T08:00:00+08:00", url=PLAIN_URL, tier="official_record"),  # 偽造宣告
        earnings_announcement_date=dp("2026-01-20T13:00:00+08:00"),
        snapshot_taken_before_earnings=True,
        consensus_eps=dp(10.0), consensus_revenue=dp(1000),
    )]
    results = run_all_gates(bundle)
    r = next(x for x in results if x.gate_name == "Gate5B_財報前共識")
    assert r.status != "pass"
    assert RC.CLAIMED_TIER_OVERSTATED in r.reject_codes, f"FAIL: 應偵測到宣告造假，實際 reject_codes={r.reject_codes}"
    assert RC.SOURCE_UNVERIFIABLE in r.reject_codes
    print(f"✓ 反例14 Gate5B(官方等級遭偽造宣告): {r.summary()}")


def test_case_15_mad_zero_with_extreme():
    """新增15：三筆EPS中兩筆一致(10,10)、一筆極端(500) → MAD=0的情況，
    500應被列為OUTLIER_UNDETERMINED、不計入有效，而非直接放行。"""
    bundle = TickerInputBundle(ticker="T15")
    bundle.peg_consensus = PEGConsensus(
        ticker="T15", target_year=2027,
        eps_estimates=[
            AnalystEstimate("INST_A", "券商A", 2027, dp(10.0)),
            AnalystEstimate("INST_B", "券商B", 2027, dp(10.0)),
            AnalystEstimate("INST_C", "券商C", 2027, dp(500.0)),
        ],
        coverage_count=3,
    )
    results = run_all_gates(bundle)
    r = next(x for x in results if x.gate_name == "PEG")
    assert RC.OUTLIER_UNDETERMINED in r.reject_codes, f"FAIL: 應標記待確認離群值，實際 reject_codes={r.reject_codes}"
    assert r.evidence_count == 2, f"FAIL: 應僅2家一致值算有效，實際 evidence_count={r.evidence_count}"
    assert r.status != "pass"  # 2家 < 門檻3家
    print(f"✓ 反例15 PEG(MAD=0含極端值): {r.summary()}")


def test_case_16_invalid_timestamp():
    """v4.5 語意：adapter 自報的時間不合法 → 只稽核；沒有獨立證據仍不放行，有獨立證據則由證據決定。"""
    def _bad(v, s):
        s.snapshot_date.value = "不是一個日期"
        s.earnings_announcement_date = dp("2026-13-99")
        return s

    v, s = _one()
    bundle = TickerInputBundle(ticker=s.ticker)
    bundle.pre_earnings_snapshots = [_bad(v, s)]
    r = eval_gate5b_pre_earnings(bundle)  # 沒有任何獨立驗證器
    assert r.evidence_count == 0 and RC.ANNOUNCEMENT_EVIDENCE_UNAVAILABLE in r.reject_codes

    v, s = _one()
    r = run_gate5b([_bad(v, s)], v)
    assert r.evidence_count == 1, f"FAIL: adapter 的錯誤時間擋下了證據成立的資料 {r.reject_codes}"
    assert RC.CLAIMED_TIMING_INCONSISTENT in r.reject_codes
    assert RC.CLAIMED_ANNOUNCEMENT_TIME_MISMATCH in r.reject_codes
    print(f"✓ 反例16 adapter 時間不合法：無證據不放行；有證據則通過並稽核 {_codes(r)}")


def test_case_17_duplicate_quarter_different_consensus():
    """新增17（本輪強化）：同一財報季度出現兩筆『都通過四層驗證（含真正
    獨立來源確認）』但數值不同的共識EPS（真衝突，不是單純重複貼上同一筆）
    → 不能再靠品質分數悄悄選一筆蓋過去，必須整季排除、標記
    CONFLICTING_VALUES_SAME_KEY，交由人工覆核。"""
    verifier = FakeIndependentVerifier()
    bundle = TickerInputBundle(ticker="T17")
    bundle.pre_earnings_snapshots = [
        make_verified_snapshot(verifier, "T17", "2026Q1", "2026-01-05T08:00:00+08:00",
                                "2026-01-20T13:00:00+08:00", 8.0),   # 兩筆都證據齊全
        make_verified_snapshot(verifier, "T17", "2026Q1", "2026-01-06T08:00:00+08:00",
                                "2026-01-20T13:00:00+08:00", 9.5),   # 但EPS數值不同
    ]
    results = run_all_gates(bundle, gate5b_verifier=verifier, gate5b_announcement_verifier=verifier)
    r = next(x for x in results if x.gate_name == "Gate5B_財報前共識")
    assert r.status != "pass"
    assert RC.CONFLICTING_VALUES_SAME_KEY in r.reject_codes, f"FAIL: 應偵測到數值衝突，實際 reject_codes={r.reject_codes}"
    assert r.evidence_count == 0, f"FAIL: 衝突季度應整季排除，實際 evidence_count={r.evidence_count}"
    print(f"✓ 反例17 Gate5B(同季真衝突須整季排除): {r.summary()}")


def test_case_17b_duplicate_quarter_same_value_is_fine():
    """對照組：同季重複但數值完全一致（真正的重複貼上，不是衝突）
    → 應正常去重保留一筆，不應被誤判為衝突。"""
    verifier = FakeIndependentVerifier()
    bundle = TickerInputBundle(ticker="T17B")
    bundle.pre_earnings_snapshots = [
        make_verified_snapshot(verifier, "T17B", "2026Q1", "2026-01-05T08:00:00+08:00",
                                "2026-01-20T13:00:00+08:00", 8.0),
        make_verified_snapshot(verifier, "T17B", "2026Q1", "2026-01-06T08:00:00+08:00",
                                "2026-01-20T13:00:00+08:00", 8.0),  # 數值相同
    ]
    results = run_all_gates(bundle, gate5b_verifier=verifier, gate5b_announcement_verifier=verifier)
    r = next(x for x in results if x.gate_name == "Gate5B_財報前共識")
    assert RC.CONFLICTING_VALUES_SAME_KEY not in r.reject_codes
    assert r.evidence_count == 1
    print(f"✓ 對照17B Gate5B(同季同值不誤判為衝突): {r.summary()}")


def test_case_20_peg_same_institution_conflicting_eps():
    """新增20（P1-2對PEG的另一半）：同機構、同目標年度出現兩筆不同EPS值
    （例如資料來源衝突或重複匯入時版本不一致）→ 不能靠去重品質分數
    悄悄選一筆，必須整組排除並記錄CONFLICTING_VALUES_SAME_KEY。"""
    bundle = TickerInputBundle(ticker="T20")
    bundle.peg_consensus = PEGConsensus(
        ticker="T20", target_year=2027,
        eps_estimates=[
            AnalystEstimate("INST_X", "券商X", 2027, dp(12.0)),
            AnalystEstimate("INST_X", "券商X", 2027, dp(15.0)),   # 同機構同年度但數值衝突
            AnalystEstimate("INST_Y", "券商Y", 2027, dp(12.5)),
            AnalystEstimate("INST_Z", "券商Z", 2027, dp(12.8)),
        ],
        coverage_count=4,
    )
    results = run_all_gates(bundle)
    r = next(x for x in results if x.gate_name == "PEG")
    assert RC.CONFLICTING_VALUES_SAME_KEY in r.reject_codes, f"FAIL: 應偵測到PEG衝突，實際 reject_codes={r.reject_codes}"
    # INST_X整組排除，只剩INST_Y、INST_Z兩家，低於3家門檻
    assert r.evidence_count == 2, f"FAIL: 應僅2家非衝突機構有效，實際 evidence_count={r.evidence_count}"
    assert r.status != "pass"
    print(f"✓ 反例20 PEG(同機構同年度EPS衝突整組排除): {r.summary()}")


def test_case_18_verified_tier_injection_blocked():
    """新增18（直接對應P0-1審查意見）：adapter惡意預先把
    verified_evidence_tier 塞成 'official_record'，即使其他三層證據
    全部缺失、網域也只是普通連結，驗證函式仍必須強制重新計算並覆寫，
    不能因為欄位已經有值就直接信任。"""
    from evidence_verification import verify_pre_earnings_evidence
    snap = PreEarningsConsensusSnapshot(
        ticker="T18", fiscal_quarter="2026Q1",
        snapshot_date=dp("2026-01-05T08:00:00+08:00", url=PLAIN_URL),  # 普通連結
        earnings_announcement_date=dp("2026-01-20T13:00:00+08:00"),
        snapshot_taken_before_earnings=True,
        consensus_eps=dp(10.0), consensus_revenue=dp(1000),
    )
    # 攻擊模擬：直接竄改 provenance，偽裝成「已經驗證過是official_record」
    snap.snapshot_date.provenance.verified_evidence_tier = "official_record"

    result = verify_pre_earnings_evidence(snap)
    assert result["final_tier"] == "unverified_link", \
        f"FAIL: 預先注入的verified_evidence_tier未被覆寫，驗證結果={result}"
    assert snap.snapshot_date.provenance.verified_evidence_tier == "unverified_link", \
        "FAIL: provenance物件上的欄位本身也必須被強制覆寫"
    print(f"✓ 反例18 P0-1(verified_evidence_tier注入阻斷): final_tier={result['final_tier']}（已強制覆寫，注入無效）")


# ======================================================================
# v4.3 驗收：原子性證據包（每一項只製造單一缺陷，確認被對應代碼擋下）
# ======================================================================

BASE_SNAP = "2026-01-05T08:00:00+08:00"
BASE_EARN = "2026-01-20T13:00:00+08:00"


def _one(ticker="T43", eps=10.0, snap=BASE_SNAP, earn=BASE_EARN, **kw):
    v = FakeIndependentVerifier()
    s = make_verified_snapshot(v, ticker, "2026Q1", snap, earn, eps, **kw)
    return v, s


def _ann(v, s):
    return verify_earnings_announcement(s.ticker, s.fiscal_quarter, v)


def _rebind(v, s, **fields):
    """直接改寫驗證器將回傳的證據包欄位（模擬驗證器/封存服務回報異常）。"""
    url = s.snapshot_date.provenance.source_url
    v.bundles[url] = dataclasses.replace(v.bundles[url], **fields)
    return url


def _codes(r):
    return sorted(set(r.reject_codes) - {RC.MIN_COUNT_NOT_MET, RC.SOURCE_UNVERIFIABLE})


def _expect_blocked(name, v, s, *codes):
    r = run_gate5b([s], v)
    assert r.evidence_count == 0, f"FAIL {name}: 應擋下，實際 evidence_count={r.evidence_count} codes={r.reject_codes}"
    for c in codes:
        assert c in r.reject_codes, f"FAIL {name}: 缺少 {c}，實際 {r.reject_codes}"
    print(f"✓ {name} → {_codes(r)}")


def _expect_verified(name, v, s):
    r = run_gate5b([s], v)
    assert r.evidence_count == 1, f"FAIL {name}: 應通過驗證，實際 codes={r.reject_codes} reasons={r.reasons}"
    print(f"✓ {name} → 驗證通過")


def test_v43_p0_1_injection_with_official_url():
    """P0-1：官方網址 + 預填 verified_evidence_tier=official_record，但獨立來源查不到
    → 重新驗證後必須是 unverified_link，物件上的欄位也被覆寫。"""
    from evidence_verification import verify_pre_earnings_evidence
    v, s = _one(registered=None)
    s.snapshot_date.provenance.verified_evidence_tier = "official_record"
    res = verify_pre_earnings_evidence(s, v, announcement=_ann(v, s))
    assert res["final_tier"] == "unverified_link"
    assert s.snapshot_date.provenance.verified_evidence_tier == "unverified_link"
    assert RC.EVIDENCE_BUNDLE_UNAVAILABLE in [c for c, _ in res["failures"]]
    print("✓ v4.3 P0-1 預填 verified 等級 + 官方網址 → 已覆寫為 unverified_link")


def test_v43_p0_2_content():
    v, s = _one(records=[{"ticker": "9999.TW", "fiscal_quarter": "2026Q1", "consensus_eps": 10.0}])
    _expect_blocked("v4.3 P0-2 官方網址但 EPS 屬於別家公司", v, s, RC.EVIDENCE_ISSUER_MISMATCH)

    v, s = _one(records=[{"ticker": "T43", "fiscal_quarter": "2025Q4", "consensus_eps": 10.0}])
    _expect_blocked("v4.3 P0-2 同公司但 EPS 屬於別的季度", v, s, RC.EVIDENCE_PERIOD_MISMATCH)

    v, s = _one(records=[{"ticker": "T43", "fiscal_quarter": "2026Q1", "consensus_eps": 12.0}])
    _expect_blocked("v4.3 P0-2 同公司同季但 EPS 不同", v, s, RC.EVIDENCE_CONTENT_MISMATCH)

    v, s = _one(eps=1.5, records=[{"ticker": "T43", "fiscal_quarter": "2026Q1", "consensus_eps": 11.5}])
    _expect_blocked("v4.3 P0-2 字串陷阱：待驗1.5、文件11.5", v, s, RC.EVIDENCE_CONTENT_MISMATCH)

    v, s = _one(content_bytes="<html><body>T43 2026Q1 共識 EPS 10.0</body></html>".encode("utf-8"))
    _expect_blocked("v4.3 P0-2 非結構化頁面（舊版字串包含會通過）", v, s, RC.EVIDENCE_CONTENT_MISMATCH)

    v, s = _one(records=[{"ticker": "T43", "fiscal_quarter": "2026Q1", "consensus_eps": 10.0},
                         {"ticker": "T43", "fiscal_quarter": "2026Q1", "consensus_eps": 12.0}])
    _expect_blocked("v4.3 P0-2 同一文件同公司同季有兩個 EPS", v, s, RC.EVIDENCE_CONTENT_MISMATCH)


def test_v43_p0_2_content_positive_formats():
    """對照：結構化內容的合理變化不應被誤殺。"""
    v, s = _one(content_bytes=b"ticker,fiscal_quarter,consensus_eps\nT43,2026Q1,10.00\n9999.TW,2026Q1,99.9\n")
    _expect_verified("v4.3 對照 CSV 且 EPS 寫成 10.00", v, s)
    v, s = _one(records=[{"symbol": "t43", "fiscal_year": 2026, "quarter": "Q1", "eps": "10"}])
    _expect_verified("v4.3 對照 年度/季度分欄、代碼小寫", v, s)


def test_v43_p0_3_time():
    v, s = _one(captured_at="2026-01-21T02:00:00+00:00")
    _expect_blocked("v4.3 P0-3 宣稱財報前、證據顯示封存在財報後", v, s, RC.EVIDENCE_ARCHIVED_AFTER_EARNINGS)

    v, s = _one()
    url = s.snapshot_date.provenance.source_url
    _rebind(v, s, snapshot_id="20260101000000", archive_url=f"https://web.archive.org/web/20260101000000/{url}")
    _expect_blocked("v4.3 P0-3 快照ID時間與封存時間不一致", v, s, RC.EVIDENCE_SNAPSHOT_ID_MISMATCH)

    v, s = _one(captured_at="2026-01-05T00:00:00")
    _expect_blocked("v4.3 P0-3 封存時間未帶時區", v, s, RC.EVIDENCE_ARCHIVE_TIMESTAMP_UNVERIFIED)

    v, s = _one()
    url = s.snapshot_date.provenance.source_url
    sid = v.bundles[url].snapshot_id
    _rebind(v, s, archive_url=f"https://archive.ph/{sid}/{url}")
    _expect_blocked("v4.3 P0-3 封存服務沒有時間核對規則", v, s, RC.EVIDENCE_ARCHIVE_TIMESTAMP_UNVERIFIED)


def test_v43_p0_4_integrity():
    v, s = _one(tamper_observed_hash="a" * 64)
    _expect_blocked("v4.3 P0-4 假的 SHA-256（格式正確、值不符）", v, s,
                    RC.EVIDENCE_HASH_MISMATCH, RC.EVIDENCE_IMMUTABILITY_UNPROVEN)

    v, s = _one(tamper_observed_hash="sha256:not-a-real-hash")
    _expect_blocked("v4.3 P0-4 雜湊格式不合法", v, s, RC.EVIDENCE_HASH_ALGORITHM_UNSUPPORTED)

    v, s = _one(bundle_overrides={"hash_algorithm": "md5"})
    _expect_blocked("v4.3 P0-4 非 SHA-256 演算法", v, s, RC.EVIDENCE_HASH_ALGORITHM_UNSUPPORTED)

    v, s = _one()
    _rebind(v, s, snapshot_id="fake-memento-123")
    _expect_blocked("v4.3 P0-4 無法查證的存證ID", v, s,
                    RC.EVIDENCE_SNAPSHOT_ID_MISMATCH, RC.EVIDENCE_IMMUTABILITY_UNPROVEN)

    v, s = _one()
    url = s.snapshot_date.provenance.source_url
    sid = v.bundles[url].snapshot_id
    _rebind(v, s, archive_url=f"https://evidence.vendor-example.com/{sid}/{url}")
    _expect_blocked("v4.3 P0-4 封存在非獨立服務", v, s, RC.EVIDENCE_SOURCE_NOT_INDEPENDENT)

    v, s = _one()
    url = s.snapshot_date.provenance.source_url
    _rebind(v, s, source_url=url + "-other")
    _expect_blocked("v4.3 P0-4 證據包屬於另一個網頁", v, s, RC.EVIDENCE_SNAPSHOT_ID_MISMATCH)

    v, s = _one()
    url = s.snapshot_date.provenance.source_url
    sid = v.bundles[url].snapshot_id
    _rebind(v, s, archive_url=f"https://web.archive.org/web/{sid}/{url}-evil")
    _expect_blocked("v4.3 P0-4 封存網址指向前綴相同的另一頁", v, s, RC.EVIDENCE_SNAPSHOT_ID_MISMATCH)


def test_v43_p1_1_time_parsing():
    for bad in ("2026-01-05T25:99:00+08:00", "2026-01-05 garbage", "2026-13-01"):
        assert parse_with_precision(bad) == (None, None), f"FAIL: 「{bad}」不應被退回日期解析"
    assert parse_with_precision("2026-01-05")[1] == "date_only"
    assert parse_with_precision("2026-01-05T08:00:00+08:00")[1] == "datetime_tz"
    v, s = _one(captured_at="2026-01-05T25:99:00+00:00")
    _expect_blocked("v4.3 P1-1 證據包封存時間不合法", v, s, RC.EVIDENCE_ARCHIVE_TIMESTAMP_UNVERIFIED)


def test_v43_fail_closed():
    v, s = _one(registered=None)
    _expect_blocked("v4.3 fail-closed 查不到證據包", v, s, RC.EVIDENCE_BUNDLE_UNAVAILABLE)
    v, s = _one(registered=RuntimeError("archive timeout"))
    _expect_blocked("v4.3 fail-closed 驗證器拋例外", v, s, RC.EVIDENCE_VERIFIER_ERROR)
    v, s = _one(registered="not a bundle")
    _expect_blocked("v4.3 fail-closed 驗證器回傳錯誤型別", v, s, RC.EVIDENCE_VERIFIER_ERROR)
    v, s = _one(bundle_overrides={"content_bytes": b""})
    _expect_blocked("v4.3 fail-closed 證據包缺內容", v, s, RC.EVIDENCE_BUNDLE_INCOMPLETE)

    from evidence_verification import verify_pre_earnings_evidence
    v, s = _one()
    res = verify_pre_earnings_evidence(s, v, record_extractor=lambda text: 1 / 0, announcement=_ann(v, s))
    assert res["final_tier"] == "unverified_link"
    assert RC.EVIDENCE_VERIFIER_ERROR in [c for c, _ in res["failures"]]
    print("✓ v4.3 fail-closed 解析器出錯 → ['EVIDENCE_VERIFIER_ERROR']")


def test_v43_atomic_single_fetch_and_trail():
    """每筆快照只向驗證器查一次；通過的軌跡要能追溯快照ID、封存網址、重算雜湊。"""
    v = FakeIndependentVerifier()
    snaps = [make_verified_snapshot(v, "T43A", f"202{5 + i // 4}Q{i % 4 + 1}",
                                    f"2025-0{i + 1}-10T08:00:00+08:00", f"2025-0{i + 1}-10T13:30:00+08:00",
                                    10.0 + i) for i in range(8)]
    r = run_gate5b(snaps, v)
    assert r.status == "pass", r.reasons
    assert len(v.calls) == 8 and all(n == 1 for n in v.calls.values()), f"FAIL: 查詢次數 {v.calls}"
    assert len(r.evidence_trail) == 8
    for t in r.evidence_trail:
        b = v.bundles[t["requested_url"]]
        assert t["sha256_recomputed"] == hashlib.sha256(b.content_bytes).hexdigest()
        assert t["snapshot_id"] == b.snapshot_id and t["archive_url"] == b.archive_url
        assert t["failure_codes"] == [] and t["final_tier"] == "official_record"
    print("✓ v4.3 原子性：8筆快照各只查詢1次，軌跡含快照ID/封存網址/重算雜湊")


def test_v43_report_contract():
    """報告輸出要有 Python↔Worker 比對所需欄位。"""
    import contextlib
    import io
    import tempfile
    from adapters.base import BaseAdapter
    from pipeline import run_pipeline, REPORT_CONTRACT_VERSION
    with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
        report = run_pipeline("T43R", BaseAdapter(), output_dir=d)
    assert report["contract_version"] == REPORT_CONTRACT_VERSION
    for g in report["gates"]:
        for key in ("status", "reject_codes", "reasons", "raw_count", "evidence_count", "evidence_trail"):
            assert key in g, f"FAIL: 報告缺 {key}"
        assert len(g["reject_codes"]) == len(g["reasons"])
    print(f"✓ v4.3 報告契約 {REPORT_CONTRACT_VERSION}：含 status/reject_codes/raw_count/evidence_count/evidence_trail")


# ======================================================================
# v4.4 驗收：財報公告時間獨立查證
# ======================================================================

def test_v44_core_attack_adapter_postdates_announcement():
    """核心攻擊：官方 1/10 已公布結果，共識在 1/12 才封存（財報後），
    但 adapter 把公告時間填成 1/25。封存內容、封存時間、SHA-256 全部真實。"""
    attack = dict(snap="2026-01-12T08:00:00+08:00", earn="2026-01-25T13:30:00+08:00")

    # 對照：若官方時間剛好等於 adapter 聲稱值（等同 v4.3 採信 adapter），這筆會通過
    v, s = _one(**attack, official_announced_at=attack["earn"])
    _expect_verified("v4.4 對照 若採信 adapter 的公告時間（v4.3 行為）", v, s)

    v, s = _one(**attack, official_announced_at="2026-01-10T14:30:00+08:00")
    r = run_gate5b([s], v)
    assert v.ann_calls == {("T43", "2026Q1"): 1}
    assert r.evidence_count == 0, f"FAIL: 財報後封存的共識被放行 codes={r.reject_codes}"
    assert RC.EVIDENCE_ARCHIVED_AFTER_EARNINGS in r.reject_codes
    assert RC.CLAIMED_ANNOUNCEMENT_TIME_MISMATCH in r.reject_codes
    print(f"✓ v4.4 核心攻擊 adapter 把公告時間填晚 → {_codes(r)}")


def test_v44_no_announcement_verifier_never_fetches_archive():
    v, s = _one()
    bundle = TickerInputBundle(ticker=s.ticker)
    bundle.pre_earnings_snapshots = [s]
    r = eval_gate5b_pre_earnings(bundle, verifier=v)  # 沒有接官方公告驗證器
    assert r.evidence_count == 0 and RC.ANNOUNCEMENT_EVIDENCE_UNAVAILABLE in r.reject_codes, r.reject_codes
    assert v.calls == {}, f"FAIL: 公告未查證就去取封存證據包 {v.calls}"

    # 網域身分不過的快照，連官方公告都不查
    v2 = FakeIndependentVerifier()
    bad = PreEarningsConsensusSnapshot(
        ticker="T44X", fiscal_quarter="2026Q1",
        snapshot_date=dp(BASE_SNAP, url=PLAIN_URL), earnings_announcement_date=dp(BASE_EARN),
        snapshot_taken_before_earnings=True, consensus_eps=dp(10.0), consensus_revenue=dp(1000))
    run_gate5b([bad], v2)
    assert v2.ann_calls == {} and v2.calls == {}, f"FAIL: 非官方來源仍發出查詢 {v2.ann_calls} {v2.calls}"
    print("✓ v4.4 未接官方公告驗證器 → 不取封存證據包；非官方來源 → 兩種查詢都不發出")


def test_v44_announcement_fail_closed():
    for name, value, code in [
        ("查不到（None）", None, RC.ANNOUNCEMENT_EVIDENCE_UNAVAILABLE),
        ("查無事件（空列表）", [], RC.ANNOUNCEMENT_EVIDENCE_UNAVAILABLE),
        ("驗證器拋例外", RuntimeError("mops timeout"), RC.ANNOUNCEMENT_VERIFIER_ERROR),
        ("回傳非列表", "not a list", RC.ANNOUNCEMENT_VERIFIER_ERROR),
        ("列表中有錯誤型別", [object()], RC.ANNOUNCEMENT_VERIFIER_ERROR),
    ]:
        v, s = _one(announcements=value)
        _expect_blocked(f"v4.4 fail-closed 公告{name}", v, s, code)


def test_v44_announcement_document_defects():
    q, t = "2026Q1", "T43"
    cases = [
        ("非官方網域", dict(source_url="https://news.example.com/t43-results"), RC.ANNOUNCEMENT_SOURCE_NOT_OFFICIAL),
        ("屬於別家公司", dict(records=[{"ticker": "9999.TW", "fiscal_quarter": q, "announced_at": BASE_EARN}]),
         RC.ANNOUNCEMENT_ISSUER_MISMATCH),
        ("屬於別的季度", dict(records=[{"ticker": t, "fiscal_quarter": "2025Q4", "announced_at": BASE_EARN}]),
         RC.ANNOUNCEMENT_PERIOD_MISMATCH),
        ("假的 SHA-256", dict(sha256="a" * 64), RC.ANNOUNCEMENT_HASH_MISMATCH),
        ("非 SHA-256 演算法", dict(hash_algorithm="md5"), RC.ANNOUNCEMENT_HASH_ALGORITHM_UNSUPPORTED),
        ("公告時間不合法", dict(records=[{"ticker": t, "fiscal_quarter": q, "announced_at": "2026-01-20T25:99:00+08:00"}]),
         RC.ANNOUNCEMENT_TIME_UNVERIFIED),
        ("非結構化頁面", dict(content_bytes="<html>T43 2026Q1 公告 2026-01-20</html>".encode("utf-8")),
         RC.ANNOUNCEMENT_CONTENT_MISMATCH),
        ("缺內容", dict(content_bytes=b""), RC.ANNOUNCEMENT_EVIDENCE_INCOMPLETE),
    ]
    for name, kw, code in cases:
        ev = make_announcement(t, q, BASE_EARN, **kw)
        if kw.get("content_bytes") == b"":
            ev = dataclasses.replace(ev, content_bytes=b"")
        v, s = _one(announcements=[ev])
        _expect_blocked(f"v4.4 公告文件{name}", v, s, code)


def test_v44_earliest_disclosure_is_cutoff():
    """自結損益 1/8 先公布、正式財報 1/20 才公布：截止點必須是 1/8。"""
    docs = [make_announcement("T43", "2026Q1", "2026-01-20T13:00:00+08:00", event_type="financial_report"),
            make_announcement("T43", "2026Q1", "2026-01-08T16:00:00+08:00", event_type="self_reported_results")]
    v, s = _one(snap="2026-01-10T08:00:00+08:00", announcements=docs)
    _expect_blocked("v4.4 多事件 封存在自結之後、正式財報之前", v, s, RC.EVIDENCE_ARCHIVED_AFTER_EARNINGS)
    v, s = _one(snap="2026-01-05T08:00:00+08:00", announcements=docs)
    _expect_verified("v4.4 多事件 封存早於最早的自結公告", v, s)


def test_v44_one_bad_document_fails_whole_period():
    """兩份公告中有一份雜湊錯誤：即使封存早於另一份有效公告，也不能放行。"""
    docs = [make_announcement("T43", "2026Q1", "2026-01-20T13:00:00+08:00"),
            make_announcement("T43", "2026Q1", "2026-01-08T16:00:00+08:00",
                              event_type="self_reported_results", sha256="b" * 64)]
    v, s = _one(snap="2026-01-05T08:00:00+08:00", announcements=docs)
    _expect_blocked("v4.4 任一公告文件無效 → 整季不放行", v, s, RC.ANNOUNCEMENT_HASH_MISMATCH)


def test_v44_date_only_announcement_is_conservative():
    """官方只有日期 2026-01-20（不知時分與時區）：當天最早可能時刻是 2026-01-19T10:00Z。"""
    docs = [make_announcement("T43", "2026Q1", "2026-01-20")]
    v, s = _one(snap="2026-01-18T00:00:00+00:00", announcements=docs)
    _expect_verified("v4.4 只有日期的公告 封存明確早於該日", v, s)
    v, s = _one(snap="2026-01-19T23:00:00+00:00", announcements=docs)
    _expect_blocked("v4.4 只有日期的公告 封存落在可能區間內", v, s, RC.EVIDENCE_ARCHIVE_TIMESTAMP_UNVERIFIED)
    r = run_gate5b([s], v)
    assert RC.CLAIMED_ANNOUNCEMENT_TIME_MISMATCH not in r.reject_codes, \
        "FAIL: adapter 的 1/20 13:00 與官方的 1/20 一致，不應記錄不一致稽核"


def test_v44_one_query_per_quarter_and_trail():
    v = FakeIndependentVerifier()
    snaps = [make_verified_snapshot(v, "T44", f"202{5 + i // 4}Q{i % 4 + 1}",
                                    f"2025-0{i + 1}-10T08:00:00+08:00", f"2025-0{i + 1}-10T13:30:00+08:00",
                                    10.0 + i) for i in range(8)]
    snaps.append(make_verified_snapshot(v, "T44", "2025Q1", "2025-01-09T08:00:00+08:00",
                                        "2025-01-10T13:30:00+08:00", 10.0))  # 同季第二筆，同 EPS
    r = run_gate5b(snaps, v)
    assert r.status == "pass", r.reasons
    assert len(v.ann_calls) == 8 and all(n == 1 for n in v.ann_calls.values()), f"FAIL: 公告查詢次數 {v.ann_calls}"
    assert RC.CLAIMED_ANNOUNCEMENT_TIME_MISMATCH not in r.reject_codes, "adapter 時間與官方一致時不應有稽核"
    for t in r.evidence_trail:
        ann = t["announcement"]
        assert ann["cutoff_document_id"].startswith("MOPS-T44-") and ann["cutoff_at"], ann
        assert ann["documents"][0]["sha256_recomputed"]
    print("✓ v4.4 9筆快照（8季）公告各只查1次；軌跡含官方截止點、公告序號、重算雜湊；時間一致時無稽核")


# ======================================================================
# v4.5 驗收：adapter 時間欄位完全退出判定路徑
# ======================================================================

DEPRECATED_PRECHECK_CODES = {RC.UNPARSEABLE_DATE, RC.TIME_PRECISION_INSUFFICIENT,
                             RC.POST_EARNINGS_REJECTED, RC.DECLARATION_MISMATCH}


class _WrongType:
    """模擬 adapter 傳入完全錯誤型別的欄位（沒有 .value）。"""


def test_v45_adapter_fields_cannot_affect_decision():
    """官方證據完整成立時，adapter 的時間欄位不論缺漏、錯誤、矛盾、型別錯，都必須：
    照常查官方公告、照常通過、只留稽核，且不產生任何已停用的前置拒絕代碼。"""
    def mutate(name, fn):
        v, s = _one()
        fn(s)
        r = run_gate5b([s], v)
        assert r.evidence_count == 1, f"FAIL {name}: adapter 欄位影響了判定 {r.reject_codes}"
        assert sum(v.ann_calls.values()) == 1, f"FAIL {name}: 官方公告沒有被查詢"
        assert not (DEPRECATED_PRECHECK_CODES & set(r.reject_codes)), f"FAIL {name}: 產生已停用代碼 {r.reject_codes}"
        print(f"✓ v4.5 {name} → 官方證據判定通過，稽核 {_codes(r)}")

    mutate("adapter 沒填公告時間", lambda s: setattr(s, "earnings_announcement_date", None))
    mutate("adapter 公告時間格式錯誤", lambda s: setattr(s, "earnings_announcement_date", dp("not-a-date")))
    mutate("adapter 快照時間空白", lambda s: setattr(s.snapshot_date, "value", None))
    mutate("adapter 兩個時間都沒填",
           lambda s: (setattr(s.snapshot_date, "value", None), setattr(s, "earnings_announcement_date", None)))
    mutate("adapter「財報前」旗標填錯", lambda s: setattr(s, "snapshot_taken_before_earnings", False))
    mutate("adapter 欄位型別錯誤",
           lambda s: (setattr(s, "earnings_announcement_date", _WrongType()),
                      setattr(s, "claimed_archive_timestamp", _WrongType()),
                      setattr(s, "claimed_content_hash", 12345)))


def test_v45_no_source_pointer():
    """缺的是「要去哪裡查證」（來源網址），不是 adapter 時間：無法查證，也不發出任何查詢。"""
    v, s = _one()
    s.snapshot_date = None
    r = run_gate5b([s], v)
    assert r.evidence_count == 0 and RC.SOURCE_UNVERIFIABLE in r.reject_codes, r.reject_codes
    assert v.ann_calls == {} and v.calls == {}
    print("✓ v4.5 缺來源網址 → SOURCE_UNVERIFIABLE，且不發出任何查詢")


# ======================================================================
# v4.6 驗收：官方公告完整性、更正公告、截止點來源、驗證器例外代碼白名單
# ======================================================================

def test_v46_announcement_coverage():
    doc = [make_announcement("T43", "2026Q1", BASE_EARN)]

    v, s = _one()
    v.announcements[("T43", "2026Q1")] = doc  # 舊式回應：只有文件清單
    _expect_blocked("v4.6 驗證器沒有宣告查詢範圍", v, s, RC.ANNOUNCEMENT_COVERAGE_INCOMPLETE)

    v, s = _one(announcements=full_coverage(doc, coverage_start="2026-02-15"))
    _expect_blocked("v4.6 查詢起點晚於期間第一天", v, s, RC.ANNOUNCEMENT_COVERAGE_INCOMPLETE)

    v, s = _one(announcements=full_coverage(doc, coverage_start="2026-01-01"))
    _expect_verified("v4.6 對照 查詢起點正好是期間第一天", v, s)

    v, s = _one(announcements=full_coverage(doc, searched_event_types=["financial_report"]))
    _expect_blocked("v4.6 沒有搜尋自結損益、法說會等事件類型", v, s, RC.ANNOUNCEMENT_COVERAGE_INCOMPLETE)

    v, s = _one(announcements=full_coverage(doc, coverage_end="2026-01-15"))
    _expect_blocked("v4.6 最早事件落在宣告的查詢終點之後", v, s, RC.ANNOUNCEMENT_COVERAGE_INCOMPLETE)

    v, s = _one(announcements=full_coverage(doc, coverage_start="not-a-date"))
    _expect_blocked("v4.6 查詢範圍無法解析", v, s, RC.ANNOUNCEMENT_COVERAGE_INCOMPLETE)

    v = FakeIndependentVerifier()
    s = make_verified_snapshot(v, "T43", "2026H1", BASE_SNAP, BASE_EARN, 10.0)
    _expect_blocked("v4.6 期間格式無法判斷起始日", v, s, RC.ANNOUNCEMENT_COVERAGE_INCOMPLETE)


def test_v46_corrections():
    orig = make_announcement("T43", "2026Q1", "2026-01-20T13:00:00+08:00", doc_id="MOPS-T43-ORIG")

    def correction(corrects):
        rec = {"ticker": "T43", "fiscal_quarter": "2026Q1", "event_type": "financial_report",
               "announced_at": "2026-01-22T10:00:00+08:00", "is_correction": True}
        if corrects:
            rec["corrects_document_id"] = corrects
        return make_announcement("T43", "2026Q1", rec["announced_at"], doc_id="MOPS-T43-CORR", records=[rec])

    v, s = _one(announcements=[correction("MOPS-T43-ORIG")])
    _expect_blocked("v4.6 只有更正公告、原始公告沒有一起回傳", v, s, RC.ANNOUNCEMENT_CORRECTION_ORIGINAL_MISSING)

    v, s = _one(announcements=[correction(None)])
    _expect_blocked("v4.6 更正公告沒有註明被更正的公告", v, s, RC.ANNOUNCEMENT_CORRECTION_ORIGINAL_MISSING)

    v, s = _one(announcements=[correction("MOPS-T43-ORIG"), orig])
    _expect_verified("v4.6 更正與原始公告都回傳、封存早於原始公告", v, s)

    v, s = _one(snap="2026-01-21T08:00:00+08:00", announcements=[correction("MOPS-T43-ORIG"), orig])
    _expect_blocked("v4.6 封存在原始公告之後、更正之前 → 截止點以原始公告為準", v, s,
                    RC.EVIDENCE_ARCHIVED_AFTER_EARNINGS)


def test_v46_captured_before_comes_from_official_time():
    """傳給封存驗證器的截止點必須是官方時間，不是 adapter 聲稱的時間。"""
    from datetime import datetime, timezone
    v, s = _one(earn="2026-01-25T13:30:00+08:00", official_announced_at=BASE_EARN)
    run_gate5b([s], v)
    got = v.captured_before[s.snapshot_date.provenance.source_url]
    assert got == datetime(2026, 1, 20, 5, 0, tzinfo=timezone.utc), f"FAIL: 截止點 {got}"
    print(f"✓ v4.6 傳給封存驗證器的截止點 = 官方 {got.isoformat()}（adapter 聲稱 1/25 不影響）")


def test_v46_verifier_fault_code_allowlist():
    from independent_verifier import VerifierFault
    v, s = _one(registered=VerifierFault("served bytes differ", reject_code=RC.EVIDENCE_HASH_MISMATCH))
    _expect_blocked("v4.6 驗證器回報白名單代碼（內容不符）", v, s, RC.EVIDENCE_HASH_MISMATCH)
    v, s = _one(registered=VerifierFault("tries to pick its own code", reject_code=RC.CLAIMED_TIER_OVERSTATED))
    r = run_gate5b([s], v)
    assert r.evidence_count == 0 and RC.EVIDENCE_VERIFIER_ERROR in r.reject_codes, r.reject_codes
    print("✓ v4.6 驗證器例外附非白名單代碼 → 一律記為 EVIDENCE_VERIFIER_ERROR")


# ======================================================================
# v4.7 驗收：官方公告完整性由實際查詢證據證明，不再相信驗證器宣告
# ======================================================================

def test_v47_withheld_earlier_document():
    """驗證器宣告完整、也附了查詢紀錄，但官方清單列出的 1/8 自結公告沒有交出原文。"""
    early_id = "MOPS-T43-2026Q1-self_reported_results"
    late = make_announcement("T43", "2026Q1", "2026-01-20T13:00:00+08:00", event_type="financial_report")
    withheld = {"self_reported_results": [{"document_id": early_id, "fiscal_quarter": "2026Q1",
                                           "announced_at": "2026-01-08T16:00:00+08:00"}]}
    v, s = _one(snap="2026-01-10T08:00:00+08:00",
                announcements=full_coverage([late], ticker="T43", extra_listing=withheld))
    _expect_blocked("v4.7 官方清單列出較早公告、驗證器沒交原文（宣告再完整也擋下）", v, s,
                    RC.ANNOUNCEMENT_LISTED_DOCUMENT_MISSING)

    # 已知限制（如實記錄）：清單與原文「一致地」漏掉同一份公告，本程式無法識破，
    # 只能靠另一個獨立環境重播同樣的查詢、比對列出的公告。
    v, s = _one(snap="2026-01-10T08:00:00+08:00", announcements=full_coverage([late], ticker="T43"))
    r = run_gate5b([s], v)
    assert r.evidence_count == 1
    print("✓ v4.7 已知限制：清單與原文一致地漏掉同一份公告時無法識破 → 需獨立環境重播比對（未解決，如實記錄）")


def test_v47_pagination_and_truncation():
    doc = [make_announcement("T43", "2026Q1", BASE_EARN)]
    v, s = _one(announcements=full_coverage(doc, pages_per_type=2))
    _expect_verified("v4.7 對照 每類 2 頁且頁頁齊全", v, s)
    v, s = _one(announcements=full_coverage(doc, pages_per_type=3, drop_pages={("financial_report", 2)}))
    _expect_blocked("v4.7 缺第 2 頁", v, s, RC.ANNOUNCEMENT_PAGINATION_INCOMPLETE)
    v, s = _one(announcements=full_coverage(doc, count_delta=1))
    _expect_blocked("v4.7 各頁合計筆數少於官方宣稱總數（結果被截斷）", v, s, RC.ANNOUNCEMENT_PAGINATION_INCOMPLETE)
    v, s = _one(announcements=full_coverage(doc, truncated_types={"investor_conference"}))
    _expect_blocked("v4.7 官方回應標示截斷", v, s, RC.ANNOUNCEMENT_PAGINATION_INCOMPLETE)


def test_v47_query_record_integrity():
    doc = [make_announcement("T43", "2026Q1", BASE_EARN)]
    v, s = _one(announcements=full_coverage(doc, tamper_query_hash=True))
    _expect_blocked("v4.7 查詢回應雜湊與原始位元組不符", v, s, RC.ANNOUNCEMENT_HASH_MISMATCH)
    v, s = _one(announcements=full_coverage(doc, query_domain="mirror.example.com"))
    _expect_blocked("v4.7 查詢不是對官方網域發出", v, s, RC.ANNOUNCEMENT_SOURCE_NOT_OFFICIAL)
    v, s = _one(announcements=AnnouncementQueryResult(
        documents=doc, queries=[], coverage_start="1990-01-01", coverage_end="2099-12-31",
        searched_event_types=sorted(REQUIRED_SEARCHED_EVENT_TYPES)))
    _expect_blocked("v4.7 只有完整宣告、沒有任何查詢紀錄", v, s, RC.ANNOUNCEMENT_COVERAGE_INCOMPLETE)


def test_v47_listing_document_cross_check():
    doc_id = "MOPS-T43-2026Q1-financial_report"
    doc = [make_announcement("T43", "2026Q1", BASE_EARN)]
    v, s = _one(announcements=full_coverage(doc, drop_listing_ids={doc_id}))
    _expect_blocked("v4.7 驗證器交出的公告不在任何官方清單中", v, s, RC.ANNOUNCEMENT_DOCUMENT_NOT_LISTED)
    v, s = _one(announcements=full_coverage(doc, listing_overrides={doc_id: {"announced_at": None}}))
    _expect_blocked("v4.7 官方清單的公告時間缺漏", v, s, RC.ANNOUNCEMENT_TIME_UNVERIFIED)
    v, s = _one(announcements=full_coverage(doc, listing_overrides={doc_id: {"announced_at": "2026-01-21T13:00:00+08:00"}}))
    _expect_blocked("v4.7 清單時間與原文時間不一致", v, s, RC.ANNOUNCEMENT_CONTENT_MISMATCH)
    v, s = _one(announcements=full_coverage(doc, listing_overrides={doc_id: {"fiscal_quarter": None}}))
    _expect_blocked("v4.7 清單項目沒有標示期間", v, s, RC.ANNOUNCEMENT_CONTENT_MISMATCH)


# ======================================================================
# v4.8 驗收：依宣告字元集嚴格解碼，不悄悄改用其他編碼
# ======================================================================

def _big5_announcement(content_type):
    recs = [{"ticker": "T43", "fiscal_quarter": "2026Q1", "event_type": "financial_report",
             "announced_at": BASE_EARN, "title": "測試公司自結損益公告"}]
    return make_announcement("T43", "2026Q1", BASE_EARN, records=recs, content_type=content_type,
                             content_bytes=json.dumps({"records": recs}, ensure_ascii=False).encode("big5"))


def test_v48_declared_charset_decoding():
    v, s = _one(announcements=[_big5_announcement("application/json; charset=big5")])
    _expect_verified("v4.8 公告原文宣告 Big5 → 依宣告解碼", v, s)
    v, s = _one(announcements=[_big5_announcement("")])
    _expect_blocked("v4.8 同一份 Big5 位元組但未宣告字元集（不悄悄改用 Big5）", v, s,
                    RC.ANNOUNCEMENT_CONTENT_MISMATCH)
    v, s = _one(announcements=[_big5_announcement("application/json; charset=shift_jis")])
    _expect_blocked("v4.8 宣告不在允許清單的編碼", v, s, RC.ANNOUNCEMENT_CONTENT_MISMATCH)

    recs = [{"ticker": "T43", "fiscal_quarter": "2026Q1", "event_type": "financial_report", "announced_at": BASE_EARN}]
    bom = make_announcement("T43", "2026Q1", BASE_EARN, records=recs,
                            content_bytes=b"\xef\xbb\xbf" + json.dumps({"records": recs}).encode("utf-8"))
    v, s = _one(announcements=[bom])
    _expect_verified("v4.8 帶 BOM 的 UTF-8、未宣告字元集", v, s)

    doc = [make_announcement("T43", "2026Q1", BASE_EARN)]
    v, s = _one(announcements=full_coverage(doc, query_encoding="big5", query_content_type="application/json; charset=big5"))
    _expect_verified("v4.8 官方查詢清單頁宣告 Big5", v, s)
    v, s = _one(announcements=full_coverage(doc, query_encoding="big5"))
    _expect_blocked("v4.8 官方查詢清單頁是 Big5 但未宣告", v, s, RC.ANNOUNCEMENT_CONTENT_MISMATCH)


def test_v48_consensus_content_charset():
    recs = [{"ticker": "T43", "fiscal_quarter": "2026Q1", "consensus_eps": 10.0, "broker": "測試券商"}]
    big5 = json.dumps({"records": recs}, ensure_ascii=False).encode("big5")
    v, s = _one(content_bytes=big5, bundle_overrides={"content_type": "text/plain; charset=cp950"})
    _expect_verified("v4.8 共識封存內容宣告 CP950", v, s)
    v, s = _one(content_bytes=big5)
    _expect_blocked("v4.8 共識封存內容是 Big5 但未宣告", v, s, RC.EVIDENCE_CONTENT_MISMATCH)


def test_v45_contract_fixtures_roundtrip():
    """跨語言契約案例：只讀 JSON 必須重現同樣判定；比對工具也必須抓得到差異。"""
    import copy
    import os
    import tempfile
    import contract_fixtures as CF
    assert CF.check() == [], f"FAIL: 契約案例與目前程式不一致 {CF.check()}"
    with open(CF.FIXTURE_PATH, encoding="utf-8") as f:
        doc = json.load(f)
    for field, new in [("evidence_count", 99), ("reject_codes", ["SOMETHING_ELSE"])]:
        bad = copy.deepcopy(doc)
        bad["cases"][0]["expected"][field] = new
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as tf:
            json.dump(bad, tf, ensure_ascii=False)
        try:
            assert CF.check(tf.name), f"FAIL: 竄改 {field} 後比對工具沒有發現"
        finally:
            os.unlink(tf.name)
    print(f"✓ v4.5 契約案例 {len(doc['cases'])} 個：只讀 JSON 重現一致；竄改預期值會被抓到")


if __name__ == "__main__":
    tests = [
        test_case_1_psr_null_duplicate,
        test_case_2_peg_no_eps_fake_coverage,
        test_case_2b_peg_outlier_and_wrong_year,
        test_case_3_single_guidance_basis_match,
        test_case_4_same_quarter_repeated,
        test_case_6_gate5b_false_declaration,
        test_case_5_peer_consensus_wrong_company,
        test_case_5b_gate8_same_ticker_diff_company_id,
        test_case_9_same_day_no_time_precision,
        test_case_10_unverified_link_source,
        test_case_11_gate5b_positive_verified,
        test_case_11b_gate5b_no_verifier_always_fails_closed,
        test_case_11c_gate5b_missing_one_layer_still_blocks,
        test_case_12_peg_negative_zero_eps_mad,
        test_case_13_same_instant_different_timezones,
        test_case_14_official_tier_forged,
        test_case_15_mad_zero_with_extreme,
        test_case_16_invalid_timestamp,
        test_case_17_duplicate_quarter_different_consensus,
        test_case_17b_duplicate_quarter_same_value_is_fine,
        test_case_18_verified_tier_injection_blocked,
        test_case_19_forged_claims_disagree_with_independent_source,
        test_case_19b_claimed_hash_mismatch_audited,
        test_case_20_peg_same_institution_conflicting_eps,
        test_v43_p0_1_injection_with_official_url,
        test_v43_p0_2_content,
        test_v43_p0_2_content_positive_formats,
        test_v43_p0_3_time,
        test_v43_p0_4_integrity,
        test_v43_p1_1_time_parsing,
        test_v43_fail_closed,
        test_v43_atomic_single_fetch_and_trail,
        test_v43_report_contract,
        test_v44_core_attack_adapter_postdates_announcement,
        test_v44_no_announcement_verifier_never_fetches_archive,
        test_v44_announcement_fail_closed,
        test_v44_announcement_document_defects,
        test_v44_earliest_disclosure_is_cutoff,
        test_v44_one_bad_document_fails_whole_period,
        test_v44_date_only_announcement_is_conservative,
        test_v44_one_query_per_quarter_and_trail,
        test_v45_adapter_fields_cannot_affect_decision,
        test_v45_no_source_pointer,
        test_v45_contract_fixtures_roundtrip,
        test_v46_announcement_coverage,
        test_v46_corrections,
        test_v46_captured_before_comes_from_official_time,
        test_v46_verifier_fault_code_allowlist,
        test_v47_withheld_earlier_document,
        test_v47_pagination_and_truncation,
        test_v47_query_record_integrity,
        test_v47_listing_document_cross_check,
        test_v48_declared_charset_decoding,
        test_v48_consensus_content_charset,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except AssertionError as e:
            print(f"✗ {t.__name__}: {e}")
            failed += 1
        except Exception as e:
            print(f"✗ {t.__name__}: 執行例外 {type(e).__name__}: {e}")
            failed += 1
    print(f"\n{'全部通過' if failed == 0 else f'{failed} 項仍有問題'} （共{len(tests)}項）")
