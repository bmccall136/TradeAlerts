import re, shutil, datetime
from pathlib import Path

P = Path(r"C:\TradeAlerts\dashboard.py")
if not P.exists():
    raise SystemExit(f"Missing: {P}")

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = P.with_suffix(f".py.bak_fix_reo_attach_v1_{ts}")
shutil.copy2(P, bak)
print(f"Backup -> {bak}")

txt = P.read_text(encoding="utf-8", errors="replace")

# 1) Remove the old/broken load injection block if it exists
txt2, n = re.subn(
    r"(?s)\n\s*#\s*---\s*MM_REO_PERSIST_LOAD_V1_START\s*---.*?#\s*---\s*MM_REO_PERSIST_LOAD_V1_END\s*---\s*\n",
    "\n",
    txt
)
print(f"Removed old MM_REO_PERSIST_LOAD_V1 blocks -> {n}")

# 2) Find api_settings_load and insert attach block AFTER we read JSON
m = re.search(r"(?m)^(?P<indent>\s*)data\s*,\s*errs\s*=\s*_read_json\(path\)\s*$", txt2)
if not m:
    raise SystemExit("ERROR: Could not find line: data, errs = _read_json(path)")

indent = m.group("indent")
insert_at = m.end()

block = (
    f"\n{indent}# --- MM_REO_PERSIST_LOAD_V2_START ---\n"
    f"{indent}try:\n"
    f"{indent}    if isinstance(data, dict) and (\"regime_exit_overlay\" not in data or not data.get(\"regime_exit_overlay\")):\n"
    f"{indent}        data[\"regime_exit_overlay\"] = _mm_get_reo(profile) or {}\n"
    f"{indent}except Exception:\n"
    f"{indent}    pass\n"
    f"{indent}# --- MM_REO_PERSIST_LOAD_V2_END ---\n"
)

txt3 = txt2[:insert_at] + block + txt2[insert_at:]

P.write_text(txt3, encoding="utf-8")
print("PATCHED ->", P)
print("DONE. Restart dashboard, then Ctrl+F5 SELL settings and verify overlay values persist.")