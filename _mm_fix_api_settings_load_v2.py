import re, shutil, datetime, pathlib

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
if not P.exists():
    raise SystemExit(f"Missing: {P}")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_fix_api_settings_load_v2_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

txt = P.read_text(encoding="utf-8", errors="replace")

# Replace the whole api_settings_load() function body (up to the next route decorator for /api/settings/save)
pat = re.compile(
    r'(?s)@app\.route\("/api/settings/load"\)\s*?\n'
    r'def\s+api_settings_load\(\):\s*\n'
    r'(.*?)\n(?=@app\.route\("/api/settings/save")'
)
m = pat.search(txt)
if not m:
    raise SystemExit("ERROR: Could not find api_settings_load() block to replace (pattern miss).")

replacement = r'''@app.route("/api/settings/load")
def api_settings_load():
    group, profile = _settings_key()
    path = _settings_path(group, profile)
    if not path:
        return jsonify({"ok": False, "error": f"Unknown group/profile: {group}/{profile}"}), 400

    data, errs = _read_json(path)

    # --- MM_REO_PERSIST_LOAD_V2_START ---
    # Always attach overlay for UI hydration. Overlay is stored in live_settings_{day|swing}.json
    try:
        if isinstance(data, dict):
            reo = data.get("regime_exit_overlay")
            if not isinstance(reo, dict) or not reo:
                data["regime_exit_overlay"] = _mm_get_reo(profile) or {}
    except Exception:
        pass
    # --- MM_REO_PERSIST_LOAD_V2_END ---

    return jsonify({"ok": True, "group": group, "profile": profile, "path": path, "data": data, "errors": errs})
'''

new_txt = txt[:m.start()] + replacement + txt[m.end():]
P.write_text(new_txt, encoding="utf-8")
print("PATCHED ->", P)
print("Replaced api_settings_load() with MM_REO_PERSIST_LOAD_V2.")
