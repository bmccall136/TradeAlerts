import shutil, datetime, pathlib, re

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_force_candidate_fires_canonical_v3d_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

txt = P.read_text(encoding="utf-8", errors="replace")

ROUTE_PAT = re.compile(r'(?m)^@app\.route\(\s*([\'"])/api/analytics/candidate_fires\1([^)]*)\)\s*$')
routes = list(ROUTE_PAT.finditer(txt))
print("Found candidate_fires route decorators ->", len(routes))
if not routes:
    raise SystemExit("ERROR: No @app.route('/api/analytics/candidate_fires') found.")

# 1) Disable duplicates (2nd+ occurrences) by renaming their route path
if len(routes) > 1:
    out = []
    last = 0
    disabled = 0
    for idx, m in enumerate(routes):
        if idx == 0:
            continue
        out.append(txt[last:m.start()])
        last = m.end()
        q = m.group(1)
        args = m.group(2)
        disabled += 1
        out.append(f"@app.route({q}/api/analytics/candidate_fires__disabled_{disabled}{q}{args})")
    out.append(txt[last:])
    txt = "".join(out)
    print("Disabled duplicate routes ->", disabled)

# 2) Inject canonical early-return block under the FIRST handler def
# Find the def line immediately following the first decorator (after duplicates renaming above)
m0 = ROUTE_PAT.search(txt)
if not m0:
    raise SystemExit("ERROR: Could not re-find first route after edits.")

# Locate the def line after the decorator
def_m = re.search(r'(?m)^\s*def\s+([A-Za-z0-9_]+)\s*\(\s*\)\s*:\s*$', txt[m0.end():])
if not def_m:
    raise SystemExit("ERROR: Could not find def ...(): line after first candidate_fires decorator.")
def_name = def_m.group(1)
def_line_start = m0.end() + def_m.start()
def_line_end = m0.end() + def_m.end()

# Determine indentation for the function body (indent of def + 4 spaces)
ind_m = re.match(r'(?m)^(?P<ind>[ \t]*)def', txt[def_line_start:def_line_end])
def_ind = ind_m.group("ind") if ind_m else ""
body_ind = def_ind + "    "

MARK = "MM_CANDIDATE_FIRES_CANONICAL_V3D"
if MARK in txt:
    print("SKIP: already patched (marker found).")
    P.write_text(txt, encoding="utf-8")
    raise SystemExit(0)

blk = (
    f"{body_ind}# {MARK}_START\n"
    f"{body_ind}# NOTE: This early-return block forces a schema-adaptive live.db backed response.\n"
    f"{body_ind}try:\n"
    f"{body_ind}    import time, sqlite3\n"
    f"{body_ind}    from flask import request, jsonify\n"
    f"{body_ind}    _db = globals().get('LIVE_DB') or r'C:\\\\TradeAlerts\\\\live.db'\n"
    f"{body_ind}    _bucket = (request.args.get('bucket','today') or 'today').lower()\n"
    f"{body_ind}    _debug = str(request.args.get('debug','0'))\n"
    f"{body_ind}    _now = int(time.time())\n"
    f"{body_ind}    if _bucket == 'all':\n"
    f"{body_ind}        _since = 0; _until = _now\n"
    f"{body_ind}    else:\n"
    f"{body_ind}        fn = globals().get('_mm_bucket_since_epoch')\n"
    f"{body_ind}        try:\n"
    f"{body_ind}            _since = int(fn(_bucket)) if fn else 0\n"
    f"{body_ind}        except Exception:\n"
    f"{body_ind}            _since = 0\n"
    f"{body_ind}        _until = _now\n"
    f"{body_ind}\n"
    f"{body_ind}    con = sqlite3.connect(_db)\n"
    f"{body_ind}    con.row_factory = sqlite3.Row\n"
    f"{body_ind}    cur = con.cursor()\n"
    f"{body_ind}\n"
    f"{body_ind}    cols = [r['name'] for r in cur.execute('PRAGMA table_info(trigger_fires)').fetchall()]\n"
    f"{body_ind}    colset = set(cols)\n"
    f"{body_ind}    pref = ['indicator','trigger','signal','name','type','family','reason']\n"
    f"{body_ind}    group_col = next((c for c in pref if c in colset), None)\n"
    f"{body_ind}\n"
    f"{body_ind}    trig_total = int(cur.execute(\n"
    f"{body_ind}        'SELECT COUNT(*) n FROM trigger_fires WHERE CAST(ts_utc AS INTEGER) >= ? AND CAST(ts_utc AS INTEGER) < ?',\n"
    f"{body_ind}        (_since, _until)\n"
    f"{body_ind}    ).fetchone()['n'])\n"
    f"{body_ind}\n"
    f"{body_ind}    sig_total = None\n"
    f"{body_ind}    if cur.execute(\"SELECT name FROM sqlite_master WHERE type='table' AND name='signal_fires'\").fetchone():\n"
    f"{body_ind}        try:\n"
    f"{body_ind}            sig_total = int(cur.execute(\n"
    f"{body_ind}                'SELECT COUNT(*) n FROM signal_fires WHERE CAST(ts_utc AS INTEGER) >= ? AND CAST(ts_utc AS INTEGER) < ?',\n"
    f"{body_ind}                (_since, _until)\n"
    f"{body_ind}            ).fetchone()['n'])\n"
    f"{body_ind}        except Exception:\n"
    f"{body_ind}            sig_total = None\n"
    f"{body_ind}\n"
    f"{body_ind}    by_indicator = {{}}\n"
    f"{body_ind}    if group_col:\n"
    f"{body_ind}        q = (\n"
    f"{body_ind}            \"SELECT COALESCE(\" + group_col + \", 'UNKNOWN') AS k, COUNT(*) AS n \"\n"
    f"{body_ind}            \"FROM trigger_fires \"\n"
    f"{body_ind}            \"WHERE CAST(ts_utc AS INTEGER) >= ? AND CAST(ts_utc AS INTEGER) < ? \"\n"
    f"{body_ind}            \"GROUP BY COALESCE(\" + group_col + \", 'UNKNOWN') \"\n"
    f"{body_ind}            \"ORDER BY n DESC\"\n"
    f"{body_ind}        )\n"
    f"{body_ind}        for r in cur.execute(q, (_since, _until)).fetchall():\n"
    f"{body_ind}            by_indicator[str(r['k'])] = int(r['n'])\n"
    f"{body_ind}    else:\n"
    f"{body_ind}        by_indicator = {{'UNKNOWN': int(trig_total)}}\n"
    f"{body_ind}\n"
    f"{body_ind}    want = ['ts_utc','symbol']\n"
    f"{body_ind}    if group_col and group_col not in want:\n"
    f"{body_ind}        want.append(group_col)\n"
    f"{body_ind}    for c in ['score','detail','details','note','meta','overlay_json','reason']:\n"
    f"{body_ind}        if c in colset and c not in want:\n"
    f"{body_ind}            want.append(c)\n"
    f"{body_ind}\n"
    f"{body_ind}    sel = ', '.join(want)\n"
    f"{body_ind}    sql_rows = (\n"
    f"{body_ind}        'SELECT ' + sel + ' FROM trigger_fires '\n"
    f"{body_ind}        'WHERE CAST(ts_utc AS INTEGER) >= ? AND CAST(ts_utc AS INTEGER) < ? '\n"
    f"{body_ind}        'ORDER BY CAST(ts_utc AS INTEGER) DESC LIMIT 500'\n"
    f"{body_ind}    )\n"
    f"{body_ind}    rows = [dict(r) for r in cur.execute(sql_rows, (_since, _until)).fetchall()]\n"
    f"{body_ind}\n"
    f"{body_ind}    con.close()\n"
    f"{body_ind}\n"
    f"{body_ind}    payload = {{\n"
    f"{body_ind}        'ok': True,\n"
    f"{body_ind}        'bucket': _bucket,\n"
    f"{body_ind}        'since_ts_utc': int(_since),\n"
    f"{body_ind}        'cand': int(trig_total),\n"
    f"{body_ind}        'req': int(trig_total),\n"
    f"{body_ind}        'strict': 0,\n"
    f"{body_ind}        'strict_n': None,\n"
    f"{body_ind}        'buyable': 0,\n"
    f"{body_ind}        'bought': 0,\n"
    f"{body_ind}        'counts': {{'trigger_fires': int(trig_total), 'signal_fires': sig_total}},\n"
    f"{body_ind}        'by_indicator': by_indicator,\n"
    f"{body_ind}        'rows': rows,\n"
    f"{body_ind}        'source': 'live.db:trigger_fires',\n"
    f"{body_ind}    }}\n"
    f"{body_ind}    if _debug == '1':\n"
    f"{body_ind}        payload['debug'] = {{'db': _db, 'rows_returned': len(rows), 'since': int(_since), 'until': int(_until), 'trigger_fires_cols': cols, 'group_col': group_col, 'handler': '{def_name}'}}\n"
    f"{body_ind}    return jsonify(payload)\n"
    f"{body_ind}except Exception as e:\n"
    f"{body_ind}    # HTTP 200 on purpose so Invoke-WebRequest doesn't throw\n"
    f"{body_ind}    try:\n"
    f"{body_ind}        from flask import jsonify\n"
    f"{body_ind}        return jsonify({{'ok': False, 'error': str(e), 'errors': [str(e)], 'rows': [], 'by_indicator': {{}}, 'cand': 0, 'req': 0, 'counts': {{'trigger_fires': 0, 'signal_fires': 0}}, 'source': 'live.db:trigger_fires', 'debug': {{'handler': '{def_name}'}}}})\n"
    f"{body_ind}    except Exception:\n"
    f"{body_ind}        raise\n"
    f"{body_ind}# {MARK}_END\n"
)

# Insert block right after the def line (def_line_end includes the newline end of def line)
new_txt = txt[:def_line_end] + "\n" + blk + txt[def_line_end:]
P.write_text(new_txt, encoding="utf-8")
print(r"PATCHED -> C:\TradeAlerts\dashboard.py")
print("Canonical handler forced under def ->", def_name)
