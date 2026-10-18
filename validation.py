"""
validation.py
==============
這一層專門處理「資料是不是真的能信」，跟 gates.py 的「判定門檻邏輯」分開放，
原因：

  1. 這些檢查（去重、空值、跨欄位配對）屬於資料完整性層次，
     之後你把驗證邏輯搬到網站 Worker 時，可以直接參照這份當規格，
     不需要連動 Gate 門檻數字。
  2. 「資料完整」與「Gate 通過」要分開：本檔案只負責產出
     「這批資料裡，有幾筆是真正有效、不重複、互相對得上的」，
     不負責判斷這樣夠不夠通過 Gate（那是 gates.py 的事）。

核心原則：永遠不信任來源聲稱的統計數字（像 coverage_count、
consecutive_weeks_trend），一律從原始明細重新算一次。
"""

from dataclasses import dataclass
from typing import List, Callable, TypeVar, Any, Optional
from schema import DataPoint

T = TypeVar("T")


@dataclass
class ValidationResult:
    valid_items: List[Any]
    duplicate_count: int
    null_or_empty_count: int
    mismatch_count: int = 0
    notes: List[str] = None

    def __post_init__(self):
        if self.notes is None:
            self.notes = []


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, str) and value.strip() == "":
        return True
    return False


def dedupe_by_key(items: List[T], key_fn: Callable[[T], Any]) -> ValidationResult:
    """依 key_fn 去重，同 key 只保留第一筆，其餘算進 duplicate_count。
    這是堵「同一筆資料複製貼上充數」最基本的一關。
    """
    seen = set()
    out = []
    dup = 0
    for item in items:
        k = key_fn(item)
        if k in seen:
            dup += 1
            continue
        seen.add(k)
        out.append(item)
    return ValidationResult(valid_items=out, duplicate_count=dup, null_or_empty_count=0)


def filter_valid_datapoints(items: List[T], value_fn: Callable[[T], DataPoint]) -> ValidationResult:
    """過濾掉 DataPoint.value 是 None/空字串的項目。
    這是堵「筆數湊夠但值是空的」這招。
    """
    out = []
    empty = 0
    for item in items:
        dp = value_fn(item)
        if dp is None or _is_empty(dp.value):
            empty += 1
            continue
        out.append(item)
    return ValidationResult(valid_items=out, duplicate_count=0, null_or_empty_count=empty)


def dedupe_and_filter(items: List[T], key_fn: Callable[[T], Any],
                       value_fn: Callable[[T], DataPoint]) -> ValidationResult:
    """舊版：先去重（保留第一筆）再過濾空值。
    保留此函式僅供向後相容；新邏輯一律改用 validate_then_dedupe，
    因為「先去重再過濾」有個漏洞：同鍵的第一筆恰好是空值時，
    後面真正有效的那一筆會被去重邏輯誤判為重複而丟棄。
    """
    deduped = dedupe_by_key(items, key_fn)
    filtered = filter_valid_datapoints(deduped.valid_items, value_fn)
    return ValidationResult(
        valid_items=filtered.valid_items,
        duplicate_count=deduped.duplicate_count,
        null_or_empty_count=filtered.null_or_empty_count,
    )


_TIER_RANK = {"official_record": 3, "immutable_archive": 2, "unverified_link": 1}


def _quality_score(dp: DataPoint) -> tuple:
    """品質分數：先比『獨立驗證後的可信層級』(verified_evidence_tier)，
    再比有無連結，最後比抓取時間新舊。用來在「同鍵多筆」時決定留哪一筆。

    刻意不信任 dp.provenance.claimed_evidence_tier（來源自己宣稱的等級）——
    一律用 evidence_verification 的網域規則當場重新判定。注意這裡只做
    Layer1（網域身分）等級的品質排序，不等於 Gate5B 的四層完整驗證；
    真正決定 Gate5B 能否放行的是 evidence_verification.verify_pre_earnings_evidence()。
    """
    from evidence_verification import verify_domain_identity
    tier = verify_domain_identity(dp.provenance.source_url)
    tier_score = _TIER_RANK.get(tier, 0)
    has_url = 1 if (dp.provenance.source_url and dp.provenance.source_url.strip()) else 0
    fetched_at = dp.provenance.fetched_at or ""
    return (tier_score, has_url, fetched_at)


def validate_then_dedupe(items: List[T], key_fn: Callable[[T], Any],
                          value_fn: Callable[[T], DataPoint]) -> ValidationResult:
    """正確順序：先過濾空值，只在「有效項目」裡去重，且同鍵多筆時
    依品質分數挑最好的一筆，而不是盲目保留第一筆。
    這樣第一筆若剛好是壞資料，不會連帶誤殺後面真正有效的紀錄。
    """
    filtered = filter_valid_datapoints(items, value_fn)
    groups: dict = {}
    order: List[Any] = []
    for item in filtered.valid_items:
        k = key_fn(item)
        if k not in groups:
            groups[k] = []
            order.append(k)
        groups[k].append(item)

    out = []
    dup = 0
    for k in order:
        group = groups[k]
        if len(group) > 1:
            dup += len(group) - 1
        best = max(group, key=lambda it: _quality_score(value_fn(it)))
        out.append(best)

    return ValidationResult(
        valid_items=out,
        duplicate_count=dup,
        null_or_empty_count=filtered.null_or_empty_count,
    )


def _median(sorted_values: List[float]) -> float:
    n = len(sorted_values)
    mid = n // 2
    return sorted_values[mid] if n % 2 == 1 else (sorted_values[mid - 1] + sorted_values[mid]) / 2


def filter_plausible_numeric(items: List[T], value_fn: Callable[[T], DataPoint],
                              mad_threshold: float = 3.5) -> ValidationResult:
    """離群值檢查，改用 MAD（中位數絕對離差）的穩健 z 分數法，不再用
    「除以中位數的倍率」——倍率法在中位數接近0、EPS為負值或零時會失真
    或直接除以零／產生無意義的巨大比值，判斷不可靠。

    做法：
      1. 算中位數 median
      2. 算每個值與中位數的絕對差，再取這些絕對差的中位數 = MAD
      3. modified z = 0.6745 * (x - median) / MAD
      4. |modified z| > mad_threshold（預設3.5，統計上常見門檻）視為離群值

    這個方法對正負值、零值一視同仁，不會因為符號或量級而失真。
    樣本數 < 4 時統計上不穩定，不做過濾（改為附註說明，交由人工核對）。
    MAD 為 0（表示大多數值完全相同）時無法定義有意義的離群門檻，
    同樣不過濾，但附註說明。
    """
    numeric_items = []
    for item in items:
        v = value_fn(item).value
        try:
            numeric_items.append((item, float(v)))
        except (TypeError, ValueError):
            continue

    if len(numeric_items) < 3:
        # n<3 時連「中位數」都無法有意義地代表集中趨勢，不做過濾。
        # n=3 其實可以算：中位數就是排序後中間那一筆，MAD 用其餘兩筆的絕對差，
        # 數學上依然成立（只是樣本極小時單一極端值的影響會被放大，這是預期行為：
        # 樣本越小，一筆離群值對判定的衝擊越大，這正是我們要抓的情況）。
        return ValidationResult(
            valid_items=[i for i, _ in numeric_items], duplicate_count=0, null_or_empty_count=0,
            notes=["樣本數<3，無法計算中位數，暫不過濾（建議人工核對）"] if numeric_items else [],
        )

    values = [v for _, v in numeric_items]
    median = _median(sorted(values))
    abs_devs = sorted(abs(v - median) for v in values)
    mad = _median(abs_devs)

    if mad == 0:
        # MAD=0 代表多數值完全相同（例如 10, 10, 500 的情況：中位數=10，
        # 多數值的絕對離差也是0）。不能像之前那樣「全部放行」，
        # 因為真正的離群值（500）會被一起帶過。改成：跟眾數（=中位數）
        # 不同的值一律標記為「待確認」而非直接採信為有效證據。
        matching = [item for item, v in numeric_items if v == median]
        differing_count = len(numeric_items) - len(matching)
        notes = (
            [f"MAD=0（多數值完全一致），但有{differing_count}筆與眾數不同，"
             f"列為待確認離群值(OUTLIER_UNDETERMINED)，不計入有效證據，需人工覆核"]
            if differing_count else
            ["數值高度一致（MAD=0），全部視為有效"]
        )
        return ValidationResult(
            valid_items=matching, duplicate_count=0, null_or_empty_count=differing_count,
            notes=notes,
        )

    out = []
    excluded = 0
    for item, v in numeric_items:
        modified_z = 0.6745 * (v - median) / mad
        if abs(modified_z) <= mad_threshold:
            out.append(item)
        else:
            excluded += 1
    notes = [f"{excluded}筆數值經MAD穩健檢定後視為離群值（含負值/零值情境），已剔除"] if excluded else []
    return ValidationResult(valid_items=out, duplicate_count=0, null_or_empty_count=excluded, notes=notes)


def detect_value_conflicts(items: List[T], key_fn: Callable[[T], Any],
                            value_fn: Callable[[T], DataPoint]) -> dict:
    """找出同一個 key 底下，數值彼此不同的情況（真衝突，而非單純重複貼上
    同一筆）。回傳 {key: [distinct_values]}，只包含有衝突（>1個不同值）的 key。

    這跟「去重」是兩回事：去重解決「到底算幾筆」，這個函式解決
    「同一個key出現衝突數值時，不能悄悄選一個就當作沒事」——
    衝突本身要被看見、被記錄，而不是被品質排序掩蓋掉。
    Gate5B（同季不同EPS）與 PEG（同機構同年度不同EPS）都適用。
    """
    from collections import defaultdict
    groups = defaultdict(set)
    for item in items:
        k = key_fn(item)
        v = value_fn(item)
        val = v.value if v else None
        if val is not None:
            groups[k].add(val)
    return {k: sorted(vs) for k, vs in groups.items() if len(vs) > 1}


def cross_match_peer_consensus(peer_qualifications: List, peer_consensus_records: List) -> ValidationResult:
    """Gate8 專用：共識紀錄必須真的對得上「合格」(qualifies=True) 的同業，
    核對依據改用 ticker（股票代碼）為主，company_id 為輔助雙重確認；
    只用 peer_name 字串配對容易同名誤判，不足以證明是同一家公司。

    規則：
      - ticker 必須相符（這是主要依據，股票代碼不會同名碰撞）
      - 若雙方都有填 company_id，則 company_id 也必須相符，否則視為配對失敗
        （例如同代碼但公司識別碼對不上，代表資料本身有矛盾，標記為不可信）
    """
    qualified_by_ticker = {p.ticker: p for p in peer_qualifications if p.qualifies and p.ticker}
    valid = []
    mismatch = 0
    reasons = []
    for rec in peer_consensus_records:
        if not rec.ticker:
            mismatch += 1
            reasons.append(f"{rec.peer_name} 的共識紀錄缺股票代碼，無法核對，已剔除")
            continue
        qp = qualified_by_ticker.get(rec.ticker)
        if qp is None:
            mismatch += 1
            reasons.append(f"股票代碼 {rec.ticker}（{rec.peer_name}）不在合格同業清單中，已剔除")
            continue
        if qp.company_id and rec.company_id and qp.company_id != rec.company_id:
            mismatch += 1
            reasons.append(f"股票代碼 {rec.ticker} 相符但公司識別碼不一致，資料矛盾，已剔除")
            continue
        valid.append(rec)
    return ValidationResult(
        valid_items=valid,
        duplicate_count=0,
        null_or_empty_count=0,
        mismatch_count=mismatch,
        notes=reasons,
    )
