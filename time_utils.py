"""
time_utils.py
==============
時間解析與區間比較的共用邏輯，從 gates.py 抽出來，讓
evidence_verification.py 的時間戳確認也能共用同一套規則，
避免兩處各寫一份、邏輯不一致。

本輪修正（P1-1）：_parse_with_precision 不再有「解析失敗就退回只取
前10碼當日期」這種危險退路。規則改成：

  - 字串本身看起來就「不含」時間標記（沒有 'T'、沒有 ':'）
    → 走純日期解析，失敗就是無法解析。
  - 字串「含有」時間標記，但完整解析失敗（例如 "2026-13-99T25:99:99"
    這種格式錯誤或數值不合法的時間戳）→ 直接判定無法解析，
    絕不能悄悄截斷成前10碼硬當日期用——那樣等於把一個本來意圖
    提供時分精度、但內容損毀的時間戳，誤判成「合法的純日期」，
    掩蓋了資料品質問題。
"""

from datetime import datetime, timedelta, timezone as dt_timezone

MAX_TZ_OFFSET = timedelta(hours=14)
MIN_TZ_OFFSET = timedelta(hours=-12)


def parse_with_precision(value):
    """回傳 (datetime, precision)。precision 為：
      "datetime_tz"    - 含時間與時區，可精確比較
      "datetime_naive" - 含時間但無時區資訊
      "date_only"      - 僅日期，無時間部分
      None             - 無法解析（包含「看起來有時間但解析失敗」的情況）
    """
    if value is None:
        return None, None
    s = str(value).strip()
    looks_like_has_time = ("T" in s) or (":" in s)

    if not looks_like_has_time:
        if len(s) > 10:
            # 比純日期字串還長，但又沒有時間標記，格式可疑，
            # 不強行只取前10碼硬解，直接視為無法解析。
            return None, None
        try:
            dt = datetime.strptime(s[:10], "%Y-%m-%d")
            return dt, "date_only"
        except ValueError:
            return None, None

    # 字串看起來含時間部分，必須完整正確解析；失敗就是失敗，不退回日期解析。
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None, None
    return dt, ("datetime_tz" if dt.tzinfo is not None else "datetime_naive")


def to_utc_interval(dt, precision):
    """把一個時間值換算成「它實際對應的UTC時刻，可能落在的範圍」
    (earliest_utc, latest_utc)。精度越低，區間越寬。"""
    if precision == "datetime_tz":
        utc_dt = dt.astimezone(dt_timezone.utc)
        return utc_dt, utc_dt
    if precision == "datetime_naive":
        earliest = (dt - MAX_TZ_OFFSET).replace(tzinfo=dt_timezone.utc)
        latest = (dt - MIN_TZ_OFFSET).replace(tzinfo=dt_timezone.utc)
        return earliest, latest
    if precision == "date_only":
        day_start = datetime.combine(dt.date(), datetime.min.time())
        day_end = day_start + timedelta(days=1) - timedelta(seconds=1)
        earliest = (day_start - MAX_TZ_OFFSET).replace(tzinfo=dt_timezone.utc)
        latest = (day_end - MIN_TZ_OFFSET).replace(tzinfo=dt_timezone.utc)
        return earliest, latest
    return None, None


def classify_timing(snap_dt, snap_prec, earn_dt, earn_prec) -> str:
    """回傳 "PRE" | "POST" | "SAME_DAY_AMBIGUOUS" | "UNPARSEABLE"。"""
    if snap_dt is None or earn_dt is None:
        return "UNPARSEABLE"
    s_early, s_late = to_utc_interval(snap_dt, snap_prec)
    e_early, e_late = to_utc_interval(earn_dt, earn_prec)
    if s_early is None or e_early is None:
        return "UNPARSEABLE"
    if s_late < e_early:
        return "PRE"
    if s_early > e_late:
        return "POST"
    return "SAME_DAY_AMBIGUOUS"


def hours_between(dt1, dt2) -> float:
    """兩個時間值相差幾小時（取絕對值），忽略時區資訊只比較naive差值，
    僅供粗略誤差範圍核對用（例如 evidence_verification 的時間戳確認）。"""
    d1 = dt1.replace(tzinfo=None) if dt1.tzinfo else dt1
    d2 = dt2.replace(tzinfo=None) if dt2.tzinfo else dt2
    return abs((d1 - d2).total_seconds()) / 3600.0
