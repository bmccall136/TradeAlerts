import shutil, datetime, pathlib, re

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_candidate_fires_schema_adaptive_v3c_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

txt = P.read_text(encoding="utf-8", errors="replace")

START = "MM_CANDIDATE_FIRES_DB_OVERRIDE_V2S_START"
END   = "MM_CANDIDATE_FIRES_DB_OVERRIDE_V2S_END"

pat = re.compile(rf"(?ms)^(?P<ind>[ \t]*)# {START}\n.*?^(?P=ind)# {END}\n")
m = pat.search(txt)
if not m:
    raise SystemExit("ERROR: Could not find existing V2S START/END block to replace.")

ind = m.group("ind")

blk = (
    f"{ind}# {START}\n"
    f"{ind}try:\n"
    f"{ind}    import time, sqlite3\n"
    f"{ind}    from flask import request, jsonify\n"
    f"{ind}    _db = globals().get('LIVE_DB') or r'C:\\TradeAlerts\\live.db'\n"
    f"{ind}    _bucket = (request.args.get('bucket','today') or 'today').lower()\n"
    f"{ind}    _debug = str(request.args.get('debug','0'))\n"
    f"{ind}    _now = int(time.time())\n"
    f"{ind}    if _bucket == 'all':\n"
    f"{ind}        _since = 0; _until = _now\n"
    f"{ind}    else:\n"
    f"{ind}        fn = globals().get('_mm_bucket_since_epoch')\n"
    f"{ind}        try:\n"
    f"{ind}            _since = int(fn(_bucket)) if fn else 0\n"
    f"{ind}        except Exception:\n"
    f"{ind}            _since = 0\n"
    f"{ind}        _until = _now\n"
    f"{ind}\n"
    f"{ind}    con = sqlite3.connect(_db)\n"
    f"{ind}    con.row_factory = sqlite3.Row\n"
    f"{ind}    cur = con.cursor()\n"
    f"{ind}\n"
    f"{ind}    cols = [r['name'] for r in cur.execute('PRAGMA table_info(trigger_fires)').fetchall()]\n"
    f"{ind}    colset = set(cols)\n"
    f"{ind}    pref = ['indicator','trigger','signal','name','type','family','reason']\n"
    f"{ind}    group_col = next((c for c in pref if c in colset), None)\n"
    f"{ind}\n"
    f"{ind}    trig_total = int(cur.execute(\n"
    f"{ind}        'SELECT COUNT(*) n FROM trigger_fires WHERE CAST(ts_utc AS INTEGER) >= ? AND CAST(ts_utc AS INTEGER) < ?',\n"
    f"{ind}        (_since, _until)\n"
    f"{ind}    ).fetchone()['n'])\n"
    f"{ind}\n"
    f"{ind}    sig_total = None\n"
    f"{ind}    if cur.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='signal_fires'\").fetchone():\n"
    f"{ind}        try:\n"
    f"{ind}            sig_total = int(cur.execute(\n"
    f"{ind}                'SELECT COUNT(*) n FROM signal_fires WHERE CAST(ts_utc AS INTEGER) >= ? AND CAST(ts_utc AS INTEGER) < ?',\n"
    f"{ind}                (_since, _until)\n"
    f"{ind}            ).fetchone()['n'])\n"
    f"{ind}        except Exception:\n"
    f"{ind}            sig_total = None\n"
    f"{ind}\n"
    f"{ind}    by_indicator = {{}}\n"
    f"{ind}    if group_col:\n"
    f"{ind}        q = (\n"
    f"{ind}            \"SELECT COALESCE(\" + group_col + \", 'UNKNOWN') AS k, COUNT(*) AS n \"\n"
    f"{ind}            \"FROM trigger_fires \"\n"
    f"{ind}            \"WHERE CAST(ts_utc AS INTEGER) >= ? AND CAST(ts_utc AS INTEGER) < ? \"\n"
    f"{ind}            \"GROUP BY COALESCE(\" + group_col + \", 'UNKNOWN') \"\n"
    f"{ind}            \"ORDER BY n DESC\"\n"
    f"{ind}        )\n"
    f"{ind}        for r in cur.execute(q, (_since, _until)).fetchall():\n"
    f"{ind}            by_indicator[str(r['k'])] = int(r['n'])\n"
    f"{ind}    else:\n"
    f"{ind}        by_indicator = {{'UNKNOWN': int(trig_total)}}\n"
    f"{ind}\n"
    f"{ind}    want = ['ts_utc','symbol']\n"
    f"{ind}    if group_col and group_col not in want:\n"
    f"{ind}        want.append(group_col)\n"
    f"{ind}    for c in ['score','reason','detail','details','note','meta','overlay_json']:\n"
    f"{ind}        if c in colset and c not in want:\n"
    f"{ind}            want.append(c)\n"
    f"{ind}\n"
    f"{ind}    sel = ', '.join(want)\n"
    f"{ind}    sql_rows = (\n"
    f"{ind}        'SELECT ' + sel + ' FROM trigger_fires '\n"
    f"{ind}        'WHERE CAST(ts_utc AS INTEGER) >= ? AND CAST(ts_utc AS INTEGER) < ? '\n"
    f"{ind}        'ORDER BY CAST(ts_utc AS INTEGER) DESC LIMIT 500'\n"
    f"{ind}    )\n"
    f"{ind}    rows = [dict(r) for r in cur.execute(sql_rows, (_since, _until)).fetchall()]\n"
    f"{ind}\n"
    f"{ind}    con.close()\n"
    f"{ind}\n"
    f"{ind}    payload = {{\n"
    f"{ind}        'ok': True,\n"
    f"{ind}        'bucket': _bucket,\n"
    f"{ind}        'since_ts_utc': int(_since),\n"
    f"{ind}        'cand': int(trig_total),\n"
    f"{ind}        'req': int(trig_total),\n"
    f"{ind}        'strict': 0,\n"
    f"{ind}        'strict_n': None,\n"
    f"{ind}        'buyable': 0,\n"
    f"{ind}        'bought': 0,\n"
    f"{ind}        'counts': {{'trigger_fires': int(trig_total), 'signal_fires': sig_total}},\n"
    f"{ind}        'by_indicator': by_indicator,\n"
    f"{ind}        'rows': rows,\n"
    f"{ind}        'source': 'live.db:trigger_fires',\n"
    f"{ind}    }}\n"
    f"{ind}    if _debug == '1':\n"
    f"{ind}        payload['debug'] = {{'db': _db, 'rows_returned': len(rows), 'since': int(_since), 'until': int(_until), 'trigger_fires_cols': cols, 'group_col': group_col}}\n"
    f"{ind}    return jsonify(payload)\n"
    f"{ind}except Exception as e:\n"
    f"{ind}    try:\n"
    f"{ind}        from flask import jsonify\n"
    f"{ind}        return jsonify({{'ok': False, 'error': str(e), 'errors': [str(e)], 'rows': [], 'by_indicator': {{}}, 'cand': 0, 'req': 0, 'counts': {{'trigger_fires': 0, 'signal_fires': 0}}}})\n"
    f"{ind}    except Exception:\n"
    f"{ind}        raise\n"
    f"{ind}# {END}\n"
)

new_txt = txt[:m.start()] + blk + txt[m.end():]
P.write_text(new_txt, encoding="utf-8")
print(r"PATCHED -> C:\TradeAlerts\dashboard.py")
print("Replaced V2S block -> schema-adaptive V3c (slice replace; no re.sub template escapes)")
