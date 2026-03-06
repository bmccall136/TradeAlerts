import pathlib, datetime, shutil, re

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
assert P.exists(), P

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_trv_meta_counts_v3_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

txt = P.read_text(encoding="utf-8", errors="replace")

MARK = "MM_TRV_META_COUNTS_ANY_JSONIFY_RETURN_V3"
if MARK in txt:
    print("Already patched (marker present).")
    raise SystemExit(0)

# Find the handler by route decorator first (most reliable)
route_m = re.search(r'(?ms)^\s*@app\.route\(\s*[\'"]\/api\/trade_review[\'"][^\)]*\)\s*\n\s*def\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(', txt)
fn_name = route_m.group(1) if route_m else None

if not fn_name:
    # fallback: function name
    m = re.search(r'(?ms)^def\s+api_trade_review\b.*?:\n', txt)
    if not m:
        raise SystemExit("ERROR: Could not find /api/trade_review route or api_trade_review() in dashboard.py")
    fn_start = m.start()
else:
    m = re.search(r'(?ms)^def\s+' + re.escape(fn_name) + r'\b.*?:\n', txt)
    if not m:
        raise SystemExit(f"ERROR: Found route for {fn_name} but could not find its def block.")
    fn_start = m.start()

# Get function block (until next top-level def or decorator)
mdef = re.search(r"(?ms)^def\s+[A-Za-z_][A-Za-z0-9_]*\b.*?:\n", txt[fn_start:])
if not mdef:
    raise SystemExit("ERROR: Could not locate function start reliably.")
abs_start = fn_start + mdef.start()
m_next = re.search(r"(?ms)^(def\s+|@app\.route)", txt[abs_start + mdef.end():])
abs_end = (abs_start + mdef.end() + m_next.start()) if m_next else len(txt)

func = txt[abs_start:abs_end]

# Find any "return jsonify(" inside the function
returns = list(re.finditer(r'(?m)^\s*return\s+jsonify\s*\(', func))
if not returns:
    raise SystemExit("ERROR: No 'return jsonify(' found inside /api/trade_review handler.")

inject = f"""
    # --- {MARK} ---
    try:
        # If we return jsonify(payload_dict) or jsonify(resp), adjust meta counts from the payload itself
        _payload = None
        try:
            # best effort: capture the object passed to jsonify on this return line
            _payload = __MM_TRV_PAYLOAD__
        except Exception:
            _payload = None

        if isinstance(_payload, dict):
            _bt = _payload.get("buy_triggers") or []
            _st = _payload.get("sell_triggers") or []
            _meta = _payload.get("meta")
            if isinstance(_meta, dict):
                _meta["buy_ct"]  = len(_bt)
                _meta["sell_ct"] = len(_st)
                _payload["meta"] = _meta
    except Exception:
        pass
    # --- /{MARK} ---
""".rstrip("\n") + "\n"

# Replace each "return jsonify(EXPR)" with:
#   inject (with __MM_TRV_PAYLOAD__ = EXPR) + original return line
def repl(m):
    line = m.group(0)
    # extract the expression inside jsonify(...) on the SAME LINE (simple + safe)
    # We'll take text from just after "return jsonify(" up to the matching ")" on that line.
    # If it's multiline, we'll skip and leave unchanged.
    full_line = line
    # Actually we need the whole line from func text:
    # easier: we will match the entire line separately
    return full_line

# We'll do a line-based transform for only the return lines
lines = func.splitlines(True)
out = []
changed = 0
ret_re = re.compile(r'^(\s*)return\s+jsonify\s*\(\s*(.+?)\s*\)\s*$', re.S)

for ln in lines:
    mret = ret_re.match(ln.rstrip("\n"))
    if mret:
        indent = mret.group(1)
        expr = mret.group(2).strip()
        # Skip multiline exprs (they won't match this regex anyway)
        inj = inject.replace("__MM_TRV_PAYLOAD__", expr)
        # keep indentation consistent (inject already 4-space indented; align with handler indent)
        # We'll just prepend the same indent to each line of inj.
        inj_lines = []
        for il in inj.splitlines(True):
            if il.strip() == "":
                inj_lines.append(il)
            else:
                inj_lines.append(indent + il.lstrip(" "))
        out.append("".join(inj_lines))
        out.append(ln)
        changed += 1
    else:
        out.append(ln)

func2 = "".join(out)
if changed == 0:
    raise SystemExit("ERROR: Found return jsonify( but could not rewrite any single-line returns (multiline payload?).")

txt2 = txt[:abs_start] + func2 + txt[abs_end:]
P.write_text(txt2, encoding="utf-8", errors="replace")
print("PATCHED ->", P)
print("Rewrote return jsonify() lines:", changed)
