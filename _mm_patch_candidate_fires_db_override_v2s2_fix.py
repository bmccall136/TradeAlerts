import re, shutil, datetime, pathlib

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_candidate_fires_db_override_v2s2fix_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

txt = P.read_text(encoding="utf-8", errors="replace")

START = "MM_CANDIDATE_FIRES_DB_OVERRIDE_V2S_START"
END   = "MM_CANDIDATE_FIRES_DB_OVERRIDE_V2S_END"

pat = re.compile(rf"(?ms)^([ \t]*)# {START}\n.*?^([ \t]*)# {END}\n")
m = pat.search(txt)
if not m:
    raise SystemExit("ERROR: Could not find existing V2S block to replace (START/END markers missing).")

ind = m.group(1)

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
    f"{ind}    con = sqlite3.connect(_db)\n"
    f"{ind}    con.row_factory = sqlite3.Row\n"
    f"{ind}    cur = con.cursor()\n"
    f"{ind}    trig_total = int(cur.execute(\n"
    f"{ind}        'SELECT COUNT(*) n FROM trigger_fires WHERE CAST(ts_utc AS INTEGER) >= ? AND CAST(ts_utc AS INTEGER) < ?',\n"
    f"{ind}        (_since, _until)\n"
    f"{ind}    ).fetchone()['n'])\n"
    f"{ind}    sig_total = int(cur.execute(\n"
    f"{ind}        'SELECT COUNT(*) n FROM signal_fires WHERE CAST(ts_utc AS INTEGER) >= ? AND CAST(ts_utc AS INTEGER) < ?',\n"
    f"{ind}        (_since, _until)\n"
    f"{ind}    ).fetchone()['n'])\n"
    f"{ind}    by_rows = cur.execute(\n"
    f"{ind}        \"SELECT COALESCE(indicator,'UNKNOWN') indicator, COUNT(*) n \"\n"
    f"{ind}        \"FROM trigger_fires \"\n"
    f"{ind}        \"WHERE CAST(ts_utc AS INTEGER) >= ? AND CAST(ts_utc AS INTEGER) < ? \"\n"
    f"{ind}        \"GROUP BY COALESCE(indicator,'UNKNOWN') \"\n"
    f"{ind}        \"ORDER BY n DESC\",\n"
    f"{ind}        (_since, _until)\n"
    f"{ind}    ).fetchall()\n"
    f"{ind}    by_indicator = {str(r['indicator']): int(r['n']) for r in by_rows}\n"
    f"{ind}    rows = [dict(r) for r in cur.execute(\n"
    f"{ind}        \"SELECT ts_utc, symbol, indicator, score, reason \"\n"
    f"{ind}        \"FROM trigger_fires \"\n"
    f"{ind}        \"WHERE CAST(ts_utc AS INTEGER) >= ? AND CAST(ts_utc AS INTEGER) < ? \"\n"
    f"{ind}        \"ORDER BY CAST(ts_utc AS INTEGER) DESC \"\n"
    f"{ind}        \"LIMIT 500\",\n"
    f"{ind}        (_since, _until)\n"
    f"{ind}    ).fetchall()]\n"
    f"{ind}    con.close()\n"
    f"{ind}    payload = {{\n"
    f"{ind}        'ok': True,\n"
    f"{ind}        'bucket': _bucket,\n"
    f"{ind}        'since_ts_utc': int(_since),\n"
    f"{ind}        'cand': trig_total,\n"
    f"{ind}        'req': trig_total,\n"
    f"{ind}        'strict': 0,\n"
    f"{ind}        'strict_n': None,\n"
    f"{ind}        'buyable': 0,\n"
    f"{ind}        'bought': 0,\n"
    f"{ind}        'counts': {{'trigger_fires': trig_total, 'signal_fires': sig_total}},\n"
    f"{ind}        'by_indicator': by_indicator,\n"
    f"{ind}        'rows': rows,\n"
    f"{ind}        'source': 'live.db:trigger_fires',\n"
    f"{ind}    }}\n"
    f"{ind}    if _debug == '1':\n"
    f"{ind}        payload['debug'] = {{'db': _db, 'rows_returned': len(rows), 'since': int(_since), 'until': int(_until)}}\n"
    f"{ind}    return jsonify(payload)\n"
    f"{ind}except Exception as e:\n"
    f"{ind}    try:\n"
    f"{ind}        from flask import jsonify\n"
    f"{ind}        return jsonify({{'ok': False, 'error': str(e), 'rows': [], 'by_indicator': {{}}, 'cand': 0, 'req': 0, 'counts': {{'trigger_fires': 0, 'signal_fires': 0}}}}), 500\n"
    f"{ind}    except Exception:\n"
    f"{ind}        raise\n"
    f"{ind}# {END}\n"
)

new_txt = txt[:m.start()] + blk + txt[m.end():]
P.write_text(new_txt, encoding="utf-8")
print(r"PATCHED -> C:\TradeAlerts\dashboard.py")
print("Replaced block -> V2S2 (schema-compatible)")
