import re, shutil, datetime, pathlib, py_compile

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_trade_review_trigger_time_et_v1e_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

txt = P.read_text(encoding="utf-8", errors="replace")

# Must be inside the V1D block so we only patch the right area
if "MM_TRADE_REVIEW_ANCHOR_FROM_DB_V1D" not in txt:
    raise SystemExit("ERROR: V1D marker not found; aborting.")

old = (
"                    for r in rows:\\n"
"                        d = _row_to_dict(r) or {}\\n"
"                        if d.get('time_et') is None:\\n"
"                            d['time_et'] = _epoch_to_et_str(d.get('ts_utc'))\\n"
"                        out['buy_triggers'].append(d)\\n"
)

new = (
"                    for r in rows:\\n"
"                        d = _row_to_dict(r) or {}\\n"
"                        # V1E: always compute time_et from ts_utc (do not trust DB time_et column)\\n"
"                        _ts = d.get('ts_utc')\\n"
"                        try:\\n"
"                            _ts_ep = int(_ts) if _ts is not None else None\\n"
"                        except Exception:\\n"
"                            _ts_ep = _to_epoch(_ts)\\n"
"                        d['time_et'] = _epoch_to_et_str(_ts_ep) if _ts_ep else (d.get('time_et') or '')\\n"
"                        out['buy_triggers'].append(d)\\n"
)

if old not in txt:
    # Provide a helpful breadcrumb for drift
    i = txt.find("out['buy_triggers'] = []")
    ctx = txt[i:i+800] if i >= 0 else ""
    raise SystemExit("ERROR: Expected V1D trigger loop snippet not found (file drift). Context:\\n" + ctx)

txt2 = txt.replace(old, new, 1)
P.write_text(txt2, encoding="utf-8")
print("PATCHED: trade_review buy_triggers time_et forced from ts_utc [V1E]")
print(f"WROTE -> {P}")

py_compile.compile(str(P), doraise=True)
print("PY_COMPILE_OK")
