// us_sector_session.mjs — 美股板塊快照「應有交易日」檢查（給 v228 的修補建議，gate-probe 不部署）
//
// 取代 normalizeUSSectorSnapshot 裡的「generated_at 距今 > 36 小時就丟 SCHEMA_SOURCE_OR_CAPTURE」：
//   1. 格式、來源、擷取時間各自回報錯誤碼，不再混在一起。
//   2. 時效改看「資料有沒有包含最後一個應有的交易日」，不看 generated_at 有多舊：
//      週末、假日不會誤判過期；只刷新 generated_at、資料沒變，也不會被當成更新。
//   3. 交易日依 NYSE 官方休市日與提前收盤日；超出表列年份就失敗（逼著更新表，不靜默放行）。
//
// NYSE 休市日與提前收盤：https://www.nyse.com/markets/hours-calendars（2026-10-19 讀取）

export const NYSE_HOLIDAYS = new Set([
  '2026-01-01', '2026-01-19', '2026-02-16', '2026-04-03', '2026-05-25', '2026-06-19', '2026-07-03',
  '2026-09-07', '2026-11-26', '2026-12-25',
  '2027-01-01', '2027-01-18', '2027-02-15', '2027-03-26', '2027-05-31', '2027-06-18', '2027-07-05',
  '2027-09-06', '2027-11-25', '2027-12-24',
]);
export const NYSE_EARLY_CLOSE = new Set(['2026-11-27', '2026-12-24', '2027-11-26']);   // 13:00 收盤
export const CALENDAR_FIRST_DAY = '2026-01-01';
export const CALENDAR_LAST_DAY = '2027-12-31';
// 上游排程 23:35 UTC（週一至週五），GitHub 實際延遲約 1.9–2.5 小時（2026-10-14～10-17 的提交時間）；
// 收盤後 8 小時內還沒發布，才算缺少該交易日。
export const PUBLISH_GRACE_HOURS = 8;
const SETTLE_MINUTES = 15;   // 收盤後 15 分鐘才算完成（沿用 v228 的 16:15）

const DAY = 86400000;
const isDay = (s) => typeof s === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(s) && new Date(s + 'T00:00:00Z').toISOString().slice(0, 10) === s;
const addDays = (s, n) => new Date(Date.parse(s + 'T00:00:00Z') + n * DAY).toISOString().slice(0, 10);

function nyParts(ms) {
  const p = Object.fromEntries(new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/New_York', year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(new Date(ms)).map((x) => [x.type, x.value]));
  return { day: `${p.year}-${p.month}-${p.day}`, minutes: Number(p.hour) * 60 + Number(p.minute) };
}

export function calendarCovers(day) {
  return isDay(day) && day >= CALENDAR_FIRST_DAY && day <= CALENDAR_LAST_DAY;
}

export function isSession(day) {
  if (!calendarCovers(day)) throw Error('CALENDAR_NOT_COVERED');
  const wd = new Date(day + 'T00:00:00Z').getUTCDay();
  return wd !== 0 && wd !== 6 && !NYSE_HOLIDAYS.has(day);
}

// 該交易日收盤後 15 分鐘的 UTC 時刻（夏令／冬令由 America/New_York 決定）
export function sessionSettledAt(day) {
  const close = (NYSE_EARLY_CLOSE.has(day) ? 13 * 60 : 16 * 60) + SETTLE_MINUTES;
  const noon = Date.parse(day + 'T12:00:00Z');
  const ny = nyParts(noon);
  const offsetMin = (ny.minutes - 12 * 60) + (ny.day < day ? -1440 : ny.day > day ? 1440 : 0);   // 紐約比 UTC 慢幾分鐘（負值）
  return Date.parse(day + 'T00:00:00Z') + (close - offsetMin) * 60000;
}

// 現在這個時刻「應該已經有」的最後一個交易日
export function expectedLatestSession(now, graceHours = PUBLISH_GRACE_HOURS) {
  let d = nyParts(now).day;
  for (let i = 0; i < 15; i++, d = addDays(d, -1)) {
    if (isSession(d) && now >= sessionSettledAt(d) + graceHours * 3600000) return d;
  }
  throw Error('NO_SESSION_FOUND');
}

// 回傳 {ok:true, observed, expected} 或 {ok:false, code, ...}；不丟例外，呼叫端照 code 顯示
export function usSectorFreshness(data, now = Date.now(), opts = {}) {
  const grace = opts.graceHours ?? PUBLISH_GRACE_HOURS;
  if (!data || typeof data !== 'object') return { ok: false, code: 'SCHEMA_MISMATCH', detail: 'root' };
  if (data.schema_version !== 1) return { ok: false, code: 'SCHEMA_MISMATCH', detail: `schema_version=${data.schema_version}` };
  if (data.source !== 'Yahoo Finance chart API (unofficial)') return { ok: false, code: 'SOURCE_MISMATCH', detail: String(data.source) };
  if (!data.histories || typeof data.histories !== 'object' || Array.isArray(data.histories) || !data.status) {
    return { ok: false, code: 'SCHEMA_MISMATCH', detail: 'histories/status' };
  }
  const captured = Date.parse(data.generated_at || '');
  if (!Number.isFinite(captured)) return { ok: false, code: 'CAPTURE_INVALID', detail: String(data.generated_at) };
  if (captured > now + 60000) return { ok: false, code: 'CAPTURE_IN_FUTURE', detail: data.generated_at };
  const spy = Array.isArray(data.histories.SPY) ? data.histories.SPY : [];
  const observed = spy.length ? spy[spy.length - 1].date : null;
  if (!isDay(observed)) return { ok: false, code: 'BENCHMARK_UNAVAILABLE' };
  let expected;
  try {
    if (!isSession(observed)) return { ok: false, code: 'NOT_A_SESSION', observed };
    expected = expectedLatestSession(now, grace);
  } catch (e) {
    return { ok: false, code: e.message, observed };   // CALENDAR_NOT_COVERED：休市日表要更新
  }
  if (captured < sessionSettledAt(observed)) return { ok: false, code: 'CAPTURE_BEFORE_CLOSE', observed, captured_at: data.generated_at };
  if (observed < expected) return { ok: false, code: 'LATEST_SESSION_MISSING', observed, expected, captured_at: data.generated_at };
  return { ok: true, observed, expected, captured_at: data.generated_at };
}
