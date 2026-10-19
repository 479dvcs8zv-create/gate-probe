import datetime as dt
import json
import math
import pathlib
import sys
from us_market_calendar import expected_latest_session
TICKERS={'SPY','XLK','XLC','XLY','XLP','XLF','XLI','XLV','XLE','XLB','XLU','XLRE'}
def validate(data, now=None):
    now=now or dt.datetime.now(dt.timezone.utc)
    issues=[]
    if not isinstance(data,dict):return {'status':'UNKNOWN','coverage':0,'observed_at':None,'issues':['INVALID_ROOT']}
    if data.get('schema_version')!=1:issues.append('SCHEMA_MISMATCH')
    status=data.get('status',{})
    histories=data.get('histories',{})
    if not isinstance(status,dict) or not isinstance(histories,dict):return {'status':'UNKNOWN','coverage':0,'observed_at':None,'issues':['INVALID_CONTAINERS']}
    if set(status)!=TICKERS or set(histories)!=TICKERS:issues.append('SYMBOL_COVERAGE')
    dates=set()
    spy_rows=histories.get('SPY')
    spy_dates=[row.get('date') for row in spy_rows[-21:]] if isinstance(spy_rows,list) and len(spy_rows)>=21 and all(isinstance(row,dict) for row in spy_rows[-21:]) else None
    for ticker in sorted(TICKERS):
        item=status.get(ticker) or {}
        rows=histories.get(ticker) or []
        if not isinstance(item,dict) or not isinstance(rows,list) or item.get('status')!='ok' or len(rows)<21:
            issues.append(ticker+':MISSING_HISTORY')
            continue
        observed_at=item.get('observed_at')
        if not isinstance(observed_at,str):issues.append(ticker+':INVALID_DATE');continue
        dates.add(observed_at)
        if not isinstance(rows[-1],dict) or rows[-1].get('date')!=observed_at:issues.append(ticker+':DATE_MISMATCH')
        if any(not isinstance(row,dict) or isinstance(row.get('close'),bool) or not isinstance(row.get('close'),(int,float)) or not math.isfinite(row['close']) or row['close']<=0 for row in rows):issues.append(ticker+':BAD_PRICE')
        parsed=[]
        for row in rows:
            try:
                day=dt.date.fromisoformat(row['date'])
                if day.isoformat()!=row['date']:raise ValueError()
                parsed.append(day)
            except (AttributeError,KeyError,TypeError,ValueError):issues.append(ticker+':INVALID_ROW_DATE');break
        if parsed and (parsed!=sorted(set(parsed))):issues.append(ticker+':NON_MONOTONIC_DATES')
        if ticker!='SPY' and spy_dates is not None and len(parsed)==len(rows) and len(parsed)>=21 and [row['date'] for row in rows[-21:]]!=spy_dates:
            issues.append(ticker+':TRADING_SESSIONS_MISMATCH')
    if len(dates)!=1:issues.append('DATES_NOT_ALIGNED')
    observed=next(iter(dates)) if len(dates)==1 else None
    if observed:
        try:
            age=(now.date()-dt.date.fromisoformat(observed)).days
            if age<0 or age>5:issues.append('STALE_OR_FUTURE_DATA')
        except (TypeError,ValueError):issues.append('INVALID_DATE')
        try:
            # A five-day window cannot see one missing session (2026-10-16 was absent from the 10-16 21:28 ET run).
            # The site reader allows PUBLISH_GRACE_HOURS; the publisher itself does not.
            expected=expected_latest_session(now,grace_hours=0)   # the publisher runs after the close: no grace
            if dt.date.fromisoformat(observed)<expected:issues.append('LATEST_SESSION_MISSING:expected '+expected.isoformat())
        except ValueError as exc:issues.append(str(exc) if str(exc) in ('CALENDAR_NOT_COVERED','NO_SESSION_FOUND') else 'INVALID_DATE')
    return {'status':'OK' if not issues else 'UNKNOWN','coverage':sum(isinstance(status.get(t),dict) and status[t].get('status')=='ok' for t in TICKERS),'observed_at':observed,'issues':issues}
if __name__=='__main__':
    payload=json.loads(pathlib.Path(sys.argv[1]).read_text(encoding='utf-8'))
    result=validate(payload)
    print(json.dumps(result,ensure_ascii=False))
    if result['status']!='OK':sys.exit(1)
