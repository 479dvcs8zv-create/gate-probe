"""
announcement_verification.py (v4.7)
====================================
Gate5B 的「財報公告時間」獨立查證。

截止點規則（v4.4 起）：
  - 公告時間由獨立的 AnnouncementVerifier 向官方來源查詢，不用 adapter 提供的時間。
  - 公司、期間、公告時間一律從官方文件原始位元組解析，SHA-256 由位元組重算。
  - 截止點取「最早」的財務結果揭露（自結損益、董事會通過財報、財報申報、法說會），
    市場最早得知結果之後的共識都不算財報前。
  - 任何一份公告文件驗證失敗，整個期間 fail-closed（無法排除它就是最早的揭露）。
  - 只有日期的公告用保守區間（當天最早可能時刻）。
  - 更正公告必須連同原始公告回傳，截止點以原始公告為準（v4.6）。

v4.7：完整性改由「實際查詢證據」證明，不再相信驗證器的宣告
  v4.6 要求驗證器宣告 coverage_start / searched_event_types，但「宣告查過四類」不等於
  「實際完整查過四類」。v4.7 起驗證器必須附上每一頁官方查詢回應的原始位元組
  （AnnouncementQueryRecord），程式自行：
    - 重算每頁回應的 SHA-256，並確認請求網址是官方網域
    - 從官方回應本身解析查詢範圍、頁碼、總頁數、總筆數、列出的公告與時間
    - 逐類核對：四類事件都要有實際查詢；頁碼 1..N 齊全；各頁合計筆數 = 回應宣稱總數；
      回應標示截斷即不放行；查詢範圍起點不晚於期間第一天、終點不早於截止點
    - 官方清單列出的每一份公告，驗證器都必須提供原文（否則就是漏抓，可能漏掉最早的揭露）；
      驗證器提供的每一份公告，都必須出現在官方清單中；清單時間必須等於原文時間
  驗證器原本宣告的欄位只記錄在軌跡中，不參與判定。

這仍不是「獨立證明」（誠實版）：
  查詢紀錄由驗證器產生。它能抓出最常見的實作錯誤（漏頁、截斷、漏文件、時間不一致），
  也讓每一次判定可被稽核與重播（請求網址＋原始回應雜湊都在軌跡中）；但一個刻意造假、
  讓清單與文件彼此一致的驗證器仍無法由本程式識破。要排除這種情況，需要另一個獨立執行
  環境重播同樣的查詢並比對列出的公告（例如 GitHub Actions 與 Worker 各跑一次）。

仍需在正式環境驗收：
  - MopsAnnouncementVerifier 尚未接上真實網路（本環境連公開資訊觀測站被代理拒絕）。
  - 公開資訊觀測站的實際回應是 HTML，需依實際錄製的回應撰寫 listing_extractor 與
    record_extractor，並以已知案例（含自結損益、含更正公告）回歸測試。
"""

import hashlib
import json
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional

from evidence_verification import (
    OFFICIAL_DOMAINS, ISSUER_KEYS, _HEX64,
    _domain_of, _domain_matches, _first, _has_issuer_and_period,
    _norm_issuer, _norm_period, _record_period, _strip_hash_prefix,
    decode_declared, parse_structured_records,
)
from reject_codes import RC
from time_utils import parse_with_precision, to_utc_interval

ANNOUNCED_AT_KEYS = ("announced_at", "announcement_time", "disclosed_at")
EVENT_TYPE_KEYS = ("event_type", "type")
CORRECTION_FLAG_KEYS = ("is_correction",)
CORRECTS_KEYS = ("corrects_document_id",)

REQUIRED_EVIDENCE_FIELDS = ("source_url", "document_id", "content_bytes", "sha256", "hash_algorithm")
REQUIRED_QUERY_FIELDS = ("event_type", "request_url", "page", "response_bytes", "response_sha256", "hash_algorithm")
LISTING_REQUIRED_KEYS = ("event_type", "ticker", "range_start", "range_end", "page", "total_pages",
                         "total_count", "items")

# 每一類都必須有實際查詢證據；漏掉任何一類都可能漏掉較早的揭露。
REQUIRED_QUERY_EVENT_TYPES = frozenset({
    "self_reported_results",       # 自結損益
    "board_approved_financials",   # 董事會通過財報
    "financial_report",            # 財報申報
    "investor_conference",         # 法說會
})
REQUIRED_SEARCHED_EVENT_TYPES = REQUIRED_QUERY_EVENT_TYPES  # v4.6 名稱，保留相容


@dataclass
class AnnouncementEvidence:
    """一份官方公告的原始文件。判定只依據 content_bytes 解析出的內容。"""
    source_url: str
    document_id: str
    content_bytes: bytes
    sha256: str
    hash_algorithm: str = "sha256"
    retrieved_at: str = ""
    content_type: str = ""   # 官方回應的 Content-Type（含 charset），v4.8 起依宣告字元集解碼


@dataclass
class AnnouncementQueryRecord:
    """一次實際對官方來源發出的查詢（一頁）與它的原始回應。"""
    event_type: str          # 這次查詢針對的事件類型
    request_url: str         # 實際請求網址（含查詢參數），必須是官方網域；供重播稽核
    page: int                # 第幾頁（1 起算）
    response_bytes: bytes    # 官方回應原始位元組
    response_sha256: str     # 回報雜湊，一律由 response_bytes 重算
    hash_algorithm: str = "sha256"
    retrieved_at: str = ""
    content_type: str = ""   # 官方回應的 Content-Type（含 charset），v4.8 起依宣告字元集解碼


@dataclass
class AnnouncementQueryResult:
    """一次官方公告查證的完整結果：所有查詢頁的原始回應＋清單列出的公告原文。"""
    documents: List[AnnouncementEvidence]
    queries: List[AnnouncementQueryRecord] = field(default_factory=list)
    # 以下為驗證器自行宣告的欄位。v4.7 起只記錄在軌跡中，不參與判定。
    coverage_start: Optional[str] = None
    coverage_end: Optional[str] = None
    searched_event_types: Optional[List[str]] = None
    sources: Optional[List[str]] = None


class AnnouncementVerifier(ABC):
    @abstractmethod
    def fetch_announcement_evidence(self, ticker: str, fiscal_quarter: str) -> Optional[AnnouncementQueryResult]:
        """回傳每一類事件的所有查詢頁原始回應，以及清單列出的每一份公告原文。
        None 代表無法查證，會 fail-closed。"""
        raise NotImplementedError


class NullAnnouncementVerifier(AnnouncementVerifier):
    """沒有網路存取能力的環境：誠實回傳 None，Gate5B 永遠不會判定通過。"""

    def fetch_announcement_evidence(self, ticker, fiscal_quarter):
        return None


class MopsAnnouncementVerifier(AnnouncementVerifier):
    """正式環境骨架（尚未實作網路呼叫，刻意不回傳假資料）。

    為什麼仍不寫解析程式：本環境連不到公開資訊觀測站（代理 403），看不到目前實際的
    查詢端點與回應格式。照記憶寫的解析器若漏抓較早的公告，截止點會被高估。
    請先在可連網的環境（例如 ops/network_probe.py 搭配 GitHub Actions）錄下實際回應，
    再依錄製檔實作並回歸測試。

    實作必須符合（程式會核對，不符合即 fail-closed）：
      1. 四類事件各自查詢，每一頁都保存 AnnouncementQueryRecord（請求網址、頁碼、原始回應、SHA-256）。
         查詢範圍起點不晚於期間第一天、終點晚於最早事件；頁碼必須 1..N 齊全。
      2. 提供 listing_extractor，從官方回應解析出 event_type、ticker、range_start、range_end、
         page、total_pages、total_count、items[{document_id, fiscal_quarter, announced_at}]；
         官方回應若沒有回顯範圍，可由 request_url 的查詢參數取得。回應若顯示結果被截斷，標 truncated=true。
      3. 官方清單列出的每一份公告都要附原文（AnnouncementEvidence），並提供 record_extractor 解析原文。
      4. 更正公告標 is_correction=true 並附 corrects_document_id，原始公告必須一起回傳。
      5. announced_at 用官方「發言日期＋發言時間」並附 +08:00。
    """

    def fetch_announcement_evidence(self, ticker, fiscal_quarter):
        raise NotImplementedError("MopsAnnouncementVerifier 尚未接上真正的網路呼叫")


# ---------------------------------------------------------------- 解析器

def default_announcement_extractor(text: str):
    """公告原文的預設解析器：JSON 或帶表頭的 CSV，表頭需含公司、期間、公告時間。"""
    return parse_structured_records(
        text, lambda header: _has_issuer_and_period(header) and bool(header & set(ANNOUNCED_AT_KEYS)))


def default_listing_extractor(request_url: str, response_text: str):
    """官方查詢回應（清單頁）的預設解析器：JSON 物件且含 LISTING_REQUIRED_KEYS，可選 truncated。
    公開資訊觀測站的實際回應是 HTML，正式環境必須提供專用 listing_extractor。"""
    try:
        obj = json.loads(response_text)
    except ValueError:
        return None
    if not isinstance(obj, dict) or any(k not in obj for k in LISTING_REQUIRED_KEYS):
        return None
    if not isinstance(obj["items"], list):
        return None
    return obj


# ---------------------------------------------------------------- 小工具

def _missing_fields(obj, required) -> list:
    missing = []
    for f in required:
        v = getattr(obj, f, None)
        if f in ("content_bytes", "response_bytes"):
            if not isinstance(v, (bytes, bytearray)) or len(v) == 0:
                missing.append(f)
        elif v is None or str(v).strip() == "":
            missing.append(f)
    return missing


def _check_hash(algorithm, reported_raw, payload: bytes, what: str):
    recomputed = hashlib.sha256(payload).hexdigest()
    reported = _strip_hash_prefix(reported_raw)
    if str(algorithm).strip().lower() != "sha256" or not _HEX64.fullmatch(reported):
        return [(RC.ANNOUNCEMENT_HASH_ALGORITHM_UNSUPPORTED,
                 f"{what}的雜湊演算法或格式不支援（{algorithm}），僅接受 64 位十六進位 SHA-256")], recomputed
    if reported != recomputed:
        return [(RC.ANNOUNCEMENT_HASH_MISMATCH, f"由{what}原始位元組重算的 SHA-256 與回報值不一致")], recomputed
    return [], recomputed


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _period_start(fiscal_quarter: str):
    m = re.fullmatch(r"(\d{4})Q([1-4])", _norm_period(fiscal_quarter) or "")
    if not m:
        return None
    return date(int(m.group(1)), 3 * (int(m.group(2)) - 1) + 1, 1)


def _same_time(a, b) -> bool:
    (adt, ap), (bdt, bp) = a, b
    return adt is not None and bdt is not None and ap == bp and adt == bdt


# ---------------------------------------------------------------- 公告原文

def _check_document(ev: AnnouncementEvidence, ticker: str, fiscal_quarter: str, extractor):
    """驗證一份公告原文，回傳 (failures, events, recomputed_sha)。"""
    fails, events = [], []
    if not _domain_matches(_domain_of(ev.source_url), OFFICIAL_DOMAINS):
        fails.append((RC.ANNOUNCEMENT_SOURCE_NOT_OFFICIAL, f"公告來源「{_domain_of(ev.source_url)}」不是官方網域"))
    hash_fails, recomputed = _check_hash(ev.hash_algorithm, ev.sha256, ev.content_bytes, "公告")
    fails.extend(hash_fails)

    text, err = decode_declared(ev.content_bytes, getattr(ev, "content_type", ""))
    if err:
        fails.append((RC.ANNOUNCEMENT_CONTENT_MISMATCH, f"公告原文無法解碼：{err}"))
        return fails, events, recomputed
    records = extractor(text)
    if records is None:
        fails.append((RC.ANNOUNCEMENT_CONTENT_MISMATCH, "公告原文無法結構化解析出（公司、期間、公告時間）紀錄"))
        return fails, events, recomputed

    want_issuer = _norm_issuer(ticker)
    issuer_hits = [r for r in records if want_issuer and _norm_issuer(_first(r, ISSUER_KEYS)) == want_issuer]
    if not issuer_hits:
        fails.append((RC.ANNOUNCEMENT_ISSUER_MISMATCH, f"公告中沒有公司代碼 {ticker} 的事件"))
        return fails, events, recomputed
    period_hits = [r for r in issuer_hits if _record_period(r) == _norm_period(fiscal_quarter)]
    if not period_hits:
        fails.append((RC.ANNOUNCEMENT_PERIOD_MISMATCH, f"公告中有 {ticker} 的事件，但不屬於 {fiscal_quarter}"))
        return fails, events, recomputed

    for r in period_hits:
        raw_time = _first(r, ANNOUNCED_AT_KEYS)
        dt, precision = parse_with_precision(raw_time)
        if dt is None:
            fails.append((RC.ANNOUNCEMENT_TIME_UNVERIFIED, f"公告時間「{raw_time}」無法解析"))
            continue
        flag = _first(r, CORRECTION_FLAG_KEYS)
        events.append({"dt": dt, "precision": precision, "iso": str(raw_time),
                       "event_type": _first(r, EVENT_TYPE_KEYS), "document_id": ev.document_id,
                       "source_url": ev.source_url,
                       "is_correction": flag is True or str(flag).strip().lower() in ("true", "1", "yes"),
                       "corrects_document_id": _first(r, CORRECTS_KEYS)})
    return fails, events, recomputed


# ---------------------------------------------------------------- 查詢證據

def _check_queries(queries, ticker: str, fiscal_quarter: str, listing_extractor):
    """從每一頁官方回應本身推導涵蓋範圍與清單。
    回傳 (failures, listed_items, coverage_by_type, query_trace)。
    listed_items: [{event_type, document_id, fiscal_quarter, announced_at}]（所有期間，之後再篩）"""
    fails, listed, coverage, trace = [], [], {}, []
    if not queries:
        return [(RC.ANNOUNCEMENT_COVERAGE_INCOMPLETE,
                 "沒有附上實際查詢紀錄（只有宣告不算），無法證明四類事件都已查詢")], listed, coverage, trace
    period_start = _period_start(fiscal_quarter)
    if period_start is None:
        return [(RC.ANNOUNCEMENT_COVERAGE_INCOMPLETE,
                 f"無法從「{fiscal_quarter}」判斷期間起始日，無法核對查詢範圍")], listed, coverage, trace

    pages_by_type = defaultdict(list)
    for i, q in enumerate(queries):
        label = f"查詢 {getattr(q, 'event_type', '?')} 第{getattr(q, 'page', '?')}頁"
        if not isinstance(q, AnnouncementQueryRecord):
            fails.append((RC.ANNOUNCEMENT_VERIFIER_ERROR, f"查詢紀錄 #{i + 1} 是非預期型別 {type(q).__name__}"))
            continue
        missing = _missing_fields(q, REQUIRED_QUERY_FIELDS)
        if missing:
            fails.append((RC.ANNOUNCEMENT_EVIDENCE_INCOMPLETE, f"{label}缺少必要欄位：{', '.join(missing)}"))
            continue
        q_fails = []
        if not _domain_matches(_domain_of(q.request_url), OFFICIAL_DOMAINS):
            q_fails.append((RC.ANNOUNCEMENT_SOURCE_NOT_OFFICIAL, f"{label}的請求網址不是官方網域"))
        hash_fails, recomputed = _check_hash(q.hash_algorithm, q.response_sha256, q.response_bytes, f"{label}回應")
        q_fails.extend(hash_fails)
        listing = None
        text, err = decode_declared(q.response_bytes, getattr(q, "content_type", ""))
        if err:
            q_fails.append((RC.ANNOUNCEMENT_CONTENT_MISMATCH, f"{label}的官方回應無法解碼：{err}"))
        else:
            listing = listing_extractor(q.request_url, text)
            if listing is None:
                q_fails.append((RC.ANNOUNCEMENT_CONTENT_MISMATCH, f"{label}的官方回應無法解析出查詢清單"))
        if listing is not None:
            if listing["event_type"] != q.event_type:
                q_fails.append((RC.ANNOUNCEMENT_CONTENT_MISMATCH,
                                f"{label}：回應內容的事件類型「{listing['event_type']}」與查詢紀錄不符"))
            if _norm_issuer(listing["ticker"]) != _norm_issuer(ticker):
                q_fails.append((RC.ANNOUNCEMENT_ISSUER_MISMATCH, f"{label}：回應查詢的公司是「{listing['ticker']}」"))
            if not all(_is_int(listing[k]) for k in ("page", "total_pages", "total_count")) or listing["page"] != q.page:
                q_fails.append((RC.ANNOUNCEMENT_PAGINATION_INCOMPLETE, f"{label}：回應的頁碼或總數不是有效整數，或與紀錄不符"))
            if listing.get("truncated") is True:
                q_fails.append((RC.ANNOUNCEMENT_PAGINATION_INCOMPLETE, f"{label}：官方回應標示結果被截斷"))
        fails.extend(q_fails)
        trace.append({"event_type": q.event_type, "page": q.page, "request_url": q.request_url,
                      "response_sha256_recomputed": recomputed,
                      "listed_document_ids": [it.get("document_id") for it in (listing or {}).get("items", [])
                                              if isinstance(it, dict)],
                      "failure_codes": [c for c, _ in q_fails]})
        if listing is not None and not q_fails:
            pages_by_type[q.event_type].append(listing)

    for t in sorted(REQUIRED_QUERY_EVENT_TYPES | set(pages_by_type)):
        pages = pages_by_type.get(t)
        if not pages:
            if t in REQUIRED_QUERY_EVENT_TYPES:
                fails.append((RC.ANNOUNCEMENT_COVERAGE_INCOMPLETE, f"沒有「{t}」的有效實際查詢紀錄"))
            continue
        meta = {(p["total_pages"], p["total_count"], p["range_start"], p["range_end"]) for p in pages}
        if len(meta) != 1:
            fails.append((RC.ANNOUNCEMENT_PAGINATION_INCOMPLETE,
                          f"「{t}」各頁回報的總頁數、總筆數或查詢範圍不一致，可能混入不同次查詢"))
            continue
        total_pages, total_count, range_start, range_end = meta.pop()
        got = sorted(p["page"] for p in pages)
        if got != list(range(1, total_pages + 1)):
            fails.append((RC.ANNOUNCEMENT_PAGINATION_INCOMPLETE, f"「{t}」取得頁碼 {got}，應為 1..{total_pages}"))
        n_items = sum(len(p["items"]) for p in pages)
        if n_items != total_count:
            fails.append((RC.ANNOUNCEMENT_PAGINATION_INCOMPLETE,
                          f"「{t}」各頁合計 {n_items} 筆，官方回應宣稱共 {total_count} 筆"))
        rs, rs_prec = parse_with_precision(range_start)
        re_, re_prec = parse_with_precision(range_end)
        if rs is None or re_ is None:
            fails.append((RC.ANNOUNCEMENT_COVERAGE_INCOMPLETE, f"「{t}」查詢範圍「{range_start}」～「{range_end}」無法解析"))
            continue
        if rs.date() > period_start:
            fails.append((RC.ANNOUNCEMENT_COVERAGE_INCOMPLETE,
                          f"「{t}」查詢起點 {range_start} 晚於期間第一天 {period_start.isoformat()}，可能漏掉較早的揭露"))
        coverage[t] = (re_, re_prec, range_end)
        for p in pages:
            for it in p["items"]:
                listed.append({"event_type": t, **(it if isinstance(it, dict) else {"_invalid": it})})
    return fails, listed, coverage, trace


# ---------------------------------------------------------------- 總入口

def verify_earnings_announcement(ticker: str, fiscal_quarter: str, verifier: AnnouncementVerifier = None,
                                 record_extractor=None, listing_extractor=None) -> dict:
    """查證某公司某期間的官方最早財務結果揭露時間。

    回傳：
      ok        True 才能用 cutoff 判定封存是否在公告前
      cutoff    {"dt", "precision", "iso", "event_type", "document_id", "source_url"}，取最早事件
      failures  [(reject_code, message)]，任何一項失敗即整體 fail-closed
      trace     每一頁查詢（請求網址、重算雜湊、列出的公告）、每份原文、截止點、驗證器宣告（僅記錄）
    """
    verifier = verifier or NullAnnouncementVerifier()
    doc_extractor = record_extractor or default_announcement_extractor
    listing_extractor = listing_extractor or default_listing_extractor
    result = {"ok": False, "cutoff": None, "failures": [],
              "trace": {"ticker": ticker, "fiscal_quarter": fiscal_quarter, "verifier_calls": 1,
                        "queries": [], "documents": []}}

    try:
        items = verifier.fetch_announcement_evidence(ticker, fiscal_quarter)
    except Exception as e:
        result["failures"].append((RC.ANNOUNCEMENT_VERIFIER_ERROR, f"公告驗證器執行錯誤：{type(e).__name__}: {e}"))
        return result
    if items is None:
        result["failures"].append((RC.ANNOUNCEMENT_EVIDENCE_UNAVAILABLE, "無法取得官方公告事件證據"))
        return result
    if isinstance(items, (list, tuple)):
        result["failures"].append((RC.ANNOUNCEMENT_COVERAGE_INCOMPLETE,
                                   "驗證器只回傳文件清單、沒有附實際查詢紀錄，無法排除漏抓較早的揭露"))
        return result
    if not isinstance(items, AnnouncementQueryResult) or not isinstance(items.documents, (list, tuple)):
        result["failures"].append((RC.ANNOUNCEMENT_VERIFIER_ERROR, f"公告驗證器回傳非預期型別 {type(items).__name__}"))
        return result
    query = items
    result["trace"]["declared_by_verifier"] = {  # 只記錄，不參與判定
        "coverage_start": query.coverage_start, "coverage_end": query.coverage_end,
        "searched_event_types": sorted(query.searched_event_types or []), "sources": list(query.sources or [])}

    try:
        q_fails, listed, coverage, q_trace = _check_queries(query.queries, ticker, fiscal_quarter, listing_extractor)
        result["failures"].extend(q_fails)
        result["trace"]["queries"] = q_trace

        candidates, returned = [], {}
        for i, ev in enumerate(query.documents):
            label = getattr(ev, "document_id", None) or f"#{i + 1}"
            if not isinstance(ev, AnnouncementEvidence):
                result["failures"].append((RC.ANNOUNCEMENT_VERIFIER_ERROR,
                                           f"公告文件 {label} 是非預期型別 {type(ev).__name__}"))
                continue
            missing = _missing_fields(ev, REQUIRED_EVIDENCE_FIELDS)
            if missing:
                result["failures"].append((RC.ANNOUNCEMENT_EVIDENCE_INCOMPLETE,
                                           f"公告文件 {label} 缺少必要欄位：{', '.join(missing)}"))
                returned[ev.document_id] = []
                continue
            fails, events, recomputed = _check_document(ev, ticker, fiscal_quarter, doc_extractor)
            result["failures"].extend((code, f"公告文件 {label}：{msg}") for code, msg in fails)
            candidates.extend(events)
            returned[ev.document_id] = events
            result["trace"]["documents"].append({
                "document_id": ev.document_id, "source_url": ev.source_url, "sha256_recomputed": recomputed,
                "event_times": [e["iso"] for e in events], "failure_codes": [c for c, _ in fails]})

        # 官方清單 ↔ 原文互相核對（只在查詢證據本身有效時進行，避免重複報同一個問題）
        if not q_fails:
            want_period = _norm_period(fiscal_quarter)
            listed_ids = set()
            for it in listed:
                doc_id = it.get("document_id")
                if not doc_id or it.get("fiscal_quarter") in (None, ""):
                    result["failures"].append((RC.ANNOUNCEMENT_CONTENT_MISMATCH,
                                               f"「{it['event_type']}」清單項目缺公告識別碼或期間：{it}"))
                    continue
                listed_ids.add(doc_id)
                if _norm_period(it["fiscal_quarter"]) != want_period:
                    continue
                listed_time = parse_with_precision(it.get("announced_at"))
                if listed_time[0] is None:
                    result["failures"].append((RC.ANNOUNCEMENT_TIME_UNVERIFIED,
                                               f"官方清單中公告 {doc_id} 的時間缺漏或無法解析：「{it.get('announced_at')}」"))
                if doc_id not in returned:
                    result["failures"].append((RC.ANNOUNCEMENT_LISTED_DOCUMENT_MISSING,
                                               f"官方「{it['event_type']}」清單列出公告 {doc_id}（{it.get('announced_at')}），"
                                               f"但驗證器沒有提供原文"))
                elif listed_time[0] is not None and returned[doc_id] and not any(
                        _same_time(listed_time, (e["dt"], e["precision"])) for e in returned[doc_id]):
                    result["failures"].append((RC.ANNOUNCEMENT_CONTENT_MISMATCH,
                                               f"公告 {doc_id} 的清單時間「{it.get('announced_at')}」與原文時間不一致"))
            for doc_id in returned:
                if doc_id not in listed_ids:
                    result["failures"].append((RC.ANNOUNCEMENT_DOCUMENT_NOT_LISTED,
                                               f"公告 {doc_id} 不在任何官方查詢清單中，無法追溯來源"))
    except Exception as e:
        result["failures"].append((RC.ANNOUNCEMENT_VERIFIER_ERROR, f"公告驗證過程發生錯誤：{type(e).__name__}: {e}"))
        return result

    # 更正公告必須連同被更正的原始公告一起回傳
    for e in candidates:
        if e["is_correction"] and (not e["corrects_document_id"] or e["corrects_document_id"] not in returned):
            result["failures"].append((RC.ANNOUNCEMENT_CORRECTION_ORIGINAL_MISSING,
                                       f"公告文件 {e['document_id']} 是更正公告，但被更正的原始公告"
                                       f"「{e['corrects_document_id'] or '未註明'}」沒有一起回傳"))

    if result["failures"]:
        return result  # 任何一項失敗都無法排除漏掉最早的揭露，整體 fail-closed
    if not candidates:
        result["failures"].append((RC.ANNOUNCEMENT_EVIDENCE_UNAVAILABLE,
                                   f"查無 {ticker} {fiscal_quarter} 的官方公告事件，無法確認公告時間"))
        return result

    cutoff = min(candidates, key=lambda e: to_utc_interval(e["dt"], e["precision"])[0])
    cutoff_early = to_utc_interval(cutoff["dt"], cutoff["precision"])[0]
    for t, (re_, re_prec, raw_end) in sorted(coverage.items()):
        if to_utc_interval(re_, re_prec)[1] < cutoff_early:
            result["failures"].append((RC.ANNOUNCEMENT_COVERAGE_INCOMPLETE,
                                       f"「{t}」查詢終點 {raw_end} 早於最早事件 {cutoff['iso']}，無法排除更早的揭露"))
    if result["failures"]:
        return result
    result.update(ok=True, cutoff=cutoff)
    result["trace"].update(cutoff_at=cutoff["iso"], cutoff_precision=cutoff["precision"],
                           cutoff_document_id=cutoff["document_id"], cutoff_event_type=cutoff["event_type"])
    return result
