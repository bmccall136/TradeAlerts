import pathlib, re, datetime, shutil

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_fix_trv_meta_counts_v3_indent_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

txt = P.read_text(encoding="utf-8", errors="replace")

MARK = "MM_TRV_META_COUNTS_ANY_JSONIFY_RETURN_V3"

# Grab the existing marker block (we will rebuild it with correct indentation)
block_re = re.compile(
    r'(?ms)^(?P<ind>[ \t]*)# --- ' + re.escape(MARK) + r' ---\s*\n'
    r'.*?'
    r'^(?P=ind)# --- /' + re.escape(MARK) + r' ---\s*\n'
)
m = block_re.search(txt)
if not m:
    raise SystemExit(f"ERROR: Could not find marker block for {MARK} to fix.")

ind = m.group("ind")
old = m.group(0)

# Extract the payload expression that was already injected (the one that is NOT None)
expr = None
for mm in re.finditer(r'(?m)^\s*_payload\s*=\s*(.+?)\s*$', old):
    rhs = (mm.group(1) or "").strip()
    if rhs and rhs != "None":
        expr = rhs

if not expr:
    # Fallback: most common name
    expr = "payload"

fixed = (
f"""{ind}# --- {MARK} ---
{ind}try:
{ind}    # If we return jsonify(payload_dict) or jsonify(resp), adjust meta counts from the payload itself
{ind}    _payload = None
{ind}    try:
{ind}        # best effort: capture the object passed to jsonify on this return line
{ind}        _payload = {expr}
{ind}    except Exception:
{ind}        _payload = None

{ind}    if isinstance(_payload, dict):
{ind}        _bt = _payload.get("buy_triggers") or []
{ind}        _st = _payload.get("sell_triggers") or []
{ind}        _meta = _payload.get("meta")
{ind}        if isinstance(_meta, dict):
{ind}            _meta["buy_ct"]  = len(_bt)
{ind}            _meta["sell_ct"] = len(_st)
{ind}            _payload["meta"] = _meta
{ind}except Exception:
{ind}    pass
{ind}# --- /{MARK} ---
"""
)

txt2 = txt[:m.start()] + fixed + txt[m.end():]
P.write_text(txt2, encoding="utf-8", errors="replace")
print("FIXED INDENT ->", P)
print("Payload expr used:", expr)
