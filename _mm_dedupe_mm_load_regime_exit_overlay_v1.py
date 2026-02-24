import re, shutil, datetime, pathlib

p = pathlib.Path(r"C:\TradeAlerts\sell_guard.py")
assert p.exists(), f"missing {p}"

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
bak = p.with_suffix(f".py.bak_dedupe_regime_exit_overlay_helper_{ts}")
shutil.copy2(p, bak)
print("Backup ->", bak)

txt = p.read_text(encoding="utf-8")

# Capture ALL defs of _mm_load_regime_exit_overlay as whole blocks up to next top-level def/class or EOF
pat = re.compile(r"(?ms)^(def\s+_mm_load_regime_exit_overlay\s*\([^)]*\)\s*:\s*.*?)(?=^\s*(def|class)\s+|\Z)")
blocks = list(pat.finditer(txt))

if not blocks:
    raise SystemExit("ERROR: no def _mm_load_regime_exit_overlay(...) found")

# Keep the first block, remove the rest
keep = blocks[0].group(1)
new_txt = txt

# Replace first occurrence with itself (normalizes nothing, just anchors)
new_txt = new_txt[:blocks[0].start()] + keep + new_txt[blocks[0].end():]

# Remove remaining blocks from bottom up so offsets don't shift
for m in reversed(blocks[1:]):
    new_txt = new_txt[:m.start()] + new_txt[m.end():]

p.write_text(new_txt, encoding="utf-8")
print("PATCHED ->", p, "(kept first _mm_load_regime_exit_overlay; removed duplicates:", len(blocks)-1, ")")
