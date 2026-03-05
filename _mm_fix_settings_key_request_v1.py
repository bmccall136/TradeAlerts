import re, shutil, datetime, pathlib

P = pathlib.Path(r"C:\TradeAlerts\dashboard.py")
if not P.exists():
    raise SystemExit(f"Missing: {P}")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_fix_settings_key_request_v1_{ts}")
shutil.copy2(P, bak)
print("Backup ->", bak)

txt = P.read_text(encoding="utf-8", errors="replace")

# Replace def _settings_key(): ... up to (but not including) def _settings_path(
pat = re.compile(r'(?s)^\s*def\s+_settings_key\(\):\s*\n.*?\n(?=^\s*def\s+_settings_path\()', re.M)
m = pat.search(txt)
if not m:
    raise SystemExit("ERROR: Could not find _settings_key() to replace.")

replacement = r'''
def _settings_key():
    """
    Returns (group, profile) for settings API calls.
    Robust against earlier patches that may have imported Flask request as flask_request.
    """
    req = globals().get("flask_request") or globals().get("request")
    args = getattr(req, "args", {}) if req is not None else {}

    group = (args.get("group") or "").strip().lower()
    profile = (args.get("profile") or "").strip().lower()

    if group not in ("buy", "sell"):
        # If missing/invalid, default to buy so UI can still load something
        group = "buy"

    if profile not in ("day", "swing"):
        profile = "day"

    return group, profile
'''.lstrip("\n")

new_txt = txt[:m.start()] + replacement + txt[m.end():]
P.write_text(new_txt, encoding="utf-8")
print("PATCHED ->", P)
print("Replaced _settings_key() with robust request arg reader (MM_FIX_SETTINGS_KEY_REQUEST_V1).")
