import re, json, shutil, datetime
from pathlib import Path

P = Path(r"C:\TradeAlerts\dashboard.py")
if not P.exists():
    raise SystemExit(f"Missing: {P}")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_reo_persist_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

txt = P.read_text(encoding="utf-8", errors="replace")

# ---- helpers we will inject once ----
HELPERS = r'''
# --- MM_REO_PERSIST_HELPERS_V1_START ---
from pathlib import Path as _MMPath
import json as _MMjson

def _mm_live_settings_path_for_profile(profile: str) -> _MMPath:
    # profile is "day" / "swing" (from UI)
    prof = (profile or "").strip().lower() or "day"
    # primary target (what BUY settings uses)
    cand = _MMPath(r"C:\TradeAlerts") / f"live_settings_{prof}.json"
    if cand.exists():
        return cand
    # fallback legacy names if you ever used them
    cand2 = _MMPath(r"C:\TradeAlerts") / f"live_settings_{prof}.json"
    return cand2

def _mm_read_json(p: _MMPath) -> dict:
    try:
        return _MMjson.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}

def _mm_write_json(p: _MMPath, obj: dict):
    p.write_text(_MMjson.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")

def _mm_get_reo(profile: str) -> dict:
    p = _mm_live_settings_path_for_profile(profile)
    obj = _mm_read_json(p)
    return obj.get("regime_exit_overlay") or {}

def _mm_set_reo(profile: str, reo: dict):
    p = _mm_live_settings_path_for_profile(profile)
    obj = _mm_read_json(p)
    obj["regime_exit_overlay"] = reo or {}
    _mm_write_json(p, obj)
# --- MM_REO_PERSIST_HELPERS_V1_END ---
'''

if "MM_REO_PERSIST_HELPERS_V1_START" not in txt:
    # inject helpers near top (after imports). Heuristic: after last import block.
    m = re.search(r'(?ms)^(import .+?\n)(\n)', txt)
    if m:
        insert_at = m.end(1)
        txt = txt[:insert_at] + HELPERS + txt[insert_at:]
    else:
        txt = HELPERS + "\n" + txt

# ---- Patch /api/settings/save ----
# We look for the route and then inject just before writing file / returning ok.
SAVE_ROUTE = re.search(r'(?ms)@app\.route\(\s*[\'"]/api/settings/save[\'"].*?\)\s*def\s+([a-zA-Z0-9_]+)\s*\(', txt)
if not SAVE_ROUTE:
    raise SystemExit("ERROR: Could not find @app.route('/api/settings/save'...) in dashboard.py")

save_fn = SAVE_ROUTE.group(1)

# Find a good injection point inside save handler: right after JSON body is parsed into `data`
# Common patterns: data = request.get_json(...) or json.loads(request.data)
SAVE_INJECT = r'''
    # --- MM_REO_PERSIST_SAVE_V1_START ---
    try:
        if isinstance(data, dict) and "regime_exit_overlay" in data:
            _mm_set_reo(profile, data.get("regime_exit_overlay") or {})
    except Exception as _e:
        # don't block saves
        pass
    # --- MM_REO_PERSIST_SAVE_V1_END ---
'''

# Only inject once
if "MM_REO_PERSIST_SAVE_V1_START" not in txt:
    # heuristic: after first assignment to `data` inside save fn
    fn_start = txt.find(f"def {save_fn}(")
    fn_body = txt[fn_start:fn_start+20000]
    m = re.search(r'(?ms)^\s*data\s*=\s*.+?$', fn_body)
    if not m:
        raise SystemExit("ERROR: Could not locate `data = ...` inside settings save handler")
    ins_at = fn_start + m.end(0)
    txt = txt[:ins_at] + SAVE_INJECT + txt[ins_at:]

# ---- Patch /api/settings/load ----
LOAD_ROUTE = re.search(r'(?ms)@app\.route\(\s*[\'"]/api/settings/load[\'"].*?\)\s*def\s+([a-zA-Z0-9_]+)\s*\(', txt)
if not LOAD_ROUTE:
    raise SystemExit("ERROR: Could not find @app.route('/api/settings/load'...) in dashboard.py")

load_fn = LOAD_ROUTE.group(1)

LOAD_INJECT = r'''
    # --- MM_REO_PERSIST_LOAD_V1_START ---
    try:
        if isinstance(data, dict) and ("regime_exit_overlay" not in data or not data.get("regime_exit_overlay")):
            data["regime_exit_overlay"] = _mm_get_reo(profile) or {}
    except Exception as _e:
        pass
    # --- MM_REO_PERSIST_LOAD_V1_END ---
'''

if "MM_REO_PERSIST_LOAD_V1_START" not in txt:
    fn_start = txt.find(f"def {load_fn}(")
    fn_body = txt[fn_start:fn_start+20000]
    # heuristic: inject right before returning jsonify(data) / return {...}
    m = re.search(r'(?ms)^\s*return\s+jsonify\(\s*data\s*\)\s*$', fn_body)
    if not m:
        # fallback: before any `return` in the handler
        m = re.search(r'(?ms)^\s*return\s+.+$', fn_body)
    if not m:
        raise SystemExit("ERROR: Could not locate return statement inside settings load handler")
    ins_at = fn_start + m.start(0)
    txt = txt[:ins_at] + LOAD_INJECT + txt[ins_at:]

P.write_text(txt, encoding="utf-8")
print("PATCHED ->", P)
print("DONE: restart $$Machine, then Ctrl+F5 Settings (SELL).")