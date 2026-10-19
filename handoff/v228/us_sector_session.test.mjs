// node --test handoff/v228/us_sector_session.test.mjs [上游 us_sector_history.json 路徑]
// 沒給路徑時用同資料夾的 fixture（macro-relay-service 提交 bdb0edd 的 data/us_sector_history.json 原檔）
import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';
import { expectedLatestSession, sessionSettledAt, usSectorFreshness, isSession } from './us_sector_session.mjs';

const here = dirname(fileURLToPath(import.meta.url));
const path = process.argv.find((a) => a.endsWith('.json')) || join(here, 'fixture_us_sector_history_bdb0edd.json');
const real = JSON.parse(readFileSync(path, 'utf8'));
const T = (s) => Date.parse(s);
const withSession = (data, day, generatedAt) => {
  const out = structuredClone(data);
  for (const id of Object.keys(out.histories)) {
    const rows = out.histories[id];
    rows.push({ date: day, close: rows[rows.length - 1].close });
    out.status[id] = { status: 'ok', observed_at: day, count: rows.length };
  }
  if (generatedAt) out.generated_at = generatedAt;
  return out;
};

test('實檔：2026-10-17 01:28Z 產生、最後一天 10-15；10-19 10:26Z 應有 10-16 → LATEST_SESSION_MISSING（不是格式錯誤）', () => {
  assert.equal(real.generated_at.slice(0, 19), '2026-10-17T01:28:36');
  assert.equal(real.histories.SPY.at(-1).date, '2026-10-15');
  const r = usSectorFreshness(real, T('2026-10-19T10:26:11.491Z'));
  assert.deepEqual([r.ok, r.code, r.observed, r.expected], [false, 'LATEST_SESSION_MISSING', '2026-10-15', '2026-10-16']);
});

test('資料補上 10-16、擷取時間不變：週一早上仍可用（舊規則 57 小時會判 UNKNOWN）', () => {
  const r = usSectorFreshness(withSession(real, '2026-10-16'), T('2026-10-19T10:26:11Z'));
  assert.deepEqual([r.ok, r.observed, r.expected], [true, '2026-10-16', '2026-10-16']);
});

test('只刷新 generated_at、資料沒變：仍是 LATEST_SESSION_MISSING', () => {
  const r = usSectorFreshness({ ...real, generated_at: '2026-10-19T09:00:00+00:00' }, T('2026-10-19T10:26:11Z'));
  assert.equal(r.code, 'LATEST_SESSION_MISSING');
});

test('收盤後 8 小時內上游還沒發布：前一個交易日仍可用；超過才算缺', () => {
  assert.equal(usSectorFreshness(real, T('2026-10-17T03:59:00Z')).ok, true);          // 10-16 收盤 20:15Z＋8h＝04:15Z
  assert.equal(usSectorFreshness(real, T('2026-10-17T04:16:00Z')).code, 'LATEST_SESSION_MISSING');
});

test('擷取時間早於最後一列的收盤：CAPTURE_BEFORE_CLOSE', () => {
  const r = usSectorFreshness(withSession(real, '2026-10-16', '2026-10-16T19:00:00+00:00'), T('2026-10-19T10:00:00Z'));
  assert.equal(r.code, 'CAPTURE_BEFORE_CLOSE');
});

test('格式、來源、擷取時間各自的錯誤碼', () => {
  const now = T('2026-10-19T10:26:11Z');
  assert.equal(usSectorFreshness({ ...real, schema_version: 2 }, now).code, 'SCHEMA_MISMATCH');
  assert.equal(usSectorFreshness({ ...real, source: 'x' }, now).code, 'SOURCE_MISMATCH');
  assert.equal(usSectorFreshness({ ...real, generated_at: 'bad' }, now).code, 'CAPTURE_INVALID');
  assert.equal(usSectorFreshness({ ...real, generated_at: '2026-10-20T00:00:00Z' }, now).code, 'CAPTURE_IN_FUTURE');
});

test('NYSE 休市日、提前收盤、夏令時間結束', () => {
  assert.equal(isSession('2026-10-16'), true);
  assert.equal(isSession('2026-11-26'), false);                                         // 感恩節
  assert.equal(expectedLatestSession(T('2026-11-27T15:00:00Z')), '2026-11-25');          // 感恩節隔天上午
  assert.equal(new Date(sessionSettledAt('2026-11-27')).toISOString(), '2026-11-27T18:15:00.000Z');   // 13:00 收盤
  assert.equal(expectedLatestSession(T('2026-11-28T02:16:00Z')), '2026-11-27');
  assert.equal(new Date(sessionSettledAt('2026-10-30')).toISOString(), '2026-10-30T20:15:00.000Z');   // 夏令
  assert.equal(new Date(sessionSettledAt('2026-11-02')).toISOString(), '2026-11-02T21:15:00.000Z');   // 冬令
  assert.equal(expectedLatestSession(T('2026-07-06T12:00:00Z')), '2026-07-02');          // 7/3 休市（獨立紀念日補假）
});

test('超出休市日表的年份：失敗而不是放行', () => {
  const data = withSession(real, '2026-10-16');
  assert.equal(usSectorFreshness(data, T('2028-01-05T12:00:00Z')).code, 'CALENDAR_NOT_COVERED');
});
