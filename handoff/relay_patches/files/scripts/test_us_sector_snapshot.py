import datetime as dt
import unittest
import math
from check_us_sector_snapshot import validate,TICKERS
class SnapshotTests(unittest.TestCase):
    def make_data(self, end=dt.date(2026,10,13)):
        rows=[{'date':(end-dt.timedelta(days=20-i)).isoformat(),'close':100+i} for i in range(21)]
        return {'schema_version':1,'histories':{t:list(rows) for t in TICKERS},'status':{t:{'status':'ok','observed_at':end.isoformat()} for t in TICKERS}}
    def test_missing(self):
        result=validate({},dt.datetime(2026,10,14,tzinfo=dt.timezone.utc))
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertIn('SYMBOL_COVERAGE',result['issues'])
    def test_complete(self):
        result=validate(self.make_data(),dt.datetime(2026,10,14,tzinfo=dt.timezone.utc))
        self.assertEqual(result['status'],'OK')
    def test_stale(self):
        result=validate(self.make_data(dt.date(2026,9,20)),dt.datetime(2026,10,14,tzinfo=dt.timezone.utc))
        self.assertIn('STALE_OR_FUTURE_DATA',result['issues'])
    def test_non_finite_prices(self):
        for price in (float('nan'),float('inf'),float('-inf'),True):
            with self.subTest(price=repr(price)):
                data=self.make_data()
                data['histories']['SPY'][0]['close']=price
                result=validate(data,dt.datetime(2026,10,14,tzinfo=dt.timezone.utc))
                self.assertIn('SPY:BAD_PRICE',result['issues'])
    def test_invalid_row_date(self):
        data=self.make_data()
        data['histories']['SPY'][0]['date']='2026-09-31'
        result=validate(data,dt.datetime(2026,10,14,tzinfo=dt.timezone.utc))
        self.assertIn('SPY:INVALID_ROW_DATE',result['issues'])
    def test_session_mismatch_same_latest_date(self):
        data=self.make_data()
        rows=data['histories']['XLK']
        prior=(dt.date.fromisoformat(rows[0]['date'])-dt.timedelta(days=1)).isoformat()
        data['histories']['XLK']=[{'date':prior,'close':99}]+rows[:8]+rows[9:]
        now=dt.datetime(2026,10,14,tzinfo=dt.timezone.utc)
        result=validate(data,now)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertIn('XLK:TRADING_SESSIONS_MISMATCH',result['issues'])
        self.assertNotIn('XLK:DATE_MISMATCH',result['issues'])
    def test_malformed_input_fails_closed(self):
        now=dt.datetime(2026,10,14,tzinfo=dt.timezone.utc)
        self.assertEqual(validate([],now)['status'],'UNKNOWN')
        self.assertIn('INVALID_ROOT',validate(None,now)['issues'])
        for bad in ([], 'bad', 7):
            data=self.make_data()
            data['histories']=bad
            self.assertIn('INVALID_CONTAINERS',validate(data,now)['issues'])
        data=self.make_data()
        data['histories']['SPY'][-1]=None
        result=validate(data,now)
        self.assertEqual(result['status'],'UNKNOWN')
        self.assertIn('SPY:BAD_PRICE',result['issues'])
        data=self.make_data()
        data['status']['SPY']='corrupt'
        self.assertIn('SPY:MISSING_HISTORY',validate(data,now)['issues'])
        data=self.make_data()
        data['histories']['SPY']='corrupt'
        self.assertIn('SPY:MISSING_HISTORY',validate(data,now)['issues'])
    def test_latest_session_missing_real_case(self):
        # Published 2026-10-17 01:28Z (Fri 21:28 ET, after the close) with the last row 10-15: one session missing.
        data=self.make_data(dt.date(2026,10,15))
        result=validate(data,dt.datetime(2026,10,17,1,28,36,tzinfo=dt.timezone.utc))
        self.assertIn('LATEST_SESSION_MISSING:expected 2026-10-16',result['issues'])
        self.assertEqual(result['status'],'UNKNOWN')
        # Before the 10-16 close the 10-15 session is the latest one that must be present.
        self.assertEqual(validate(data,dt.datetime(2026,10,16,19,0,tzinfo=dt.timezone.utc))['status'],'OK')
    def test_weekend_and_holiday(self):
        data=self.make_data(dt.date(2026,10,16))
        self.assertEqual(validate(data,dt.datetime(2026,10,19,10,26,tzinfo=dt.timezone.utc))['status'],'OK')
        data=self.make_data(dt.date(2026,11,25))   # Thanksgiving 11-26 closed
        self.assertEqual(validate(data,dt.datetime(2026,11,27,15,0,tzinfo=dt.timezone.utc))['status'],'OK')
    def test_calendar_not_covered_fails_closed(self):
        data=self.make_data(dt.date(2028,1,4))
        self.assertIn('CALENDAR_NOT_COVERED',validate(data,dt.datetime(2028,1,5,12,0,tzinfo=dt.timezone.utc))['issues'])
if __name__=='__main__':unittest.main()
