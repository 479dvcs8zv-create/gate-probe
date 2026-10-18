"""
gates.py
========
目前版本（v4.5）的 Gate5B 判定只依據兩份獨立證據：
  1. 官方公告驗證（announcement_verification）查出的最早財務結果揭露時間
  2. 封存證據包驗證（evidence_verification）確認的封存內容、時間與完整性
adapter 的快照時間、公告時間、「財報前」旗標一律只做稽核（CLAIMED_* 代碼），
缺漏、格式錯誤或自相矛盾都不會在獨立驗證之前擋下資料。

以下為 v3 的修改紀錄。其中「宣告矛盾即不採信（DECLARATION_MISMATCH）」等
以 adapter 時間做前置判定的行為，已在 v4.5 移除。

v3 修正重點（對應當時列的 P0/P1）：

  P0 Gate5B 時間驗證：改為三態判定，不再是單純布林值或粗略日期比較。
     - VERIFIED_PRE_EARNINGS：時間精度足夠（非僅限同日的裸日期），
       且確認快照早於公告，且來源 evidence_tier 達到 official_record
       或 immutable_archive，才算數。
     - UNVERIFIABLE_TIME：日期存在但時間精度不足（例如同一天但沒有
       時分資訊，無法判斷財報公告前後），或來源信任層級不足
       （只是一個普通連結，無法證明未被事後修改）。
     - REJECTED_POST_EARNINGS：可確認快照時間在公告之後。
     宣告的布林值若與以上判定矛盾，視為資料自相矛盾（DECLARATION_MISMATCH），
     一律不採信，不會因為「宣告是 False」就豁免判斷。

  P1 PEG 離群值：改用 validation.py 的 MAD 穩健方法，對負值/零值安全。

  P1 去重品質：quality score 現在比對 evidence_tier（可信層級），
     不再只看「有沒有 URL」。

  P1 GateResult 拒絕代碼：新增 reject_codes（穩定機器可讀代碼），
     reasons 仍保留人類可讀文字，兩者一一對應，供 Python↔Worker
     一致性比對使用（比對 code 而非文字，文字可以改措辭不影響比對）。
"""

from dataclasses import dataclass, field
from typing import List, Optional

from schema import TickerInputBundle
from validation import (
    dedupe_and_filter, validate_then_dedupe, cross_match_peer_consensus,
    dedupe_by_key, filter_plausible_numeric, detect_value_conflicts,
)
from reject_codes import RC, Diagnostics
from evidence_verification import verify_pre_earnings_evidence, tier_was_overstated, verify_domain_identity
from announcement_verification import AnnouncementVerifier, verify_earnings_announcement
from time_utils import parse_with_precision, classify_timing
from independent_verifier import IndependentVerifier

# ---- 可調門檻常數 ----
PSR_MIN_QUARTERS = 20
PEG_MIN_ANALYST_COVERAGE = 3
GATE5A_MIN_GUIDANCE_RECORDS = 6
GATE5B_MIN_QUARTERS = 8
GATE8_MIN_PEER_QUALIFIED = 3
GATE8_MIN_YEARS_CONSENSUS = 2

VERIFIED_TIERS = {"official_record", "immutable_archive"}


@dataclass
class GateResult:
    gate_name: str
    status: str                 # "pass" | "insufficient" | "not_connected"
    reasons: List[str] = field(default_factory=list)       # 人類可讀
    reject_codes: List[str] = field(default_factory=list)  # 機器可讀，與 reasons 一一對應
    raw_count: int = 0
    evidence_count: int = 0
    evidence_trail: List[dict] = field(default_factory=list)  # 可追溯驗證紀錄（目前由 Gate5B 填入）

    def summary(self) -> str:
        flag = ""
        if self.raw_count > self.evidence_count:
            flag = f"  ⚠ 原始{self.raw_count}筆 → 有效僅{self.evidence_count}筆"
        return f"[{self.status.upper():14s}] {self.gate_name} — {'; '.join(self.reasons) if self.reasons else 'OK'}{flag}"

    @classmethod
    def from_diag(cls, gate_name: str, status: str, diag: Diagnostics, raw_count: int = 0, evidence_count: int = 0):
        return cls(gate_name=gate_name, status=status, reasons=diag.reasons, reject_codes=diag.codes,
                    raw_count=raw_count, evidence_count=evidence_count)


def eval_gate4_moat(bundle: TickerInputBundle) -> GateResult:
    items = bundle.moat_items
    if not items:
        return GateResult("Gate4_護城河", "not_connected", ["無資料：moat comparisons 未接線"], [RC.DATA_NOT_CONNECTED])
    raw = len(items)
    diag = Diagnostics()
    vr = validate_then_dedupe(items, key_fn=lambda i: (i.peer_name, i.comparison_point), value_fn=lambda i: i.target_value)
    if vr.duplicate_count:
        diag.add(RC.DUPLICATE_REMOVED, f"{vr.duplicate_count}筆重複比較項目已剔除")
    if vr.null_or_empty_count:
        diag.add(RC.NULL_VALUE_REMOVED, f"{vr.null_or_empty_count}筆數值為空已剔除")
    valid = vr.valid_items
    missing_original = [i for i in valid if i.original_text_source is None]
    if missing_original:
        diag.add(RC.MISSING_ORIGINAL_SOURCE, f"{len(missing_original)}/{len(valid)} 筆缺附原文比較證據")
        return GateResult.from_diag("Gate4_護城河", "insufficient", diag, raw, len(valid) - len(missing_original))
    if not valid:
        diag.add(RC.MIN_COUNT_NOT_MET, "去重過濾後無有效比較項目")
        return GateResult.from_diag("Gate4_護城河", "insufficient", diag, raw, 0)
    return GateResult.from_diag("Gate4_護城河", "pass", diag, raw, len(valid))


def eval_psr(bundle: TickerInputBundle) -> GateResult:
    h = bundle.psr_history
    if h is None:
        return GateResult("PSR", "not_connected", ["PSR 五年歷史未接線"], [RC.DATA_NOT_CONNECTED])
    raw = len(h.quarterly_series)
    diag = Diagnostics()
    vr = validate_then_dedupe(h.quarterly_series, key_fn=lambda dp: dp.provenance.as_of_date, value_fn=lambda dp: dp)
    if vr.duplicate_count:
        diag.add(RC.DUPLICATE_REMOVED, f"{vr.duplicate_count}筆為同一日期重複，已剔除")
    if vr.null_or_empty_count:
        diag.add(RC.NULL_VALUE_REMOVED, f"{vr.null_or_empty_count}筆為空值，已剔除")
    n = len(vr.valid_items)
    if n < PSR_MIN_QUARTERS:
        diag.add(RC.MIN_COUNT_NOT_MET, f"同口徑({h.basis_definition})去重過濾後僅 {n}/{PSR_MIN_QUARTERS} 季")
        return GateResult.from_diag("PSR", "insufficient", diag, raw, n)
    return GateResult.from_diag("PSR", "pass", diag, raw, n)


def eval_peg(bundle: TickerInputBundle) -> GateResult:
    p = bundle.peg_consensus
    if p is None:
        return GateResult("PEG", "not_connected", ["PEG 共識未接線"], [RC.DATA_NOT_CONNECTED])
    raw = len(p.eps_estimates)
    diag = Diagnostics()

    year_matched = [e for e in p.eps_estimates if e.target_year == p.target_year]
    if len(year_matched) < raw:
        diag.add(RC.YEAR_MISMATCH, f"{raw - len(year_matched)}筆目標年度與{p.target_year}不符，已剔除")

    # 衝突偵測必須在去重之前做：去重會依品質分數悄悄選一筆，若先去重
    # 再檢測衝突，同key只剩一筆，永遠偵測不到衝突。同一機構同一年度
    # 若出現彼此不同的EPS數值，整組排除，不能讓品質排序掩蓋掉真實分歧。
    conflicts = detect_value_conflicts(year_matched, key_fn=lambda e: e.institution_id, value_fn=lambda e: e.eps)
    if conflicts:
        for inst, values in conflicts.items():
            diag.add(RC.CONFLICTING_VALUES_SAME_KEY, f"機構{inst}: 出現{len(values)}個不同EPS值{values}，視為衝突，整組排除待人工覆核")
    conflicting_insts = set(conflicts.keys())
    non_conflicting = [e for e in year_matched if e.institution_id not in conflicting_insts]

    vr = validate_then_dedupe(non_conflicting, key_fn=lambda e: e.institution_id, value_fn=lambda e: e.eps)
    if vr.duplicate_count:
        diag.add(RC.DUPLICATE_REMOVED, f"{vr.duplicate_count}家機構ID重複（數值相同），已剔除")
    if vr.null_or_empty_count:
        diag.add(RC.NULL_VALUE_REMOVED, f"{vr.null_or_empty_count}筆EPS為空值，已剔除")

    plaus = filter_plausible_numeric(vr.valid_items, value_fn=lambda e: e.eps)
    for note in plaus.notes:
        if "樣本數" in note:
            code = RC.SAMPLE_TOO_SMALL_FOR_OUTLIER_CHECK
        elif "待確認離群值" in note:
            code = RC.OUTLIER_UNDETERMINED
        elif "MAD=0" in note:
            code = RC.ZERO_SPREAD_SKIP_OUTLIER_CHECK
        else:
            code = RC.OUTLIER_REMOVED
        diag.add(code, note)

    actual_coverage = len(plaus.valid_items)
    if p.coverage_count != actual_coverage:
        diag.add(RC.CLAIMED_COUNT_MISMATCH, f"聲稱覆蓋{p.coverage_count}家，實際驗證後僅{actual_coverage}家有效，已改用實際值")

    if actual_coverage < PEG_MIN_ANALYST_COVERAGE:
        diag.add(RC.MIN_COUNT_NOT_MET, f"{p.target_year}年實際有效且合理的共識僅 {actual_coverage}/{PEG_MIN_ANALYST_COVERAGE} 家")
        return GateResult.from_diag("PEG", "insufficient", diag, raw, actual_coverage)
    return GateResult.from_diag("PEG", "pass", diag, raw, actual_coverage)


def eval_capacity_risk(bundle: TickerInputBundle) -> GateResult:
    c = bundle.capacity_risk
    if c is None:
        return GateResult("產能風險", "not_connected", ["產能風險資料未接線"], [RC.DATA_NOT_CONNECTED])
    diag = Diagnostics()
    if not c.fab_location_exposure:
        diag.add(RC.MIN_COUNT_NOT_MET, "缺：產地曝險")
    if not c.alternative_sources:
        diag.add(RC.MIN_COUNT_NOT_MET, "缺：替代方案")
    if not c.customer_concentration:
        diag.add(RC.MIN_COUNT_NOT_MET, "缺：客戶集中度")
    if diag.reasons:
        return GateResult.from_diag("產能風險", "insufficient", diag)
    return GateResult.from_diag("產能風險", "pass", diag)


def _is_empty_dp(dp) -> bool:
    return dp is None or dp.value is None or (isinstance(dp.value, str) and dp.value.strip() == "")


def eval_cb(bundle: TickerInputBundle) -> GateResult:
    records = bundle.cb_records
    if not records:
        return GateResult("可轉債CB", "not_connected", ["CB 資料未接線"], [RC.DATA_NOT_CONNECTED])
    diag = Diagnostics()
    valid = 0
    for r in records:
        if not r.event_log:
            diag.add(RC.MIN_COUNT_NOT_MET, f"{r.cb_id} 缺事件核對紀錄")
            continue
        if _is_empty_dp(r.conversion_price) or _is_empty_dp(r.shares_outstanding_same_day) or _is_empty_dp(r.fx_rate_same_day):
            diag.add(RC.NULL_VALUE_REMOVED, f"{r.cb_id} 轉換價/股本/匯率其中一項為空")
            continue
        valid += 1
    if diag.reasons:
        return GateResult.from_diag("可轉債CB", "insufficient", diag, len(records), valid)
    return GateResult.from_diag("可轉債CB", "pass", diag, len(records), valid)


def eval_holder_concentration(bundle: TickerInputBundle) -> GateResult:
    h = bundle.holder_concentration
    if h is None:
        return GateResult("大戶籌碼", "not_connected", ["大戶持股分布未接線"], [RC.DATA_NOT_CONNECTED])
    diag = Diagnostics()
    vr = validate_then_dedupe(h.weekly_distribution, key_fn=lambda dp: dp.provenance.as_of_date, value_fn=lambda dp: dp)
    if vr.duplicate_count:
        diag.add(RC.DUPLICATE_REMOVED, f"{vr.duplicate_count}週資料重複，已剔除")
    n = len(vr.valid_items)
    if h.consecutive_weeks_trend is None:
        diag.add(RC.MIN_COUNT_NOT_MET, "延續性尚未計算")
        return GateResult.from_diag("大戶籌碼", "insufficient", diag, evidence_count=n)
    if n < 2:
        diag.add(RC.MIN_COUNT_NOT_MET, f"去重後僅{n}週有效資料，不足以支撐延續性判斷")
        return GateResult.from_diag("大戶籌碼", "insufficient", diag, evidence_count=n)
    return GateResult.from_diag("大戶籌碼", "pass", diag, evidence_count=n)


def eval_gate5a_guidance(bundle: TickerInputBundle) -> GateResult:
    records = bundle.guidance_records
    if not records:
        return GateResult("Gate5A_年度指引", "not_connected", ["指引配對資料未接線"], [RC.DATA_NOT_CONNECTED])
    raw = len(records)
    diag = Diagnostics()
    vr = validate_then_dedupe(records, key_fn=lambda r: r.fiscal_year, value_fn=lambda r: r.guidance_release_date)
    if vr.duplicate_count:
        diag.add(RC.DUPLICATE_REMOVED, f"{vr.duplicate_count}筆年度重複，已剔除")
    if vr.null_or_empty_count:
        diag.add(RC.NULL_VALUE_REMOVED, f"{vr.null_or_empty_count}筆缺原發布日，已剔除")
    valid = vr.valid_items
    bad_basis = [r for r in valid if not r.basis_matches]
    if bad_basis:
        diag.add(RC.BASIS_MISMATCH, f"{len(bad_basis)}筆口徑不一致")
    good = [r for r in valid if r.basis_matches]
    if len(good) < GATE5A_MIN_GUIDANCE_RECORDS:
        diag.add(RC.MIN_COUNT_NOT_MET, f"有效且口徑一致的指引僅 {len(good)}/{GATE5A_MIN_GUIDANCE_RECORDS} 筆")
        return GateResult.from_diag("Gate5A_年度指引", "insufficient", diag, raw, len(good))
    return GateResult.from_diag("Gate5A_年度指引", "pass", diag, raw, len(good))


# ---------------- Gate5B：三態時間驗證 + 四層存證驗證 ----------------
# 時間解析/區間比較邏輯已移至 time_utils.py（供 evidence_verification.py 共用）。
# 來源可信層級的四層驗證（網域/內容對應/時間戳確認/不可變證明）
# 已移至 evidence_verification.verify_pre_earnings_evidence()，
# 這裡只負責：時間先後判定 → 四層驗證 → 同季數值衝突偵測 → 去重計數。


def _claimed_timing_audits(s) -> list:
    """adapter 自報時間的一致性稽核（只記錄，不影響判定）。
    對缺漏、無法解析、甚至型別錯誤的欄位都必須穩健：這裡出錯不能變成拒絕理由。"""
    try:
        snap_raw = getattr(getattr(s, "snapshot_date", None), "value", None)
        earn_raw = getattr(getattr(s, "earnings_announcement_date", None), "value", None)
        declared_pre = bool(getattr(s, "snapshot_taken_before_earnings", False))
        audits = []
        snap_dt, snap_prec = parse_with_precision(snap_raw)
        earn_dt, earn_prec = parse_with_precision(earn_raw)
        if snap_raw is not None and snap_dt is None:
            audits.append(f"adapter 聲稱的快照時間「{snap_raw}」無法解析")
        if snap_dt is not None and earn_dt is not None:
            timing = classify_timing(snap_dt, snap_prec, earn_dt, earn_prec)
            if timing == "POST" and declared_pre:
                audits.append("adapter 宣告「財報前」，但它自報的快照時間晚於它自報的公告時間")
            elif timing == "PRE" and not declared_pre:
                audits.append("adapter 宣告「非財報前」，但它自報的快照時間早於它自報的公告時間")
            elif timing == "POST":
                audits.append("adapter 自報這是財報後的快照")
        return audits
    except Exception as e:  # 稽核失敗只記錄，不中斷也不拒絕
        return [f"adapter 時間欄位稽核時發生錯誤：{type(e).__name__}"]


def eval_gate5b_pre_earnings(bundle: TickerInputBundle, verifier: IndependentVerifier = None,
                             record_extractor=None, announcement_verifier: AnnouncementVerifier = None,
                             announcement_extractor=None, announcement_listing_extractor=None) -> GateResult:
    """verifier：封存證據包驗證器；announcement_verifier：官方公告時間驗證器。
    兩者預設都是 Null 實作（一律回傳無法查證），所以在接上真正能做獨立查證的實作
    之前，這個 Gate 不可能判定 pass——這是刻意的保守失敗。
    v4.5 起 adapter 的快照時間、公告時間與「財報前」旗標全部只做稽核，
    不會在獨立驗證之前擋下或放行任何一筆；判定只依據官方公告與封存證據包。"""
    snaps = bundle.pre_earnings_snapshots
    raw = len(snaps)
    diag = Diagnostics()
    timing_verified = []   # 進入獨立驗證的快照（名稱沿用舊版；v4.5 起不再依 adapter 時間篩選）

    for s in snaps:
        eps = getattr(s, "consensus_eps", None)
        if eps is None or getattr(eps, "value", None) is None:
            diag.add(RC.NULL_VALUE_REMOVED, f"{s.fiscal_quarter}: 共識值為空")  # 待驗的值本身缺漏
            continue
        if getattr(getattr(s, "snapshot_date", None), "provenance", None) is None:
            diag.add(RC.SOURCE_UNVERIFIABLE, f"{s.fiscal_quarter}: 缺來源網址，無法進行獨立查證")
            continue
        for msg in _claimed_timing_audits(s):
            diag.add(RC.CLAIMED_TIMING_INCONSISTENT, f"{s.fiscal_quarter}: {msg}")
        timing_verified.append(s)

    # ---- 四層存證驗證：網域身分 + 內容對應 + 時間戳確認 + 不可變證明 ----
    # 全部四層都通過，才真正算 VERIFIED_PRE_EARNINGS；任一層沒過，
    # 不管網域多權威，一律視為不足採信。每次都重新計算，不信任
    # 外部（adapter）預先塞入的任何驗證結果。
    # 官方公告時間：每個（公司、季度）最多查一次，同季的所有快照共用同一個截止點；
    # 網域身分不過的快照不會用到截止點，就不發出官方查詢。
    announcements = {}

    def _announcement_for(s):
        if verify_domain_identity(s.snapshot_date.provenance.source_url) != "official_record":
            return None
        key = (s.ticker, s.fiscal_quarter)
        if key not in announcements:
            announcements[key] = verify_earnings_announcement(
                s.ticker, s.fiscal_quarter, verifier=announcement_verifier, record_extractor=announcement_extractor,
                listing_extractor=announcement_listing_extractor)
        return announcements[key]

    layer_verified = []
    trail = []
    for s in timing_verified:
        result = verify_pre_earnings_evidence(s, verifier=verifier, record_extractor=record_extractor,
                                              announcement=_announcement_for(s))
        trail.append({"fiscal_quarter": s.fiscal_quarter, "final_tier": result["final_tier"], **result["trace"]})

        prov = s.snapshot_date.provenance
        if tier_was_overstated(prov, result["domain_identity"]):
            diag.add(RC.CLAIMED_TIER_OVERSTATED,
                      f"{s.fiscal_quarter}: 來源宣告「{prov.claimed_evidence_tier}」，"
                      f"但獨立驗證（網域規則）結果僅為「{result['domain_identity']}」，宣告與實際不符，已記錄稽核")

        for code, msg in result["audits"]:
            diag.add(code, f"{s.fiscal_quarter}: {msg}")

        if result["final_tier"] not in VERIFIED_TIERS:
            for code, msg in result["failures"]:
                diag.add(code, f"{s.fiscal_quarter}: {msg}")
            failed_layers = []
            if result["domain_identity"] not in VERIFIED_TIERS:
                failed_layers.append("網域身分")
            if not result["announcement_verified"]:
                failed_layers.append("官方公告時間")
            if not result["content_correspondence"]:
                failed_layers.append("內容對應")
            if not result["timestamp_confirmation"]:
                failed_layers.append("時間戳獨立確認")
            if not result["immutability_proof"]:
                failed_layers.append("不可變證明")
            diag.add(RC.SOURCE_UNVERIFIABLE,
                      f"{s.fiscal_quarter}: 四層存證驗證未全部通過（缺：{'、'.join(failed_layers)}），列為未能驗證")
            continue
        layer_verified.append(s)

    # ---- 同季數值衝突偵測：不能靠品質分數悄悄選一筆蓋過真實衝突 ----
    conflicts = detect_value_conflicts(layer_verified, key_fn=lambda s: s.fiscal_quarter,
                                        value_fn=lambda s: s.consensus_eps)
    if conflicts:
        for q, values in conflicts.items():
            diag.add(RC.CONFLICTING_VALUES_SAME_KEY,
                      f"{q}: 同季出現{len(values)}個不同共識EPS值{values}，視為實質衝突，整季排除待人工覆核")
    conflicting_quarters = set(conflicts.keys())
    non_conflicting = [s for s in layer_verified if s.fiscal_quarter not in conflicting_quarters]

    # 衝突已排除，剩下的同季重複必定是真正的「同一筆資料重複」而非數值分歧，
    # 這時去重挑品質較佳的一筆才安全。
    vr = validate_then_dedupe(non_conflicting, key_fn=lambda s: s.fiscal_quarter, value_fn=lambda s: s.consensus_eps)
    if vr.duplicate_count:
        diag.add(RC.DUPLICATE_REMOVED, f"{vr.duplicate_count}季重複（數值相同，已驗證通過者中），已剔除")

    n = len(vr.valid_items)
    if n < GATE5B_MIN_QUARTERS:
        diag.add(RC.MIN_COUNT_NOT_MET,
                  f"通過時間判定+四層存證驗證+衝突檢查後僅 {n}/{GATE5B_MIN_QUARTERS} 季達 VERIFIED_PRE_EARNINGS")
        result = GateResult.from_diag("Gate5B_財報前共識", "insufficient", diag, raw, n)
    else:
        result = GateResult.from_diag("Gate5B_財報前共識", "pass", diag, raw, n)
    result.evidence_trail = trail
    return result


def eval_gate8_peers(bundle: TickerInputBundle, required_years: list = None) -> GateResult:
    peers = bundle.peer_qualifications
    consensus = bundle.peer_consensus_2yr
    diag = Diagnostics()
    raw_peer_count = len(peers)

    peers_with_ticker = [p for p in peers if p.ticker]
    if len(peers_with_ticker) < len(peers):
        diag.add(RC.MISSING_TICKER, f"{len(peers) - len(peers_with_ticker)}家同業缺股票代碼，已剔除")
    peer_dedup = dedupe_by_key(peers_with_ticker, key_fn=lambda p: p.ticker)
    if peer_dedup.duplicate_count:
        diag.add(RC.DUPLICATE_REMOVED, f"{peer_dedup.duplicate_count}家同業股票代碼重複列示，已剔除")
    qualified = [p for p in peer_dedup.valid_items if p.qualifies]

    match_vr = cross_match_peer_consensus(peer_dedup.valid_items, consensus)
    matched_consensus = match_vr.valid_items
    for note in match_vr.notes:
        code = RC.COMPANY_ID_MISMATCH if "公司識別碼" in note else (
            RC.MISSING_TICKER if "缺股票代碼" in note else RC.TICKER_NOT_QUALIFIED)
        diag.add(code, note)

    valid_consensus = [c for c in matched_consensus if c.consensus_value and c.consensus_value.value is not None]
    empty_dropped = len(matched_consensus) - len(valid_consensus)
    if empty_dropped:
        diag.add(RC.NULL_VALUE_REMOVED, f"{empty_dropped}筆共識數值為空，已剔除")

    year_dedup = dedupe_by_key(valid_consensus, key_fn=lambda c: (c.ticker, c.year))
    if year_dedup.duplicate_count:
        diag.add(RC.DUPLICATE_REMOVED, f"{year_dedup.duplicate_count}筆同業年度共識重複，已剔除")

    covered_years = set(c.year for c in year_dedup.valid_items)

    if required_years:
        missing_years = [y for y in required_years if y not in covered_years]
        years_ok = len(missing_years) == 0
        if missing_years:
            diag.add(RC.REQUIRED_YEAR_MISSING, f"缺少必要年度 {missing_years} 的有效共識")
    else:
        years_ok = len(covered_years) >= GATE8_MIN_YEARS_CONSENSUS
        if not years_ok:
            diag.add(RC.MIN_COUNT_NOT_MET, f"有效且配對正確的共識涵蓋僅 {len(covered_years)}/{GATE8_MIN_YEARS_CONSENSUS} 年度")

    peer_ok = len(qualified) >= GATE8_MIN_PEER_QUALIFIED
    if not peer_ok:
        diag.add(RC.MIN_COUNT_NOT_MET, f"合格同業（經ticker驗證）僅 {len(qualified)}/{GATE8_MIN_PEER_QUALIFIED}")

    if not peer_ok or not years_ok:
        return GateResult.from_diag("Gate8_同業", "insufficient", diag, raw_peer_count, len(qualified))
    return GateResult.from_diag("Gate8_同業", "pass", diag, raw_peer_count, len(qualified))


ALL_GATE_EVALUATORS = [
    eval_gate4_moat,
    eval_psr,
    eval_peg,
    eval_capacity_risk,
    eval_cb,
    eval_holder_concentration,
    eval_gate5a_guidance,
    eval_gate5b_pre_earnings,
    eval_gate8_peers,
]


def run_all_gates(bundle: TickerInputBundle, gate5b_verifier: IndependentVerifier = None,
                  gate5b_record_extractor=None, gate5b_announcement_verifier: AnnouncementVerifier = None,
                  gate5b_announcement_extractor=None, gate5b_announcement_listing_extractor=None) -> List[GateResult]:
    """gate5b_verifier：封存證據包驗證器；gate5b_announcement_verifier：官方公告時間驗證器。
    兩者預設都是 Null 實作（一律 fail-closed）。兩個 extractor 是特定網站頁面的
    結構化解析器，預設只支援 JSON/CSV。其他 Gate 不需要這些參數。"""
    results = []
    for fn in ALL_GATE_EVALUATORS:
        try:
            if fn is eval_gate5b_pre_earnings:
                results.append(fn(bundle, verifier=gate5b_verifier, record_extractor=gate5b_record_extractor,
                                  announcement_verifier=gate5b_announcement_verifier,
                                  announcement_extractor=gate5b_announcement_extractor,
                                  announcement_listing_extractor=gate5b_announcement_listing_extractor))
            else:
                results.append(fn(bundle))
        except Exception as e:
            results.append(GateResult(fn.__name__, "insufficient", [f"判定邏輯例外：{e}"], ["INTERNAL_EXCEPTION"]))
    return results
