"""
schema.py
=========
整套管線的「資料契約」。所有資料來源（不論是你的 GPT 處理網站、付費 API、
或未來任何新來源）只要回傳符合這裡定義格式的 dict / dataclass，
後面的 Gate 判定邏輯就能直接吃進去，不需要關心資料是怎麼抓來的。

這是刻意做的「關注點分離」：
  抓資料（adapters/*.py）  →  標準化（本檔案的 schema）  →  判定（gates/*.py）
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Optional, List, Dict, Any


# ---------- 共用：每一筆資料都要能追溯 ----------

@dataclass
class Provenance:
    """任何一筆數值都必須標明出處，否則視為不可信，不得進入 Gate 判定。

    evidence_tier 區分「有連結」跟「真的能證明資料沒被事後竄改」是兩回事：
      - "official_record"：官方/監理機關/交易所本身發布的紀錄（如公司重大訊息公告、
        交易所公告），本質上具公信力與時間戳。
      - "immutable_archive"：不可變存證服務（如加蓋可信時間戳的快照、
        Wayback Machine 有時間戳的頁面版本、區塊鏈存證等），可證明某時間點內容。
      - "unverified_link"：純粹一個網址，沒有任何機制證明內容沒被事後修改——
        即使連結本身是真的，也不能單憑它認定歷史時點資料未被竄改。
      - None：未標註，視同 "unverified_link" 處理（最低信任等級）。
    """
    source_name: str            # 例如 "BLS", "FRED", "公司法說會簡報", "GPT網站抓取:XXX"
    source_url: Optional[str]   # 原文連結，缺的話必須是 None 並在 pipeline 標記警告
    fetched_at: str             # ISO8601 timestamp，抓取當下時間
    as_of_date: Optional[str]   # 資料本身對應的日期（例如財報期別、公告日）
    raw_excerpt: Optional[str] = None   # 原文摘要（供人工核對，非逐字大段引用）
    claimed_evidence_tier: Optional[str] = None   # 資料來源「自己宣告」的等級，僅供稽核比對，Gate絕不可直接採信
    verified_evidence_tier: Optional[str] = None  # 經 evidence_verification.py 獨立規則驗證後的等級，
                                                    # 只有這個欄位能決定 Gate5B 是否放行；
                                                    # 預設 None 代表「尚未驗證」，呼叫端需先跑驗證才能使用


@dataclass
class DataPoint:
    value: Any
    provenance: Provenance
    is_stale: bool = False      # pipeline 會依 as_of_date + 下次發布時間自動判斷
    notes: Optional[str] = None


# ---------- Gate 4 護城河 ----------

@dataclass
class MoatComparisonItem:
    peer_name: str
    comparison_point: str        # 例如 "製程良率", "客戶集中度"
    target_value: DataPoint
    peer_value: DataPoint
    original_text_source: Optional[DataPoint] = None  # 附原文比較證據


# ---------- PSR / PEG ----------

@dataclass
class PSRHistory:
    ticker: str
    basis_definition: str         # 口徑定義：股本基準 / 營收欄位，必須明確寫死
    quarterly_series: List[DataPoint] = field(default_factory=list)  # 至少 20 季 (5年)


@dataclass
class AnalystEstimate:
    """單一機構的一筆預估值。相較於裸的 DataPoint，這裡強制要求機構身分
    （institution_id）與目標年度，去重與跨欄位核對才有依據，
    不能只靠 source_name 字串比對（名稱容易同名、縮寫不一致）。"""
    institution_id: str           # 機構代碼/統一識別，例如券商內部代號或公開資料庫ID
    institution_name: str
    target_year: int
    eps: DataPoint


@dataclass
class PEGConsensus:
    ticker: str
    target_year: int              # 例如 2027
    eps_estimates: List[AnalystEstimate] = field(default_factory=list)  # 多家券商
    median_eps: Optional[float] = None
    coverage_count: int = 0       # 幾家券商覆蓋（僅供參考，判定時一律重新計算，不採信此欄位）


# ---------- 產能風險 ----------

@dataclass
class CapacityRiskProfile:
    ticker: str
    fab_location_exposure: List[DataPoint] = field(default_factory=list)  # 產地曝險 %
    alternative_sources: List[DataPoint] = field(default_factory=list)    # 替代方案
    customer_concentration: List[DataPoint] = field(default_factory=list) # 前五大客戶占比


# ---------- 可轉債 (CB) ----------

@dataclass
class ConvertibleBondRecord:
    cb_id: str
    conversion_price: DataPoint
    shares_outstanding_same_day: DataPoint
    fx_rate_same_day: DataPoint
    event_log: List[DataPoint] = field(default_factory=list)  # 贖回/轉換/重設事件


# ---------- 大戶籌碼 ----------

@dataclass
class HolderConcentration:
    ticker: str
    threshold_lots: int           # 大戶門檻，例如 400 張
    weekly_distribution: List[DataPoint] = field(default_factory=list)
    consecutive_weeks_trend: Optional[int] = None  # 延續性：連續N週增/減


# ---------- Gate 5A / 5B 指引與共識 ----------

@dataclass
class EarningsCalendarEntry:
    """財報公告行事曆，Gate5B 驗證快照是否真的在財報前必須靠這個基準比對，
    不能只看快照自己宣稱的布林值。"""
    ticker: str
    fiscal_quarter: str
    actual_announcement_date: DataPoint


@dataclass
class GuidanceRecord:
    ticker: str
    fiscal_year: int
    guidance_text: DataPoint          # 原始指引用詞
    guidance_release_date: DataPoint  # 原發布日
    actual_result: DataPoint          # 同口徑實績
    basis_matches: bool               # 口徑是否一致（排除業外、股本調整與否）


@dataclass
class PreEarningsConsensusSnapshot:
    ticker: str
    fiscal_quarter: str                # 例如 "2026Q3"
    snapshot_date: DataPoint           # 快照「實際擷取/存證」的時間點，必須可查證
    earnings_announcement_date: DataPoint  # 該季財報「實際公告」日期，用來跟上面比對
    consensus_eps: DataPoint
    consensus_revenue: DataPoint
    snapshot_taken_before_earnings: bool = False  # 保留舊欄位，但判定不再單獨採信此值，
                                                    # 只用來跟實際日期比對是否「宣告與事實不符」

    # 四層存證驗證用（evidence_verification.verify_pre_earnings_evidence）：
    # 這三個欄位全部是 adapter「聲稱」的值（claimed_*），不是獨立驗證的結果。
    # 真正的驗證結果（observed_* / verified_*）由 IndependentVerifier 在驗證當下
    # 現場取得，不儲存在這個物件上、也不信任這裡填的任何東西作為驗證依據——
    # 這些欄位只用來跟 IndependentVerifier 回報的「真正觀察值」做比對，
    # 兩者不一致時才是真正有意義的稽核訊號。
    claimed_archive_timestamp: Optional[DataPoint] = None
        # adapter聲稱的「存證服務回報的封存時間」。注意：這仍然是adapter自己填的，
        # 不能直接當作「獨立確認」——真正的獨立確認要靠 IndependentVerifier
        # 現場向存證服務查詢取得 observed_archive_timestamp 後比對。
    claimed_content_hash: Optional[str] = None
        # adapter聲稱的內容雜湊/memento ID。同樣只是聲稱，必須靠
        # IndependentVerifier 重新取得 observed_content_hash 後比對才算數。


# ---------- Gate 8 同業 ----------

@dataclass
class PeerQualification:
    peer_name: str
    ticker: str                       # 股票代碼，跨欄位核對改用這個而非公司名稱字串
    company_id: Optional[str]         # 公司統一識別碼（如有），雙重核對用
    revenue_scale_match: bool
    product_overlap_score: float      # 0~1
    listing_region: str
    qualifies: bool                   # 是否達到「合格同業」門檻
    reason: str


@dataclass
class PeerConsensusRecord:
    peer_name: str
    ticker: str                       # 必須跟 PeerQualification.ticker 配對，而非僅名稱
    company_id: Optional[str]
    year: int
    consensus_value: DataPoint


# ---------- 匯總容器：一次巡檢的完整輸入 ----------

@dataclass
class TickerInputBundle:
    ticker: str
    moat_items: List[MoatComparisonItem] = field(default_factory=list)
    psr_history: Optional[PSRHistory] = None
    peg_consensus: Optional[PEGConsensus] = None
    capacity_risk: Optional[CapacityRiskProfile] = None
    cb_records: List[ConvertibleBondRecord] = field(default_factory=list)
    holder_concentration: Optional[HolderConcentration] = None
    guidance_records: List[GuidanceRecord] = field(default_factory=list)   # Gate 5A
    pre_earnings_snapshots: List[PreEarningsConsensusSnapshot] = field(default_factory=list)  # Gate 5B
    earnings_calendar: List[EarningsCalendarEntry] = field(default_factory=list)  # Gate 5B 比對基準
    peer_qualifications: List[PeerQualification] = field(default_factory=list)  # Gate 8
    peer_consensus_2yr: List[PeerConsensusRecord] = field(default_factory=list)  # Gate 8
