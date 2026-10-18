"""
evidence_verification.py (v4.3)
================================
Gate5B 的來源驗證。所有判定只依據「獨立驗證器一次取回的同一份證據包」
（VerifiedEvidenceBundle），adapter 填的 claimed_* 欄位只用來做不一致稽核，
絕不構成任何一層的通過依據。

四層，全部成立才可升級為 official_record（= Gate5B 的 VERIFIED_PRE_EARNINGS）：

  Layer1 網域身分   source_url 屬於允許的官方網域（純網址結構檢查，不需網路）
  Layer2 內容對應   從證據包原始位元組「結構化」解析出紀錄，同一筆紀錄內
                    公司代碼、財報期間、EPS 三者都必須與待驗資料相符；
                    不再用「字串包含」判斷（避免 1.5 命中 11.5、或命中別家公司/別季）
  Layer3 封存時間   captured_at 必須帶時區、必須能由快照 ID 獨立推導核對，
                    且明確早於「官方最早財務結果揭露時間」（v4.4 起由
                    announcement_verification 獨立查證，不再使用 adapter 的公告時間）
  Layer4 不可變性   封存服務具獨立性、快照 ID 綁定原始網址與封存網址、
                    雜湊演算法為 SHA-256、且由 content_bytes 重算的雜湊與回報值一致

fail-closed 原則：取不到證據包、證據包不完整、驗證器拋例外、任何檢查無法完成，
一律判定未通過，並留下對應的 EVIDENCE_* 拒絕代碼。

官方公告時間沒有查證成功時，連封存證據包都不會去取，直接 fail-closed。
adapter 的 earnings_announcement_date 只用於稽核（CLAIMED_ANNOUNCEMENT_TIME_MISMATCH）。

仍需在正式環境補齊的信任邊界（本檔無法代為證明）：
  - 驗證器本身連到哪個封存服務、是否被冒用，需要在 Worker 端做端對端驗收。
"""

import codecs
import csv
import hashlib
import io
import json
import re
from datetime import datetime, timezone as dt_timezone
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

from time_utils import parse_with_precision, classify_timing, to_utc_interval
from independent_verifier import IndependentVerifier, NullIndependentVerifier, VerifiedEvidenceBundle
from reject_codes import RC

OFFICIAL_DOMAINS = {
    "mops.twse.com.tw", "twse.com.tw", "tpex.org.tw",
    "sec.gov", "bls.gov", "frb.gov", "federalreserve.gov",
    "fred.stlouisfed.org", "eia.gov",
}
ARCHIVE_DOMAINS = {
    "web.archive.org", "archive.ph", "archive.today", "perma.cc",
}

# 快照 ID → 封存時間的獨立核對規則。目前只有 Wayback 的 14 位 UTC 時間戳可由 ID 推導時間；
# 其他封存服務在補上規則前，Layer3 一律 fail-closed（EVIDENCE_ARCHIVE_TIMESTAMP_UNVERIFIED）。
SNAPSHOT_TIME_BINDING_RULES = {"web.archive.org": "wayback14"}

# 驗證器拋出例外時可以附帶的拒絕代碼（白名單）。不在名單內的一律記為 EVIDENCE_VERIFIER_ERROR，
# 避免驗證器用例外「指定」任意代碼；不論代碼為何，例外一律 fail-closed。
VERIFIER_FAULT_CODES = {
    RC.EVIDENCE_HASH_MISMATCH,
    RC.EVIDENCE_SNAPSHOT_ID_MISMATCH,
    RC.EVIDENCE_IMMUTABILITY_UNPROVEN,
}

REQUIRED_BUNDLE_FIELDS = (
    "source_url", "archive_url", "snapshot_id", "captured_at",
    "content_bytes", "sha256", "hash_algorithm",
)

# 結構化內容的欄位名稱（同一筆紀錄內取第一個出現的欄位）
ISSUER_KEYS = ("ticker", "symbol", "stock_id", "issuer")
PERIOD_KEYS = ("fiscal_quarter", "period")
EPS_KEYS = ("consensus_eps", "eps", "eps_estimate")

_HEX64 = re.compile(r"[0-9a-f]{64}")


# ---------------------------------------------------------------- 共用小工具

def _domain_of(url):
    if not url:
        return None
    try:
        netloc = urlparse(url).netloc.lower()
    except Exception:
        return None
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc or None


def _domain_matches(domain, allowlist) -> bool:
    if domain is None:
        return False
    return any(domain == d or domain.endswith("." + d) for d in allowlist)


def _strip_hash_prefix(h: str) -> str:
    h = (h or "").strip().lower()
    return h[len("sha256:"):] if h.startswith("sha256:") else h


def _to_decimal(v):
    if v is None or isinstance(v, bool):
        return None
    try:
        d = Decimal(str(v).strip())
    except (InvalidOperation, ValueError):
        return None
    return d if d.is_finite() else None


# 允許的字元編碼。台灣官方與資料商頁面常見 UTF-8 與 Big5／CP950；其他一律 fail-closed，
# 等真實回應確認後再擴充（ops/network_probe.py 的報告會列出實際宣告與可解碼的編碼）。
ALLOWED_CHARSETS = ("utf-8", "utf-8-sig", "big5", "cp950", "big5hkscs")
_ALLOWED_CODEC_NAMES = {codecs.lookup(c).name for c in ALLOWED_CHARSETS}


def decode_declared(payload: bytes, content_type):
    """依 Content-Type 宣告的字元集嚴格解碼；沒有宣告時用 UTF-8（容許 BOM）。
    回傳 (text, None) 或 (None, 失敗說明)。解碼失敗不會悄悄改用其他編碼：
    錯誤的解碼可能把公告時間、公司代碼、EPS 解析錯，寧可不放行。"""
    m = re.search(r"charset=[\"']?([\w.:-]+)", content_type or "", re.I)
    declared = m.group(1).lower() if m else None
    enc = declared or "utf-8"
    try:
        name = codecs.lookup(enc).name
    except LookupError:
        return None, f"不支援的字元編碼「{enc}」"
    if name not in _ALLOWED_CODEC_NAMES:
        return None, f"字元編碼「{enc}」不在允許清單 {list(ALLOWED_CHARSETS)}"
    if name == "utf-8" and payload.startswith(b"\xef\xbb\xbf"):
        payload = payload[3:]
    try:
        return payload.decode(name), None
    except UnicodeDecodeError as e:
        how = f"宣告的 {enc}" if declared else "預設的 UTF-8（未宣告字元集）"
        return None, f"以{how}嚴格解碼失敗（第 {e.start} 個位元組）"


def _norm_issuer(v):
    return None if v is None else str(v).strip().upper()


def _norm_period(v):
    return None if v is None else re.sub(r"[^0-9A-Za-z]", "", str(v)).upper()


def _first(record: dict, keys):
    for k in keys:
        if k in record and record[k] not in (None, ""):
            return record[k]
    return None


def _record_period(record: dict):
    p = _first(record, PERIOD_KEYS)
    if p is not None:
        return _norm_period(p)
    year, quarter = record.get("fiscal_year"), record.get("quarter")
    if year not in (None, "") and quarter not in (None, ""):
        q = str(quarter).strip().upper().lstrip("Q")
        return _norm_period(f"{year}Q{q}")
    return None


# ---------------------------------------------------------------- Layer1

def verify_domain_identity(source_url: str) -> str:
    """網址屬於哪種身分。只回答身分，不代表內容、時間、不可變性已驗證。"""
    domain = _domain_of(source_url)
    if _domain_matches(domain, OFFICIAL_DOMAINS):
        return "official_record"
    if _domain_matches(domain, ARCHIVE_DOMAINS):
        return "immutable_archive"
    return "unverified_link"


# ---------------------------------------------------------------- Layer2

def _has_issuer_and_period(header: set) -> bool:
    has_issuer = bool(header & set(ISSUER_KEYS))
    has_period = bool(header & set(PERIOD_KEYS)) or {"fiscal_year", "quarter"} <= header
    return has_issuer and has_period


def default_record_extractor(text: str):
    """把共識證據內容解析成紀錄列表（list[dict]）；無法結構化解析時回傳 None。
    支援 JSON（list，或含 records/data/items 陣列的物件）與帶表頭的 CSV。
    HTML 等非結構化內容回傳 None → Layer2 fail-closed；
    正式環境若要支援特定資料商的頁面，請傳入專用 record_extractor。"""
    return parse_structured_records(
        text, lambda header: _has_issuer_and_period(header) and bool(header & set(EPS_KEYS)))


def parse_structured_records(text: str, csv_header_ok):
    """共用的 JSON/CSV 結構化解析。CSV 的表頭必須通過 csv_header_ok 才接受，
    避免把 HTML 或一般文字誤當成表格。共識證據與官方公告證據共用此函式。"""
    s = text.strip()
    if not s:
        return None
    if s[0] in "[{":
        try:
            obj = json.loads(s)
        except ValueError:
            return None
        if isinstance(obj, dict):
            for k in ("records", "data", "items"):
                if isinstance(obj.get(k), list):
                    obj = obj[k]
                    break
            else:
                obj = [obj]
        if not isinstance(obj, list):
            return None
        return [r for r in obj if isinstance(r, dict)]
    try:
        rows = list(csv.DictReader(io.StringIO(s)))
    except csv.Error:
        return None
    if not rows:
        return None
    return rows if csv_header_ok(set(rows[0].keys())) else None


def _check_content(snapshot, bundle: VerifiedEvidenceBundle, extractor) -> list:
    text, err = decode_declared(bundle.content_bytes, getattr(bundle, "content_type", ""))
    if err:
        return [(RC.EVIDENCE_CONTENT_MISMATCH, f"證據內容無法解碼：{err}")]

    records = extractor(text)
    if records is None:
        return [(RC.EVIDENCE_CONTENT_MISMATCH,
                 "證據內容無法結構化解析出（公司、期間、EPS）紀錄；不以字串包含判定")]

    want_eps = _to_decimal(snapshot.consensus_eps.value if snapshot.consensus_eps else None)
    if want_eps is None:
        return [(RC.EVIDENCE_CONTENT_MISMATCH, "待驗 EPS 不是有效數值")]

    want_issuer = _norm_issuer(snapshot.ticker)
    issuer_hits = [r for r in records if want_issuer and _norm_issuer(_first(r, ISSUER_KEYS)) == want_issuer]
    if not issuer_hits:
        return [(RC.EVIDENCE_ISSUER_MISMATCH, f"證據中沒有公司代碼 {snapshot.ticker} 的紀錄")]

    want_period = _norm_period(snapshot.fiscal_quarter)
    period_hits = [r for r in issuer_hits if _record_period(r) == want_period]
    if not period_hits:
        return [(RC.EVIDENCE_PERIOD_MISMATCH,
                 f"證據中有 {snapshot.ticker} 的紀錄，但沒有 {snapshot.fiscal_quarter} 期間")]

    eps_values = {_to_decimal(_first(r, EPS_KEYS)) for r in period_hits}
    eps_values.discard(None)
    if not eps_values:
        return [(RC.EVIDENCE_CONTENT_MISMATCH, "證據中同公司同期間的紀錄沒有有效 EPS")]
    if len(eps_values) > 1:
        return [(RC.EVIDENCE_CONTENT_MISMATCH,
                 f"證據中同公司同期間出現多個不同 EPS {sorted(str(v) for v in eps_values)}，無法確認")]
    found = next(iter(eps_values))
    if found != want_eps:
        return [(RC.EVIDENCE_CONTENT_MISMATCH, f"證據 EPS {found} 與待驗 EPS {want_eps} 不符")]
    return []


# ---------------------------------------------------------------- Layer3

def _check_time(bundle: VerifiedEvidenceBundle, cutoff: dict):
    """回傳 (failures, captured_dt)。captured_dt 只有在可解析且帶時區時才非 None。
    cutoff 是 announcement_verification 查證出的官方最早揭露事件；
    這裡完全不讀 snapshot.earnings_announcement_date（adapter 提供的值）。"""
    captured_dt, precision = parse_with_precision(bundle.captured_at)
    if captured_dt is None or precision != "datetime_tz":
        return [(RC.EVIDENCE_ARCHIVE_TIMESTAMP_UNVERIFIED,
                 f"封存時間「{bundle.captured_at}」無法解析或未帶時區")], None

    fails = []
    rule = SNAPSHOT_TIME_BINDING_RULES.get(_domain_of(bundle.archive_url))
    if rule == "wayback14":
        sid = str(bundle.snapshot_id).strip()
        if not re.fullmatch(r"\d{14}", sid):
            fails.append((RC.EVIDENCE_SNAPSHOT_ID_MISMATCH, f"快照 ID「{sid}」不是 Wayback 的 14 位時間戳"))
        else:
            try:
                sid_dt = datetime.strptime(sid, "%Y%m%d%H%M%S").replace(tzinfo=dt_timezone.utc)
            except ValueError:
                sid_dt = None
            if sid_dt is None or sid_dt != captured_dt.astimezone(dt_timezone.utc):
                fails.append((RC.EVIDENCE_SNAPSHOT_ID_MISMATCH,
                              f"快照 ID 推導的時間與證據包封存時間 {bundle.captured_at} 不一致"))
    else:
        fails.append((RC.EVIDENCE_ARCHIVE_TIMESTAMP_UNVERIFIED,
                      "尚未支援此封存服務的快照時間核對規則，封存時間無法獨立確認"))

    timing = classify_timing(captured_dt, precision, cutoff["dt"], cutoff["precision"])
    official = f"官方最早揭露 {cutoff['iso']}（{cutoff.get('event_type') or '事件'}，{cutoff['document_id']}）"
    if timing == "POST":
        fails.append((RC.EVIDENCE_ARCHIVED_AFTER_EARNINGS, f"封存時間 {bundle.captured_at} 晚於{official}"))
    elif timing != "PRE":
        fails.append((RC.EVIDENCE_ARCHIVE_TIMESTAMP_UNVERIFIED,
                      f"封存時間 {bundle.captured_at} 與{official}的時間區間重疊，精度不足以確認在公告之前"))
    return fails, captured_dt


# ---------------------------------------------------------------- Layer4

def _check_immutability(bundle: VerifiedEvidenceBundle, requested_url: str):
    """回傳 (failures, recomputed_sha256)。"""
    fails = []
    archive_host = _domain_of(bundle.archive_url)
    if not _domain_matches(archive_host, ARCHIVE_DOMAINS) or archive_host == _domain_of(requested_url):
        fails.append((RC.EVIDENCE_SOURCE_NOT_INDEPENDENT,
                      f"封存網址「{archive_host}」不是獨立的封存服務"))

    if bundle.source_url.strip() != requested_url.strip():
        fails.append((RC.EVIDENCE_SNAPSHOT_ID_MISMATCH, "證據包的原始網址與請求查證的網址不同"))
    # 封存網址必須是「.../{快照ID}[旗標_]/{請求的原始網址}」，且快照ID之後的部分要完全相同；
    # 不用字串包含，避免指向「原始網址-evil」這類前綴相同的另一頁也被放行。
    # （正式環境的 WebArchiveVerifier 應自行用請求網址組出 archive_url，才能保證完全一致。）
    sid = str(bundle.snapshot_id).strip()
    m = re.search(r"/" + re.escape(sid) + r"(?:[a-z]{1,3}_)?/(.+)$", bundle.archive_url)
    if m is None:
        fails.append((RC.EVIDENCE_SNAPSHOT_ID_MISMATCH, "封存網址中找不到該快照 ID，無法確認是同一版本"))
    elif m.group(1) != requested_url.strip():
        fails.append((RC.EVIDENCE_SNAPSHOT_ID_MISMATCH, "封存網址指向的原始網址與請求查證的網址不同"))

    recomputed = hashlib.sha256(bundle.content_bytes).hexdigest()
    reported = _strip_hash_prefix(bundle.sha256)
    if str(bundle.hash_algorithm).strip().lower() != "sha256" or not _HEX64.fullmatch(reported):
        fails.append((RC.EVIDENCE_HASH_ALGORITHM_UNSUPPORTED,
                      f"雜湊演算法或格式不支援（{bundle.hash_algorithm}），僅接受 64 位十六進位 SHA-256"))
    elif reported != recomputed:
        fails.append((RC.EVIDENCE_HASH_MISMATCH, "由原始位元組重算的 SHA-256 與證據包回報值不一致"))

    if fails:
        fails.append((RC.EVIDENCE_IMMUTABILITY_UNPROVEN, "無法證明內容在封存後未被修改"))
    return fails, recomputed


# ---------------------------------------------------------------- 稽核（不影響判定）

CLAIMED_SNAPSHOT_TOLERANCE_HOURS = 24


def _audit_claims(snapshot, recomputed_sha, captured_dt, cutoff=None) -> list:
    """adapter 聲稱值與獨立證據的比對，只產生稽核代碼，不影響判定。"""
    audits = []
    claimed_snap = getattr(getattr(snapshot, "snapshot_date", None), "value", None)
    s_dt, s_prec = parse_with_precision(claimed_snap)
    if captured_dt is not None and s_dt is not None and s_prec == "datetime_tz":
        gap_h = abs((s_dt - captured_dt).total_seconds()) / 3600
        if gap_h > CLAIMED_SNAPSHOT_TOLERANCE_HOURS:
            audits.append((RC.CLAIMED_TIMING_INCONSISTENT,
                           f"adapter 聲稱的快照時間 {claimed_snap} 與封存時間相差 {gap_h:.1f} 小時"))

    claimed_earn = getattr(getattr(snapshot, "earnings_announcement_date", None), "value", None)
    if cutoff is not None and claimed_earn is not None:
        e_dt, e_prec = parse_with_precision(claimed_earn)
        if e_dt is None:
            audits.append((RC.CLAIMED_ANNOUNCEMENT_TIME_MISMATCH,
                           f"adapter 聲稱的公告時間「{claimed_earn}」無法解析"))
        else:
            # 比較時間區間而非單點：只有日期的公告與同日的精確時間不算不一致
            c_early, c_late = to_utc_interval(e_dt, e_prec)
            o_early, o_late = to_utc_interval(cutoff["dt"], cutoff["precision"])
            if c_early > o_late:
                audits.append((RC.CLAIMED_ANNOUNCEMENT_TIME_MISMATCH,
                               f"adapter 聲稱的公告時間 {claimed_earn} 晚於官方最早揭露 {cutoff['iso']}"
                               f"（若採信聲稱值，財報後的資料可能被當成財報前）"))
            elif c_late < o_early:
                audits.append((RC.CLAIMED_ANNOUNCEMENT_TIME_MISMATCH,
                               f"adapter 聲稱的公告時間 {claimed_earn} 早於官方最早揭露 {cutoff['iso']}"))
    claimed_hash = getattr(snapshot, "claimed_content_hash", None)
    if claimed_hash and _strip_hash_prefix(claimed_hash) != recomputed_sha:
        audits.append((RC.CLAIMED_HASH_MISMATCH, "adapter 聲稱的雜湊與證據包重算結果不一致"))
    claimed_ts = getattr(getattr(snapshot, "claimed_archive_timestamp", None), "value", None)
    if claimed_ts is not None and captured_dt is not None:
        c_dt, c_prec = parse_with_precision(claimed_ts)
        if c_dt is None or c_prec != "datetime_tz" or c_dt != captured_dt:
            audits.append((RC.CLAIMED_HASH_MISMATCH, "adapter 聲稱的封存時間與證據包封存時間不一致"))
    return audits


def _missing_fields(bundle) -> list:
    missing = []
    for f in REQUIRED_BUNDLE_FIELDS:
        v = getattr(bundle, f, None)
        if f == "content_bytes":
            if not isinstance(v, (bytes, bytearray)) or len(v) == 0:
                missing.append(f)
        elif v is None or str(v).strip() == "":
            missing.append(f)
    return missing


# ---------------------------------------------------------------- 總入口

def verify_pre_earnings_evidence(snapshot, verifier: IndependentVerifier = None, record_extractor=None,
                                 announcement: dict = None) -> dict:
    """Gate5B 來源驗證總入口。每次都重新計算，並強制覆寫
    provenance.verified_evidence_tier（外部預先寫入的值一律無效）。

    announcement：announcement_verification.verify_earnings_announcement() 的結果。
    沒有傳入、或官方公告查證未成功時，不取封存證據包，直接 fail-closed。

    回傳：
      domain_identity / content_correspondence / timestamp_confirmation / immutability_proof
      final_tier   只有四層全過才是 official_record，否則 unverified_link
      failures     [(reject_code, message)]，判定失敗原因
      audits       [(reject_code, message)]，claimed 與證據不一致的稽核訊號（不影響判定）
      trace        可追溯紀錄：快照 ID、封存網址、封存時間、回報與重算雜湊、驗證器呼叫次數
    """
    verifier = verifier or NullIndependentVerifier()
    extractor = record_extractor or default_record_extractor
    prov = snapshot.snapshot_date.provenance
    requested_url = prov.source_url or ""

    result = {
        "domain_identity": verify_domain_identity(requested_url),
        "announcement_verified": False,
        "content_correspondence": False,
        "timestamp_confirmation": False,
        "immutability_proof": False,
        "final_tier": "unverified_link",
        "failures": [],
        "audits": [],
        "trace": {"requested_url": requested_url, "verifier_calls": 0},
    }

    def _finish():
        layer1_ok = result["domain_identity"] == "official_record"
        all_pass = (layer1_ok and result["announcement_verified"] and result["content_correspondence"]
                    and result["timestamp_confirmation"] and result["immutability_proof"])
        result["final_tier"] = result["domain_identity"] if all_pass else "unverified_link"
        prov.verified_evidence_tier = result["final_tier"]  # 強制覆寫，封閉注入
        result["trace"]["failure_codes"] = [c for c, _ in result["failures"]]
        return result

    # Layer1 不過就不發出網路查證（正式環境省一次外部呼叫），直接 fail-closed
    if result["domain_identity"] != "official_record":
        return _finish()

    # 官方公告時間沒有查證成功，就沒有可信的截止點，不取證據包、直接 fail-closed
    if announcement is None:
        result["failures"].append((RC.ANNOUNCEMENT_EVIDENCE_UNAVAILABLE, "未提供官方公告查證結果"))
        return _finish()
    result["trace"]["announcement"] = announcement.get("trace", {})
    if not announcement.get("ok") or not announcement.get("cutoff"):
        result["failures"].extend(announcement.get("failures") or
                                  [(RC.ANNOUNCEMENT_EVIDENCE_UNAVAILABLE, "官方公告查證未成功")])
        return _finish()
    cutoff = announcement["cutoff"]
    result["announcement_verified"] = True

    # 只請驗證器找「官方最早揭露時間之前」的封存版本（截止點來自官方，不是 adapter）
    captured_before = to_utc_interval(cutoff["dt"], cutoff["precision"])[0]
    result["trace"]["captured_before"] = captured_before.isoformat()
    try:
        result["trace"]["verifier_calls"] = 1
        bundle = verifier.fetch_verified_bundle(requested_url, captured_before=captured_before)
    except Exception as e:
        code = getattr(e, "reject_code", None)
        if code not in VERIFIER_FAULT_CODES:
            code = RC.EVIDENCE_VERIFIER_ERROR
        result["failures"].append((code, f"驗證器回報失敗：{type(e).__name__}: {e}"))
        return _finish()

    if bundle is None:
        result["failures"].append((RC.EVIDENCE_BUNDLE_UNAVAILABLE, "無法取得獨立證據包"))
        return _finish()
    if not isinstance(bundle, VerifiedEvidenceBundle):
        result["failures"].append((RC.EVIDENCE_VERIFIER_ERROR, f"驗證器回傳非預期型別 {type(bundle).__name__}"))
        return _finish()
    missing = _missing_fields(bundle)
    if missing:
        result["failures"].append((RC.EVIDENCE_BUNDLE_INCOMPLETE, f"證據包缺少必要欄位：{', '.join(missing)}"))
        return _finish()

    try:
        content_fails = _check_content(snapshot, bundle, extractor)
        time_fails, captured_dt = _check_time(bundle, cutoff)
        immut_fails, recomputed = _check_immutability(bundle, requested_url)
    except Exception as e:
        result["failures"].append((RC.EVIDENCE_VERIFIER_ERROR, f"驗證檢查過程發生錯誤：{type(e).__name__}: {e}"))
        return _finish()

    # 稽核與判定隔離：adapter 欄位就算型別錯誤讓稽核出錯，也只記一筆稽核，不能變成拒絕理由
    try:
        audits = _audit_claims(snapshot, recomputed, captured_dt, cutoff)
    except Exception as e:
        audits = [(RC.CLAIMED_TIMING_INCONSISTENT, f"adapter 欄位稽核時發生錯誤：{type(e).__name__}")]

    result["content_correspondence"] = not content_fails
    result["timestamp_confirmation"] = not time_fails
    result["immutability_proof"] = not immut_fails
    result["failures"] = content_fails + time_fails + immut_fails
    result["audits"] = audits
    result["trace"].update({
        "snapshot_id": bundle.snapshot_id,
        "archive_url": bundle.archive_url,
        "captured_at": bundle.captured_at,
        "sha256_reported": _strip_hash_prefix(bundle.sha256),
        "sha256_recomputed": recomputed,
        "verifier_reported_status": bundle.verification_status,
        # 兩種完整性證據分開呈現，避免把「與封存索引摘要一致」誤讀成「歷史內容未遭竄改的獨立證明」
        "integrity": {
            "content_sha256_recomputed": recomputed,
            "archive_capture_digest": {
                "algorithm": getattr(bundle, "archive_digest_algorithm", "") or None,
                "value": getattr(bundle, "archive_digest", "") or None,
                "matched_served_bytes": getattr(bundle, "archive_digest_matched", None),
            },
            "independent_history_proof": False,
            "meaning": ("封存索引摘要相符＝現在取得的位元組與封存服務在擷取當下記錄的一致；"
                        "SHA-256＝本系統持有的位元組。兩者都不能獨立證明封存服務本身未修改歷史內容。"),
        },
        "retrieval": getattr(bundle, "retrieval_trace", None),
    })
    return _finish()


def tier_was_overstated(provenance, independently_verified_tier: str) -> bool:
    """稽核用：來源宣告的等級是否高於獨立判定結果。"""
    rank = {"official_record": 3, "immutable_archive": 2, "unverified_link": 1, None: 0}
    return rank.get(provenance.claimed_evidence_tier, 0) > rank.get(independently_verified_tier, 0)
