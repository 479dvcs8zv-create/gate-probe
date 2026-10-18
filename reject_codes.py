"""
reject_codes.py
================
穩定的機器可讀代碼，給 Python 預驗證層與正式 Worker 比對時用。

原則：
  - 代碼一旦發布就不能改名（可以新增，不能重新定義語意），
    否則跨版本比對會失真。
  - 每個代碼對應一種「可歸類的拒絕/警示原因」，reasons（人類可讀文字）
    可以隨時改措辭，但 code 要穩定，兩邊比對時比對 code 而非文字。
"""


class RC:
    # 通用
    DATA_NOT_CONNECTED = "DATA_NOT_CONNECTED"
    DUPLICATE_REMOVED = "DUPLICATE_REMOVED"
    NULL_VALUE_REMOVED = "NULL_VALUE_REMOVED"
    MIN_COUNT_NOT_MET = "MIN_COUNT_NOT_MET"

    # PEG / 數值類
    YEAR_MISMATCH = "YEAR_MISMATCH"
    OUTLIER_REMOVED = "OUTLIER_REMOVED"
    OUTLIER_UNDETERMINED = "OUTLIER_UNDETERMINED"   # MAD=0時與眾數不同的值，待人工覆核，不計入有效
    SAMPLE_TOO_SMALL_FOR_OUTLIER_CHECK = "SAMPLE_TOO_SMALL_FOR_OUTLIER_CHECK"
    ZERO_SPREAD_SKIP_OUTLIER_CHECK = "ZERO_SPREAD_SKIP_OUTLIER_CHECK"  # 保留：數值完全一致且無差異時使用
    CLAIMED_COUNT_MISMATCH = "CLAIMED_COUNT_MISMATCH"

    # Gate5B 時間驗證專用
    # 【v4.5 起停止產生】下列四個代碼原本由「adapter 時間前置檢查」產生，會在獨立驗證之前
    # 就擋下資料，讓 adapter 欄位仍能左右判定。v4.5 起 adapter 時間只做稽核
    # （CLAIMED_TIMING_INCONSISTENT），這四個代碼不再由任何 Gate 產生；
    # 依「代碼不改語意」原則保留定義，只供讀取舊版報告時對照。
    TIME_PRECISION_INSUFFICIENT = "TIME_PRECISION_INSUFFICIENT"   # （已停用）只有日期無時間，同日無法判斷先後
    POST_EARNINGS_REJECTED = "POST_EARNINGS_REJECTED"             # （已停用）可確認在公告之後
    DECLARATION_MISMATCH = "DECLARATION_MISMATCH"                 # （已停用）宣告值與實際判斷結果矛盾
    UNPARSEABLE_DATE = "UNPARSEABLE_DATE"                         # （已停用）
    SOURCE_UNVERIFIABLE = "SOURCE_UNVERIFIABLE"                   # 來源驗證未全部通過（每筆失敗快照的摘要代碼）
    CLAIMED_TIMING_INCONSISTENT = "CLAIMED_TIMING_INCONSISTENT"   # （稽核用）adapter 自報的時間或旗標自相矛盾、無法解析、或與封存時間不符
    CLAIMED_TIER_OVERSTATED = "CLAIMED_TIER_OVERSTATED"           # 來源宣告的可信等級高於獨立驗證結果（稽核用）
    CONFLICTING_VALUES_SAME_KEY = "CONFLICTING_VALUES_SAME_KEY"   # 同一key下出現彼此不同的數值，視為實質衝突
    CLAIMED_HASH_MISMATCH = "CLAIMED_HASH_MISMATCH"               # adapter聲稱的雜湊/時間戳/內容與獨立驗證結果不一致（稽核用）

    # ---- v4.3 原子性證據包（Gate5B Layer2/3/4 共用同一份不可變證據） ----
    EVIDENCE_BUNDLE_UNAVAILABLE = "EVIDENCE_BUNDLE_UNAVAILABLE"                      # 無法取得獨立證據包
    EVIDENCE_BUNDLE_INCOMPLETE = "EVIDENCE_BUNDLE_INCOMPLETE"                        # 證據包缺少必要欄位
    EVIDENCE_SNAPSHOT_ID_MISMATCH = "EVIDENCE_SNAPSHOT_ID_MISMATCH"                  # 內容/時間/網址不屬於同一個封存快照
    EVIDENCE_CONTENT_MISMATCH = "EVIDENCE_CONTENT_MISMATCH"                          # 原文與待驗資料不一致（含無法結構化解析）
    EVIDENCE_PERIOD_MISMATCH = "EVIDENCE_PERIOD_MISMATCH"                            # 年度或季度不符
    EVIDENCE_ISSUER_MISMATCH = "EVIDENCE_ISSUER_MISMATCH"                            # 公司識別不符
    EVIDENCE_HASH_MISMATCH = "EVIDENCE_HASH_MISMATCH"                                # 由原始位元組重算的 SHA-256 不一致
    EVIDENCE_HASH_ALGORITHM_UNSUPPORTED = "EVIDENCE_HASH_ALGORITHM_UNSUPPORTED"      # 不支援的雜湊演算法或格式
    EVIDENCE_ARCHIVE_TIMESTAMP_UNVERIFIED = "EVIDENCE_ARCHIVE_TIMESTAMP_UNVERIFIED"  # 無法獨立確認封存時間（含精度不足）
    EVIDENCE_ARCHIVED_AFTER_EARNINGS = "EVIDENCE_ARCHIVED_AFTER_EARNINGS"            # 封存時間晚於財報公告
    EVIDENCE_IMMUTABILITY_UNPROVEN = "EVIDENCE_IMMUTABILITY_UNPROVEN"                # Layer4 整體結論：無法證明內容不可事後修改
    EVIDENCE_SOURCE_NOT_INDEPENDENT = "EVIDENCE_SOURCE_NOT_INDEPENDENT"              # 封存服務不具獨立性
    EVIDENCE_VERIFIER_ERROR = "EVIDENCE_VERIFIER_ERROR"                              # 驗證器執行錯誤（fail-closed）

    # ---- v4.4 財報公告時間獨立查證（不再以 adapter 的公告時間作為放行依據） ----
    ANNOUNCEMENT_EVIDENCE_UNAVAILABLE = "ANNOUNCEMENT_EVIDENCE_UNAVAILABLE"          # 無法取得官方公告事件，或查無事件
    ANNOUNCEMENT_EVIDENCE_INCOMPLETE = "ANNOUNCEMENT_EVIDENCE_INCOMPLETE"            # 公告證據缺少必要欄位
    ANNOUNCEMENT_SOURCE_NOT_OFFICIAL = "ANNOUNCEMENT_SOURCE_NOT_OFFICIAL"            # 公告來源不是官方網域
    ANNOUNCEMENT_CONTENT_MISMATCH = "ANNOUNCEMENT_CONTENT_MISMATCH"                  # 公告原文無法結構化解析出事件紀錄
    ANNOUNCEMENT_ISSUER_MISMATCH = "ANNOUNCEMENT_ISSUER_MISMATCH"                    # 公告屬於其他公司
    ANNOUNCEMENT_PERIOD_MISMATCH = "ANNOUNCEMENT_PERIOD_MISMATCH"                    # 公告屬於其他年度或季度
    ANNOUNCEMENT_TIME_UNVERIFIED = "ANNOUNCEMENT_TIME_UNVERIFIED"                    # 公告時間無法解析
    ANNOUNCEMENT_HASH_MISMATCH = "ANNOUNCEMENT_HASH_MISMATCH"                        # 由原始位元組重算的 SHA-256 不一致
    ANNOUNCEMENT_HASH_ALGORITHM_UNSUPPORTED = "ANNOUNCEMENT_HASH_ALGORITHM_UNSUPPORTED"  # 不支援的雜湊演算法或格式
    ANNOUNCEMENT_VERIFIER_ERROR = "ANNOUNCEMENT_VERIFIER_ERROR"                      # 公告驗證器執行錯誤（fail-closed）
    CLAIMED_ANNOUNCEMENT_TIME_MISMATCH = "CLAIMED_ANNOUNCEMENT_TIME_MISMATCH"        # adapter 聲稱的公告時間與官方最早公告不一致（稽核用）

    # ---- v4.6 官方公告完整性（漏抓較早的揭露會讓截止點被高估，fail-closed 本身擋不住，必須明確要求） ----
    ANNOUNCEMENT_COVERAGE_INCOMPLETE = "ANNOUNCEMENT_COVERAGE_INCOMPLETE"            # 驗證器未宣告、或宣告的查詢期間／事件類型不足
    ANNOUNCEMENT_CORRECTION_ORIGINAL_MISSING = "ANNOUNCEMENT_CORRECTION_ORIGINAL_MISSING"  # 有更正公告，但沒有附上被更正的原始公告

    # ---- v4.7 可稽核的查詢證據（完整性由官方回應本身證明，不再相信驗證器宣告） ----
    ANNOUNCEMENT_PAGINATION_INCOMPLETE = "ANNOUNCEMENT_PAGINATION_INCOMPLETE"        # 缺頁、頁碼不一致、合計筆數不符、或回應標示被截斷
    ANNOUNCEMENT_LISTED_DOCUMENT_MISSING = "ANNOUNCEMENT_LISTED_DOCUMENT_MISSING"    # 官方清單列出的公告，驗證器沒有提供原文
    ANNOUNCEMENT_DOCUMENT_NOT_LISTED = "ANNOUNCEMENT_DOCUMENT_NOT_LISTED"            # 驗證器提供的公告，不在任何官方查詢清單中

    # Gate8 同業
    MISSING_TICKER = "MISSING_TICKER"
    TICKER_NOT_QUALIFIED = "TICKER_NOT_QUALIFIED"
    COMPANY_ID_MISMATCH = "COMPANY_ID_MISMATCH"
    REQUIRED_YEAR_MISSING = "REQUIRED_YEAR_MISSING"

    # Gate5A / Gate4
    BASIS_MISMATCH = "BASIS_MISMATCH"
    MISSING_ORIGINAL_SOURCE = "MISSING_ORIGINAL_SOURCE"


class Diagnostics:
    """累積 (code, message) pair，最後分別輸出成 reasons（人類讀）與
    reject_codes（機器比對用），兩個陣列順序保證一一對應。"""

    def __init__(self):
        self.reasons = []
        self.codes = []

    def add(self, code: str, message: str):
        self.codes.append(code)
        self.reasons.append(message)

    def extend_notes(self, code: str, messages: list):
        for m in messages:
            self.add(code, m)
