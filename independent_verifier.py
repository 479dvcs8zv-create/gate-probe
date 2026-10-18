"""
independent_verifier.py (v4.6)
===============================
封存證據包的獨立驗證器。只有一個方法 fetch_verified_bundle()：一次、原子性地從
「同一個封存版本」取回原始位元組、封存時間、快照 ID 與雜湊，包成 VerifiedEvidenceBundle。
evidence_verification.py 對這一份證據包做全部檢查。

v4.6：
  - WebArchiveVerifier 改為真正的網路實作（Wayback CDX + id_ 原文）。
  - fetch_verified_bundle 多一個 captured_before：官方最早揭露時間（由
    announcement_verification 獨立查證，不是 adapter 提供）。驗證器只會選這個時間
    之前的封存版本；即使封存服務沒有照參數過濾，驗證器自己也會再過濾一次。
  - 驗證器可以拋出 VerifierFault 並附上「限定範圍」的拒絕代碼，讓「內容被竄改」
    和「服務連不上」在報告中可以區分。evidence_verification 只接受白名單內的代碼，
    其他例外一律記為 EVIDENCE_VERIFIER_ERROR。任何例外都 fail-closed。

信任邊界（誠實版）：
  - 證據包回報的 sha256 不被信任，evidence_verification 一律由 content_bytes 重算。
  - WebArchiveVerifier 另外比對 Wayback CDX 在「封存當下」記錄的內容摘要
    （SHA-1，base32）。這是封存服務在擷取時寫下的紀錄，用來確認現在取得的位元組
    就是當時封存的位元組。SHA-1 在密碼學上已不夠強，因此它只是額外的一致性檢查；
    完整性主要仍靠獨立封存服務 + 快照 ID 綁定 + SHA-256 重算。
  - 本環境無法連到 Wayback（代理回應 403），WebArchiveVerifier 只用本機模擬伺服器
    做過協定層級與故障注入測試。對真實 Wayback 的行為（網址正規化、壓縮內容的摘要、
    轉址規則）必須在可連網的環境做端對端驗收；遇到不一致時本實作一律 fail-closed。
"""

import base64
import hashlib
import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from reject_codes import RC


@dataclass
class VerifiedEvidenceBundle:
    """一次原子性查證的完整結果。所有欄位必須來自同一個封存版本。"""
    source_url: str              # 被封存的原始網址（必須等於請求查證的網址）
    archive_url: str             # 該封存版本的網址（例如 Wayback memento URL）
    snapshot_id: str             # 封存服務的版本識別碼（Wayback 為 14 位 UTC 時間戳 YYYYMMDDhhmmss）
    captured_at: str             # 封存時間，ISO8601 且必須帶時區
    content_bytes: bytes         # 原始位元組（未解碼），SHA-256 必須對它計算
    sha256: str                  # 回報的雜湊（hex），只供比對，不被信任
    hash_algorithm: str = "sha256"
    verification_status: str = "unknown"  # 驗證器自報狀態，僅記錄在軌跡中，不參與判定
    # v4.7：封存服務在「擷取當下」記錄的內容摘要，以及取回內容是否與它相符。
    # 相符只代表「現在取得的位元組 = 封存服務當時記錄的位元組」，
    # 不代表「獨立證明封存服務本身沒有修改歷史內容」，兩者在報告中分開呈現。
    archive_digest: str = ""
    archive_digest_algorithm: str = ""
    archive_digest_matched: Optional[bool] = None
    retrieval_trace: Optional[dict] = None   # 索引查詢的分頁、筆數、時間窗等，供稽核
    content_type: str = ""                   # 封存原文的 Content-Type（含 charset），供依宣告字元集解碼


class VerifierFault(Exception):
    """驗證器失敗。reject_code 只是建議，evidence_verification 只接受白名單內的代碼。"""

    def __init__(self, message: str, reject_code: Optional[str] = None):
        super().__init__(message)
        self.reject_code = reject_code


class ArchiveFetchError(VerifierFault):
    """取得失敗（連不上、HTTP 錯誤、逾時、格式錯誤、超過大小上限）。記為 EVIDENCE_VERIFIER_ERROR。"""


class ArchiveIntegrityError(VerifierFault):
    """取得了內容但完整性不成立（摘要不符、被轉址到其他版本、原始網址不符）。"""


class IndependentVerifier(ABC):
    @abstractmethod
    def fetch_verified_bundle(self, source_url: str,
                              captured_before: Optional[datetime] = None) -> Optional[VerifiedEvidenceBundle]:
        """一次取得同一封存版本的完整證據包。
        captured_before：只接受早於此時間（UTC）的封存版本。
        回傳 None 代表查無符合的封存版本；拋出例外代表查證失敗。兩者呼叫端都會 fail-closed。"""
        raise NotImplementedError


class NullIndependentVerifier(IndependentVerifier):
    """沒有網路存取能力的環境：誠實回傳 None，Gate5B 永遠不會判定通過。"""

    def fetch_verified_bundle(self, source_url, captured_before=None):
        return None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """不自動跟隨轉址：Wayback 在指定版本不存在時會轉址到最接近的版本，
    自動跟隨就可能拿到另一個時間點的內容。"""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class WebArchiveVerifier(IndependentVerifier):
    """以 Internet Archive Wayback Machine 取得封存證據。

    流程：
      1. CDX 查詢：只要 HTTP 200 的版本，時間窗 from = 截止點前 lookback_days 天、to = 截止點前一秒。
         以正數 limit 分頁並要求續查鍵（showResumeKey），逐頁取完整個時間窗；
         不依賴負數 limit「只取最後幾筆」的服務端語意。
         某頁剛好滿頁卻沒有續查鍵 → 無法確認是否被截斷，fail-closed；頁數超過上限也 fail-closed。
         回應中的每一筆都再自行確認早於截止點，不信任服務端過濾。
      2. 取最接近截止點的那一版，CDX 記錄的原始網址必須與請求完全相同。
      3. 以 {timestamp}id_ 取回原始位元組（不含 Wayback 工具列），不跟隨轉址，有大小上限。
      4. 原文的 SHA-1(base32) 必須等於 CDX 在封存當下記錄的 digest。
      5. 回傳證據包：快照 ID = timestamp，封存時間由 timestamp 換算（UTC），
         sha256 由原文計算。
    """

    CDX_FIELDS = ("timestamp", "original", "statuscode", "digest", "mimetype")

    def __init__(self, base_url: str = "https://web.archive.org", timeout: float = 20.0,
                 max_bytes: int = 10 * 1024 * 1024, opener=None, cdx_page_size: int = 100,
                 max_cdx_pages: int = 20, lookback_days: int = 180,
                 user_agent: str = "gate-pipeline-evidence-verifier/4.7"):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.max_bytes = max_bytes
        self.cdx_page_size = cdx_page_size
        self.max_cdx_pages = max_cdx_pages
        self.lookback_days = lookback_days
        self.user_agent = user_agent
        self.opener = opener or self.build_opener()
        self.requests = []  # 實際發出的網址，供稽核與測試
        self.last_cdx_trace = None
        self.last_content_type = ""

    @staticmethod
    def build_opener(proxy_url: Optional[str] = None):
        """預設沿用環境的代理設定；不論是否指定代理，都不自動跟隨轉址。"""
        handlers = [_NoRedirect()]
        if proxy_url:
            handlers.append(urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url}))
        return urllib.request.build_opener(*handlers)

    def _get(self, url: str) -> bytes:
        self.requests.append(url)
        req = urllib.request.Request(url, headers={"User-Agent": self.user_agent, "Accept-Encoding": "identity"})
        try:
            with self.opener.open(req, timeout=self.timeout) as resp:
                status = resp.status
                body = resp.read(self.max_bytes + 1)
                self.last_content_type = resp.headers.get("Content-Type", "") or ""
        except urllib.error.HTTPError as e:
            if 300 <= e.code < 400:
                raise ArchiveIntegrityError(
                    f"封存服務回應轉址 HTTP {e.code}（→ {e.headers.get('Location')}），拒絕跟隨以免取到其他版本",
                    RC.EVIDENCE_SNAPSHOT_ID_MISMATCH)
            raise ArchiveFetchError(f"封存服務回應 HTTP {e.code}")
        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError, OSError) as e:
            raise ArchiveFetchError(f"無法連線封存服務：{type(e).__name__}: {getattr(e, 'reason', e)}")
        if status != 200:
            raise ArchiveFetchError(f"封存服務回應 HTTP {status}")
        if len(body) > self.max_bytes:
            raise ArchiveFetchError(f"封存服務回應超過 {self.max_bytes} bytes 上限")
        return body

    def _cdx_page(self, params: dict):
        """取一頁 CDX，回傳 (records, resume_key)。"""
        raw = self._get(f"{self.base_url}/cdx/search/cdx?{urllib.parse.urlencode(params)}")
        try:
            text = raw.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError:
            raise ArchiveFetchError("CDX 回應不是有效的 UTF-8")
        if not text:
            return [], None
        try:
            rows = json.loads(text)
        except ValueError:
            raise ArchiveFetchError("CDX 回應不是有效的 JSON")
        if not isinstance(rows, list) or not rows:
            return [], None
        resume = None
        # showResumeKey=true 時，續查鍵以「空列 + 單欄列」附在最後
        if len(rows) >= 2 and rows[-2] == [] and isinstance(rows[-1], list) and len(rows[-1]) == 1:
            resume = str(rows[-1][0])
            rows = rows[:-2]
        if not rows:
            return [], resume
        header = rows[0]
        if not isinstance(header, list) or not set(self.CDX_FIELDS) <= set(header):
            raise ArchiveFetchError(f"CDX 回應欄位不符：{header!r}")
        records = []
        for r in rows[1:]:
            if not isinstance(r, list) or len(r) != len(header):
                raise ArchiveFetchError("CDX 回應列格式錯誤")
            records.append(dict(zip(header, r)))
        return records, resume

    def _cdx_records(self, source_url: str, captured_before: Optional[datetime]) -> list:
        params = {"url": source_url, "output": "json", "fl": ",".join(self.CDX_FIELDS),
                  "filter": "statuscode:200", "limit": str(self.cdx_page_size), "showResumeKey": "true"}
        if captured_before is not None:
            before = captured_before.astimezone(timezone.utc)
            params["to"] = (before - timedelta(seconds=1)).strftime("%Y%m%d%H%M%S")
            params["from"] = (before - timedelta(days=self.lookback_days)).strftime("%Y%m%d%H%M%S")
        records, pages, resume = [], 0, None
        while True:
            if resume is not None:
                params["resumeKey"] = resume
            page_records, resume = self._cdx_page(params)
            pages += 1
            records.extend(page_records)
            if resume is None:
                if len(page_records) >= self.cdx_page_size:
                    raise ArchiveFetchError(
                        f"CDX 第 {pages} 頁剛好 {len(page_records)} 筆（滿頁）卻沒有續查鍵，無法確認結果是否被截斷")
                break
            if pages >= self.max_cdx_pages:
                raise ArchiveFetchError(f"CDX 超過 {self.max_cdx_pages} 頁仍未取完，無法確認是否取得完整封存清單")
        self.last_cdx_trace = {"pages": pages, "records": len(records), "from": params.get("from"),
                               "to": params.get("to"), "page_size": self.cdx_page_size}
        return records

    def fetch_verified_bundle(self, source_url, captured_before=None):
        candidates = []
        for rec in self._cdx_records(source_url, captured_before):
            ts = str(rec.get("timestamp", ""))
            if not re.fullmatch(r"\d{14}", ts):
                raise ArchiveFetchError(f"CDX 回應的時間戳「{ts}」格式錯誤")
            ts_dt = datetime.strptime(ts, "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
            if rec.get("statuscode") != "200":
                continue
            if captured_before is not None and ts_dt >= captured_before.astimezone(timezone.utc):
                continue  # 不信任服務端過濾：截止點之後的版本一律不選
            candidates.append((ts_dt, rec))
        if not candidates:
            return None

        ts_dt, rec = max(candidates, key=lambda c: c[0])
        if rec.get("original") != source_url:
            raise ArchiveIntegrityError(
                f"CDX 記錄的原始網址「{rec.get('original')}」與請求的「{source_url}」不同",
                RC.EVIDENCE_SNAPSHOT_ID_MISMATCH)

        snapshot_id = rec["timestamp"]
        body = self._get(f"{self.base_url}/web/{snapshot_id}id_/{source_url}")
        content_type = self.last_content_type

        digest = str(rec.get("digest", ""))
        if not re.fullmatch(r"[A-Z2-7]{32}", digest):
            raise ArchiveIntegrityError("CDX 沒有提供有效的封存當下內容摘要，無法確認內容未被修改",
                                        RC.EVIDENCE_IMMUTABILITY_UNPROVEN)
        served = base64.b32encode(hashlib.sha1(body).digest()).decode("ascii")
        if served != digest:
            raise ArchiveIntegrityError("取得的內容與封存當下記錄的摘要不一致（可能被修改，或取到不同版本）",
                                        RC.EVIDENCE_HASH_MISMATCH)

        return VerifiedEvidenceBundle(
            source_url=source_url,
            archive_url=f"{self.base_url}/web/{snapshot_id}/{source_url}",
            snapshot_id=snapshot_id,
            captured_at=ts_dt.isoformat(),
            content_bytes=body,
            sha256=hashlib.sha256(body).hexdigest(),
            hash_algorithm="sha256",
            verification_status="cdx_digest_matched",
            archive_digest=digest,
            archive_digest_algorithm="sha1-base32",
            archive_digest_matched=True,
            retrieval_trace={**(self.last_cdx_trace or {}), "candidates_before_cutoff": len(candidates),
                             "selected_timestamp": snapshot_id},
            content_type=content_type,
        )
