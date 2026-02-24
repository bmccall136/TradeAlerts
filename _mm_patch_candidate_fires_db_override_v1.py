import re,shutil,datetime,pathlib
P=pathlib.Path(r'C:\TradeAlerts\dashboard.py')
ts=datetime.datetime.now().strftime('%Y%m%d_%H%M%S')
bak=P.with_suffix(f'.py.bak_candidate_fires_db_override_v1_{ts}')
shutil.copy2(P,bak)
print(f'Backup -> {bak}')
txt=P.read_text(encoding='utf-8')
if 'MM_CANDIDATE_FIRES_DB_OVERRIDE_V1_START' in txt:
    print('SKIP: override already present'); raise SystemExit(0)
# locate function
m=re.search(r'(?ms)^def\\s+api_analytics_candidate_fires\\s*\\(.*?\\)\\s*:\\s*\\n', txt)
if not m: raise SystemExit('ERROR: def api_analytics_candidate_fires(...) not found')
ins=m.end()
block = r'''    # MM_CANDIDATE_FIRES_DB_OVERRIDE_V1_START
    # Force Candidate Fires to come from live.db trigger_fires (DB is source of truth).
    try:
        from flask import request as flask_request
    except Exception:
        flask_request = None
    try:
        import time, sqlite3
        _db = globals().get('LIVE_DB') or r'C:\\TradeAlerts\\live.db'
        _bucket = (flask_request.args.get('bucket','today').lower() if flask_request else 'today')
        _debug = (flask_request.args.get('debug','0') if flask_request else '0')
        _now = int(time.time())
        if _bucket == 'all':
            _since = 0
            _until = _now
        else:
            try:
                _since = int(globals().get('_mm_bucket_since_epoch')(_bucket))  # may exist in this file
            except Exception:
                _since = 0
            _until = _now
        con = sqlite3.connect(_db)
        con.row_factory = sqlite3.Row
        cur = con.cursor()
        cols = [r['name'] for r in cur.execute('PRAGMA table_info(trigger_fires)').fetchall()]
        # pick common columns if present, else select *
        want = []
        for c in ['ts_utc','ts_et','time_et','symbol','indicator','signal','family','score','reason','detail']:
            if c in cols and c not in want:
                want.append(c)
        sel = (', '.join(want) if want else '*')
        total = cur.execute('SELECT COUNT(*) AS n FROM trigger_fires WHERE ts_utc>=? AND ts_utc<?', (_since,_until)).fetchone()['n']
        by = cur.execute('SELECT indicator, COUNT(*) AS n FROM trigger_fires WHERE ts_utc>=? AND ts_utc<? GROUP BY indicator ORDER BY n DESC', (_since,_until)).fetchall()
        by_indicator = { (r['indicator'] if r['indicator'] is not None else 'UNKNOWN'): int(r['n']) for r in by }
        rows = [dict(r) for r in cur.execute(f'SELECT {sel} FROM trigger_fires WHERE ts_utc>=? AND ts_utc<? ORDER BY ts_utc DESC LIMIT 500', (_since,_until)).fetchall()]
        con.close()
        payload = {
            'ok': True,
            'source': 'live.db:trigger_fires',
            'bucket': _bucket,
            'window': {'since_ts_utc': int(_since), 'until_ts_utc': int(_until)},
            'total': int(total),
            'by_indicator': by_indicator,
            'rows': rows,
            'errors': []
        }
        if str(_debug) == '1':
            payload['debug'] = {'db': _db, 'cols': cols, 'select': sel, 'rows_returned': len(rows)}
        return jsonify(payload)
    except Exception as e:
        try:
            return jsonify({'ok': False, 'error': str(e), 'rows': [], 'by_indicator': {}, 'errors': [str(e)]}), 500
        except Exception:
            raise
    # MM_CANDIDATE_FIRES_DB_OVERRIDE_V1_END

'''
txt2 = txt[:ins] + block + txt[ins:]
P.write_text(txt2, encoding='utf-8')
print('PATCHED -> C:\\\\TradeAlerts\\\\dashboard.py')
