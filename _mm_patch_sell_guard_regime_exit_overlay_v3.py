import os, re, sys, json, shutil, datetime, pathlib

p = pathlib.Path(r"C:\TradeAlerts\sell_guard.py")
assert p.exists(), f"missing {p}"

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = p.with_suffix(f".py.bak_regime_exit_overlay_from_settings_v3_{ts}")
shutil.copy2(p, bak)
print("Backup ->", bak)

txt = p.read_text(encoding="utf-8")

MARK = "MM_REGIME_EXIT_OVERLAY_FROM_SETTINGS_V3"

# --- insert helper after imports (once) ---
if MARK not in txt:
    helper = f"""
# {MARK}
def _mm_load_regime_exit_overlay(mode, legacy_map):
    \"\"\"Load regime_exit_overlay from settings JSON (DAY/SWING aware) with legacy fallback.
    Scope: ONLY target_mult/stop_mult/time_mult for TREND/CHOP/DEAD (plus UNKNOWN).
    \"\"\"
    try:
        root = os.path.dirname(__file__)
        mu = (mode or "").upper()
        primary = os.path.join(root, "live_settings_swing.json") if ("SWING" in mu) else os.path.join(root, "live_settings_day.json")
        fallback = os.path.join(root, "live_settings.json")

        def _read(fp):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    return f.read()
            except Exception:
                return None

        def _loads(s):
            try:
                return json.loads(s) if s else None
            except Exception:
                return None

        cfg = _loads(_read(primary)) or _loads(_read(fallback)) or {{}}
        ov = cfg.get("regime_exit_overlay")
        if not isinstance(ov, dict):
            return legacy_map

        out = {{}}
        for k in ("TREND","CHOP","DEAD"):
            v = ov.get(k)
            if not isinstance(v, dict):
                continue
            lk = legacy_map.get(k, {{}}) if isinstance(legacy_map, dict) else {{}}
            def _f(key, default):
                try:
                    return float(v.get(key, lk.get(key, default)))
                except Exception:
                    try:
                        return float(lk.get(key, default))
                    except Exception:
                        return float(default)
            out[k] = {{
                "target_mult": _f("target_mult", 1.0),
                "stop_mult":   _f("stop_mult",   1.0),
                "time_mult":   _f("time_mult",   1.0),
            }}

        # ensure UNKNOWN + fill missing keys from legacy
        if isinstance(legacy_map, dict):
            legacy_map = dict(legacy_map)
        else:
            legacy_map = {{}}
        legacy_map.setdefault("UNKNOWN", {{"target_mult":1.0,"stop_mult":1.0,"time_mult":1.0}})

        for k in ("TREND","CHOP","DEAD","UNKNOWN"):
            if k not in out:
                out[k] = legacy_map.get(k) or {{"target_mult":1.0,"stop_mult":1.0,"time_mult":1.0}}
        return out
    except Exception:
        return legacy_map
"""

    # insert helper after the initial import block
    lines = txt.splitlines(True)
    imp = re.compile(r"^\s*(from\s+\S+\s+import\s+.+|import\s+.+)\s*$")
    i = 0
    while i < len(lines) and imp.match(lines[i]):
        i += 1
    txt = "".join(lines[:i]) + helper + "".join(lines[i:])

# --- patch _mm_regime_overlay to use loader ---
m = re.search(r"(?m)^def\s+_mm_regime_overlay\s*\(([^)]*)\)\s*:\s*$", txt)
if not m:
    raise SystemExit("ERROR: could not find def _mm_regime_overlay(...) in sell_guard.py")

fn_start = m.start()
after_sig = txt.find("\n", m.end()) + 1
mnext = re.search(r"(?m)^(def|class)\s+\w+", txt[after_sig:])
fn_end = (after_sig + mnext.start()) if mnext else len(txt)

sig_inner = (m.group(1) or "").strip()

# Ensure a mode param exists (default empty string) WITHOUT breaking existing args
if re.search(r"(?<!\w)mode\s*=", sig_inner) or re.search(r"(?<!\w)mode\b", sig_inner):
    new_sig = f"def _mm_regime_overlay({sig_inner}):\n"
else:
    if sig_inner:
        new_sig = f"def _mm_regime_overlay({sig_inner}, mode=\"\"):\n"
    else:
        new_sig = "def _mm_regime_overlay(mode=\"\"):\n"

legacy = {
    "CHOP":   {"target_mult":0.60,"stop_mult":0.80,"time_mult":0.80},
    "TREND":  {"target_mult":1.60,"stop_mult":1.25,"time_mult":1.30},
    "DEAD":   {"target_mult":0.50,"stop_mult":0.70,"time_mult":0.60},
    "UNKNOWN":{"target_mult":1.00,"stop_mult":1.00,"time_mult":1.00},
}

# Build a safe body that:
#  - accepts either label/lab/etc (first arg), or uses label param if present
#  - calls _mm_load_regime_exit_overlay(mode, legacy)
#  - returns map[label] with UNKNOWN fallback
body = []
body.append("    try:\n")
body.append("        # label arg is usually the first positional param in existing signatures\n")
body.append("        _lab = None\n")
body.append("        try:\n")
body.append("            _lab = (locals().get('label') or locals().get('lab') or locals().get('regime') or locals().get('r') or None)\n")
body.append("        except Exception:\n")
body.append("            _lab = None\n")
body.append("        if _lab is None:\n")
body.append("            try:\n")
body.append("                # fallback: first positional arg from locals (best-effort)\n")
body.append("                # if original signature was (label): it'll be in locals() already\n")
body.append("                _lab = None\n")
body.append("            except Exception:\n")
body.append("                _lab = None\n")
body.append("        _lab = (_lab or 'UNKNOWN').upper()\n")
body.append(f"        _legacy = {json.dumps(legacy, separators=(',',':'))}\n")
body.append("        _ov = _mm_load_regime_exit_overlay(mode, _legacy)\n")
body.append("        return _ov.get(_lab) or _ov.get('UNKNOWN') or {'target_mult':1.0,'stop_mult':1.0,'time_mult':1.0}\n")
body.append("    except Exception:\n")
body.append("        return {'target_mult':1.0,'stop_mult':1.0,'time_mult':1.0}\n")

new_fn = new_sig + "".join(body)

txt = txt[:fn_start] + new_fn + txt[fn_end:]

p.write_text(txt, encoding="utf-8")
print("PATCHED ->", p, f"[{MARK}]")
