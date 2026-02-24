import re, shutil, datetime, pathlib

p = pathlib.Path(r"C:\TradeAlerts\sell_guard.py")
assert p.exists(), f"missing {p}"

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = p.with_suffix(f".py.bak_regime_exit_overlay_mode_from_live_mode_v5_{ts}")
shutil.copy2(p, bak)
print("Backup ->", bak)

txt = p.read_text(encoding="utf-8")

MARK = "MM_REGIME_EXIT_OVERLAY_MODE_FROM_LIVE_MODE_V5"

# Replace the helper function _mm_load_regime_exit_overlay(...) entirely
pat = re.compile(r"(?ms)^def\s+_mm_load_regime_exit_overlay\s*\([^)]*\)\s*:\s*.*?(?=^\s*def\s+|\Z)")
m = pat.search(txt)
if not m:
    raise SystemExit("ERROR: def _mm_load_regime_exit_overlay(...) not found in sell_guard.py")

helper = f'''
# {MARK}
def _mm_load_regime_exit_overlay(mode, legacy_map):
    """Load regime_exit_overlay using ACTIVE mode from live_mode.txt (dashboard toggle).

    Order:
      1) Read live_mode.txt to determine active mode (DAY/SWING). Default DAY.
      2) Select primary = live_settings_swing.json if SWING else live_settings_day.json
      3) Load regime_exit_overlay from primary; fallback to live_settings.json
      4) Return legacy_map if missing/invalid

    Scope: ONLY target_mult/stop_mult/time_mult for TREND/CHOP/DEAD (+ UNKNOWN).
    """
    try:
        import os, json

        root = os.path.dirname(__file__)
        live_fp   = os.path.join(root, "live_settings.json")
        day_fp    = os.path.join(root, "live_settings_day.json")
        swing_fp  = os.path.join(root, "live_settings_swing.json")

        # Dashboard mode toggle file (source of truth)
        live_mode_fp = os.path.join(root, "live_mode.txt")
        valid_modes = {{"DAY","SWING"}}

        def _read_json(fp):
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return None

        def _read_mode_file():
            try:
                with open(live_mode_fp, "r", encoding="utf-8") as f:
                    s = (f.read() or "").strip().upper()
            except Exception:
                s = ""
            if s in valid_modes:
                return s
            return "DAY"

        # 1) Determine active mode from live_mode.txt
        cfg_mode = _read_mode_file()

        # Fallback to provided mode arg only if somehow mode file logic breaks
        if not cfg_mode:
            cfg_mode = (mode or "").upper().strip() or "DAY"
        if cfg_mode not in valid_modes:
            cfg_mode = "DAY"

        primary_fp = swing_fp if (cfg_mode == "SWING") else day_fp

        # 2) Load from primary first; fallback to live_settings.json
        primary_cfg = _read_json(primary_fp) or {{}}
        live_cfg = _read_json(live_fp) or {{}}
        cfg = primary_cfg if isinstance(primary_cfg, dict) and primary_cfg else live_cfg

        ov = cfg.get("regime_exit_overlay")
        if not isinstance(ov, dict):
            # last-ditch: if primary missing overlay but live has it, try live
            ov = live_cfg.get("regime_exit_overlay")
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
'''

txt = txt[:m.start()] + helper + txt[m.end():]

p.write_text(txt, encoding="utf-8")
print("PATCHED ->", p, f"[{MARK}]")
