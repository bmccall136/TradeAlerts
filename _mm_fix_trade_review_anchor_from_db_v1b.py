import re, shutil, datetime, pathlib, sys

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
if not P.exists():
    raise SystemExit(f"Missing: {P}")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_trade_review_anchor_v1b_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

txt = P.read_text(encoding="utf-8", errors="replace")

# Locate the /api/trade_review route + function
route_pat = re.compile(r"(?m)^\s*@app\.route\(\s*['\"]/api/trade_review['\"]\s*\)\s*$")
m_route = route_pat.search(txt)
if not m_route:
    raise SystemExit("ERROR: Could not find @app.route('/api/trade_review')")

# Find the def line right after the decorator
def_pat = re.compile(r"(?m)^\s*def\s+api_trade_review\s*\(\s*\)\s*:\s*$")
m_def = def_pat.search(txt, m_route.end())
if not m_def:
    raise SystemExit("ERROR: Could not find def api_trade_review() after route decorator")

start = m_route.start()

# End = next @app.route after this function OR end of file
next_route = re.search(r"(?m)^\s*@app\.route\(", txt[m_def.end():])
end = (m_def.end() + next_route.start()) if next_route else len(txt)

api_repl = (
"@app.route('/api/trade_review')\n"
"def api_trade_review():\n"
"    # --- MM_TRADE_REVIEW_ANCHOR_FROM_DB_V1B ---\n"
"    # DB-anchored Trade Review payload:\n"
"    # - Anchor is BUY timestamp (from trades BUY row)\n"
"    # - buy/sell prices hydrate so UI stops showing 0.00\n"
"    # - triggers pulled around BUY (and SELL if present)\n"
"    out = {\"buys\": [], \"sells\": [], \"buy_triggers\": [], \"sell_triggers\": [], \"errors\": [], \"meta\": {}}\n"
"    try:\n"
"        import sqlite3\n"
"        from datetime import datetime, timezone\n"
"        trade_id = request.args.get(\"trade_id\", type=int)\n"
"        symbol_q = (request.args.get(\"symbol\") or \"\").strip().upper()\n"
"\n"
"        def _row_to_dict(r):\n"
"            if r is None:\n"
"                return None\n"
"            try:\n"
"                return dict(r)\n"
"            except Exception:\n"
"                return {k: r[k] for k in r.keys()}\n"
"\n"
"        def _ts_et_from_utc_epoch(tsu):\n"
"            try:\n"
"                if \"_mm_ts_to_et\" in globals():\n"
"                    return _mm_ts_to_et(int(tsu))\n"
"            except Exception:\n"
"                pass\n"
"            try:\n"
"                import pytz\n"
"                et = pytz.timezone(\"America/New_York\")\n"
"                dt = datetime.fromtimestamp(int(tsu), tz=timezone.utc).astimezone(et)\n"
"                return dt.strftime(\"%m/%d/%Y, %I:%M %p\")\n"
"            except Exception:\n"
"                return \"\"\n"
"\n"
"        con = sqlite3.connect(LIVE_DB)\n"
"        con.row_factory = sqlite3.Row\n"
"        cur = con.cursor()\n"
"\n"
"        trade = None\n"
"        if trade_id:\n"
"            trade = cur.execute(\"SELECT * FROM trades WHERE id=?\", (int(trade_id),)).fetchone()\n"
"        elif symbol_q:\n"
"            trade = cur.execute(\n"
"                \"SELECT * FROM trades WHERE UPPER(symbol)=? AND UPPER(COALESCE(action,'')) IN ('BUY','BOT','BUY_FILLED','BUY_EXECUTED') \"\n"
"                \"ORDER BY id DESC LIMIT 1\",\n"
"                (symbol_q,)\n"
"            ).fetchone()\n"
"            if trade is None:\n"
"                trade = cur.execute(\n"
"                    \"SELECT * FROM trades WHERE UPPER(symbol)=? ORDER BY id DESC LIMIT 1\",\n"
"                    (symbol_q,)\n"
"                ).fetchone()\n"
"\n"
"        trade_d = _row_to_dict(trade) or {}\n"
"        sym = (trade_d.get(\"symbol\") or symbol_q or \"\").upper().strip()\n"
"\n"
"        act = (trade_d.get(\"action\") or \"\").upper().strip()\n"
"\n"
"        # BUY anchor: if selected trade isn't a BUY, find most recent BUY for this symbol.\n"
"        buy_row = None\n"
"        if sym:\n"
"            if act in ('BUY','BOT','BUY_FILLED','BUY_EXECUTED'):\n"
"                buy_row = trade\n"
"            else:\n"
"                buy_row = cur.execute(\n"
"                    \"SELECT * FROM trades WHERE UPPER(symbol)=? AND UPPER(COALESCE(action,'')) IN ('BUY','BOT','BUY_FILLED','BUY_EXECUTED') \"\n"
"                    \"ORDER BY id DESC LIMIT 1\",\n"
"                    (sym,)\n"
"                ).fetchone()\n"
"\n"
"        buy_d = _row_to_dict(buy_row) or {}\n"
"\n"
"        def _to_int(x):\n"
"            try:\n"
"                return int(x)\n"
"            except Exception:\n"
"                return None\n"
"        def _to_float(x):\n"
"            try:\n"
"                return float(x)\n"
"            except Exception:\n"
"                return None\n"
"\n"
"        buy_ts = _to_int(buy_d.get('ts_utc') or buy_d.get('ts') or buy_d.get('timestamp'))\n"
"        buy_price = _to_float(buy_d.get('price') or buy_d.get('fill_price') or buy_d.get('avg_price'))\n"
"        qty = _to_float(buy_d.get('qty') or buy_d.get('quantity') or trade_d.get('qty') or trade_d.get('quantity'))\n"
"\n"
"        sell_ts = None\n"
"        sell_price = None\n"
"        if act in ('SELL','SOLD','SELL_FILLED','SELL_EXECUTED'):\n"
"            sell_ts = _to_int(trade_d.get('ts_utc') or trade_d.get('ts') or trade_d.get('timestamp'))\n"
"            sell_price = _to_float(trade_d.get('price') or trade_d.get('fill_price') or trade_d.get('avg_price'))\n"
"\n"
"        win = request.args.get('win_secs', type=int) or 900\n"
"        if buy_ts and sym:\n"
"            lo = int(buy_ts) - int(win)\n"
"            hi = int(buy_ts) + int(win)\n"
"            try:\n"
"                rows = cur.execute(\n"
"                    \"SELECT * FROM trigger_fires WHERE UPPER(symbol)=? AND COALESCE(ts_utc,0) BETWEEN ? AND ? ORDER BY COALESCE(ts_utc,0) ASC\",\n"
"                    (sym, lo, hi)\n"
"                ).fetchall()\n"
"                out['buy_triggers'] = [_row_to_dict(r) for r in rows]\n"
"            except Exception as e:\n"
"                out['errors'].append('buy_triggers query failed: ' + str(e))\n"
"\n"
"            if sell_ts:\n"
"                slo = int(sell_ts) - int(win)\n"
"                shi = int(sell_ts) + int(win)\n"
"                try:\n"
"                    rows = cur.execute(\n"
"                        \"SELECT * FROM sell_events WHERE UPPER(symbol)=? AND COALESCE(ts_utc,0) BETWEEN ? AND ? ORDER BY COALESCE(ts_utc,0) ASC\",\n"
"                        (sym, slo, shi)\n"
"                    ).fetchall()\n"
"                    out['sell_triggers'] = [_row_to_dict(r) for r in rows]\n"
"                except Exception as e:\n"
"                    out['errors'].append('sell_triggers query failed: ' + str(e))\n"
"\n"
"        out['meta'] = {\n"
"            'symbol': sym,\n"
"            'trade_id': int(trade_id) if trade_id else (trade_d.get('id') or None),\n"
"            'buy_ts_utc': buy_ts,\n"
"            'buy_time_et': _ts_et_from_utc_epoch(buy_ts) if buy_ts else '',\n"
"            'buy_price': buy_price,\n"
"            'sell_ts_utc': sell_ts,\n"
"            'sell_time_et': _ts_et_from_utc_epoch(sell_ts) if sell_ts else '',\n"
"            'sell_price': sell_price,\n"
"            'qty': qty,\n"
"            'anchor_ts_utc': buy_ts,\n"
"            'win_secs': win,\n"
"        }\n"
"\n"
"        con.close()\n"
"    except Exception as e:\n"
"        out['errors'].append('api_trade_review exception: ' + str(e))\n"
"    return jsonify(out)\n"
"    # --- /MM_TRADE_REVIEW_ANCHOR_FROM_DB_V1B ---\n"
)

txt_new = txt[:start] + api_repl + txt[end:]
P.write_text(txt_new, encoding="utf-8")
print("PATCHED: /api/trade_review -> MM_TRADE_REVIEW_ANCHOR_FROM_DB_V1B")
print(f"WROTE -> {P}")

import py_compile
py_compile.compile(str(P), doraise=True)
print("PY_COMPILE_OK")
print("DONE. If Trade Review page still shows 0.00, restart dashboard. Test endpoints:")
print("  http://127.0.0.1:5001/api/trade_review?symbol=PG")
print("  http://127.0.0.1:5001/api/trade_review?symbol=PNW")
