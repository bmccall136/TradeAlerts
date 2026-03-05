import re, shutil, datetime, pathlib, py_compile

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_trade_review_trigger_time_et_v1e2_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

txt = P.read_text(encoding="utf-8", errors="replace")

if "MM_TRADE_REVIEW_ANCHOR_FROM_DB_V1D" not in txt:
    raise SystemExit("ERROR: V1D marker not found; aborting.")

# Work only inside the V1D block to avoid collateral edits
m_blk = re.search(r"(?s)# --- MM_TRADE_REVIEW_ANCHOR_FROM_DB_V1D ---.*?# --- /MM_TRADE_REVIEW_ANCHOR_FROM_DB_V1D ---", txt)
if not m_blk:
    raise SystemExit("ERROR: Could not isolate V1D block.")

blk = m_blk.group(0)

# Replace the inner trigger loop (indentation-agnostic)
pat = re.compile(
    r"(?s)(out\['buy_triggers'\]\s*=\s*\[\]\s*\n)"
    r"(\s*for\s+r\s+in\s+rows:\s*\n)"
    r"(\s*d\s*=\s*_row_to_dict\(r\)\s*or\s*\{\}\s*\n)"
    r"(\s*if\s+d\.get\('time_et'\)\s+is\s+None:\s*\n)"
    r"(\s*d\['time_et'\]\s*=\s*_epoch_to_et_str\(d\.get\('ts_utc'\)\)\s*\n)"
    r"(\s*out\['buy_triggers'\]\.append\(d\)\s*\n)"
)

m = pat.search(blk)
if not m:
    # dump a small breadcrumb to help if it drifts again
    j = blk.find("out['buy_triggers']")
    ctx = blk[j:j+600] if j >= 0 else blk[:600]
    raise SystemExit("ERROR: Could not find expected buy_triggers loop inside V1D block. Context:\n" + ctx)

prefix = m.group(1)
indent_for = re.match(r"^(\s*)for", m.group(2)).group(1)
indent_d   = re.match(r"^(\s*)d\s*=", m.group(3)).group(1)

replacement = (
    prefix +
    f"{indent_for}for r in rows:\n"
    f"{indent_d}d = _row_to_dict(r) or {{}}\n"
    f"{indent_d}# V1E2: always compute time_et from ts_utc (ignore DB time_et)\n"
    f"{indent_d}_ts = d.get('ts_utc')\n"
    f"{indent_d}try:\n"
    f"{indent_d}    _ts_ep = int(_ts) if _ts is not None else None\n"
    f"{indent_d}except Exception:\n"
    f"{indent_d}    _ts_ep = _to_epoch(_ts)\n"
    f"{indent_d}d['time_et'] = _epoch_to_et_str(_ts_ep) if _ts_ep else (d.get('time_et') or '')\n"
    f"{indent_d}out['buy_triggers'].append(d)\n"
)

blk2, n = pat.subn(replacement, blk, count=1)
if n != 1:
    raise SystemExit(f"ERROR: Unexpected replacement count: {n}")

txt2 = txt[:m_blk.start()] + blk2 + txt[m_blk.end():]
P.write_text(txt2, encoding="utf-8")
print("PATCHED: trade_review buy_triggers time_et forced from ts_utc [V1E2]")
print(f"WROTE -> {P}")

py_compile.compile(str(P), doraise=True)
print("PY_COMPILE_OK")
