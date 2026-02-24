import re, shutil, datetime, pathlib

paths = [
  pathlib.Path(r"C:\TradeAlerts\templates\settings_buy.html"),
  pathlib.Path(r"C:\TradeAlerts\templates\settings_sell.html"),
]
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

MARK_START = "MM_REGIME_EXIT_OVERLAY_UI_V5_START"
MARK_END   = "MM_REGIME_EXIT_OVERLAY_UI_V5_END"

for path in paths:
    if not path.exists():
        print("SKIP missing ->", path)
        continue

    txt = path.read_text(encoding="utf-8", errors="replace")
    if MARK_START not in txt or MARK_END not in txt:
        print("SKIP no V5 markers ->", path.name)
        continue

    bak = path.with_suffix(path.suffix + f".bak_reo_ui_v6_retry_{ts}")
    shutil.copy2(path, bak)

    # inside the block, replace the single call "hydrate();" with a retry loop
    block_pat = re.compile(r"(?s)(<!--\s*%s\s*-->.*?<!--\s*%s\s*-->)" % (re.escape(MARK_START), re.escape(MARK_END)))
    m = block_pat.search(txt)
    if not m:
        print("SKIP block not found ->", path.name)
        continue

    block = m.group(1)

    if "MM_REO_HYDRATE_RETRY_V6" in block:
        print("SKIP already v6 ->", path.name)
        continue

    # Find the last "hydrate();" call near the bottom of our script
    if "hydrate();" not in block:
        print("WARN no hydrate(); found ->", path.name)
        continue

    replacement = r"""
  // MM_REO_HYDRATE_RETRY_V6
  // If settings are populated later (fetch / async), retry hydrate for a short window.
  (function(){
    var tries = 0;
    function tick(){
      tries++;
      try {
        var ta = qs("#settings_json");
        var hasTA = ta && (ta.value || "").trim().length > 0;
        var hasObj = false;
        try { hasObj = !!tryReadSettingsObject(); } catch(e) { hasObj = false; }

        if (hasTA || hasObj) {
          hydrate();
          return;
        }
      } catch(e) {}
      if (tries < 25) setTimeout(tick, 200);
    }
    tick();
  })();
""".strip("\n")

    # replace only the first occurrence from the end: easiest approach is reverse replace once
    idx = block.rfind("hydrate();")
    new_block = block[:idx] + replacement + block[idx+len("hydrate();"):]

    new_txt = txt[:m.start()] + new_block + txt[m.end():]
    path.write_text(new_txt, encoding="utf-8")
    print("Backup ->", bak)
    print("PATCHED ->", path)

