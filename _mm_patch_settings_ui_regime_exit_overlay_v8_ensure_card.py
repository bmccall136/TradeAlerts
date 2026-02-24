import re, shutil, datetime, pathlib

paths = [
  pathlib.Path(r"C:\TradeAlerts\templates\settings_buy.html"),
  pathlib.Path(r"C:\TradeAlerts\templates\settings_sell.html"),
]
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

MARK_START = "MM_REGIME_EXIT_OVERLAY_UI_V5_START"
MARK_END   = "MM_REGIME_EXIT_OVERLAY_UI_V5_END"

def backup(p: pathlib.Path, tag: str):
    bak = p.with_suffix(p.suffix + f".bak_{tag}_{ts}")
    shutil.copy2(p, bak)
    return bak

block_pat = re.compile(r"(?s)(<!--\s*%s\s*-->.*?<!--\s*%s\s*-->)" % (re.escape(MARK_START), re.escape(MARK_END)))

for path in paths:
    if not path.exists():
        print("SKIP missing ->", path)
        continue

    txt = path.read_text(encoding="utf-8", errors="replace")
    m = block_pat.search(txt)
    if not m:
        print("SKIP no V5 block ->", path.name)
        continue

    block = m.group(1)
    if "MM_REO_ENSURE_CARD_V8" in block:
        print("SKIP already v8 ->", path.name)
        continue

    bak = backup(path, "reo_ui_v8_ensure_card")
    print("Backup ->", bak)

    # Extract the card HTML (everything from the card div through the hidden textarea)
    card_m = re.search(r"(?s)(<div class=\"card mb-3\" id=\"mm-regime-exit-overlay-card\".*?</div>\s*</div>\s*</div>\s*</div>\s*<!-- keep JSON hidden .*?</textarea>)", block)
    if not card_m:
        print("WARN could not locate card+textarea chunk in block ->", path.name)
        continue
    card_chunk = card_m.group(1)

    # Inject an ensureCard() that will (re)insert the card before "Other Settings" if possible
    inject = r'''
  // MM_REO_ENSURE_CARD_V8
  // The settings UI is often re-rendered after /api/settings/load; if our card gets wiped,
  // recreate it and re-wire inputs.
  function mmReoFindInsertPoint(){
    try {
      // Prefer inserting right before the "Other Settings" section if we can find it
      var els = Array.prototype.slice.call(document.querySelectorAll("div,span,h1,h2,h3,h4"));
      for (var i=0;i<els.length;i++){
        var t = (els[i].textContent||"").trim();
        if (t === "Other Settings"){
          return els[i];
        }
      }
    } catch(e) {}
    // Fallback: first big container/card stack
    return document.querySelector(".container") || document.querySelector(".mm-ax-container") || document.body;
  }

  function mmReoEnsureCard(){
    try {
      if (document.querySelector("#mm-regime-exit-overlay-card")) return true;

      var wrap = document.createElement("div");
      wrap.innerHTML = %CARD_CHUNK_JSON%;

      // pull the first element (our card) + textarea and insert both
      var nodes = Array.prototype.slice.call(wrap.childNodes).filter(function(n){ return n && n.nodeType === 1; });
      if (!nodes.length) return false;

      var insertBefore = mmReoFindInsertPoint();
      var parent = insertBefore && insertBefore.parentNode ? insertBefore.parentNode : (document.body || document.documentElement);

      // Insert all top-level nodes in order
      nodes.forEach(function(n){
        try {
          if (insertBefore && insertBefore.parentNode) {
            insertBefore.parentNode.insertBefore(n, insertBefore);
          } else {
            parent.appendChild(n);
          }
        } catch(e) {}
      });

      // Wire handlers again (since we created fresh inputs)
      try {
        qsa("[data-mm-reo]").forEach(function(inp){
          inp.addEventListener("input", push);
          inp.addEventListener("change", push);
        });
      } catch(e) {}

      return !!document.querySelector("#mm-regime-exit-overlay-card");
    } catch(e) {
      return false;
    }
  }
'''.strip("\n")

    # Put the injection right after qsa() helper (stable anchor)
    anchor = "function qsa(sel){ return Array.prototype.slice.call(document.querySelectorAll(sel)); }"
    ai = block.find(anchor)
    if ai < 0:
        print("WARN anchor not found ->", path.name)
        continue
    insert_at = ai + len(anchor)

    # JSON-escape the HTML chunk so we can safely embed it as a JS string literal
    import json
    card_json = json.dumps(card_chunk)

    inject2 = inject.replace("%CARD_CHUNK_JSON%", card_json)

    block = block[:insert_at] + "\n\n" + inject2 + "\n" + block[insert_at:]

    # Upgrade the hydrate retry tick to ensureCard() first, then hydrate()
    if "MM_REO_HYDRATE_RETRY_V6" in block:
        block = re.sub(
            r"(?s)//\s*MM_REO_HYDRATE_RETRY_V6.*?\}\)\(\);\s*",
            lambda mm: mm.group(0).replace("hydrate();", "mmReoEnsureCard(); hydrate();"),
            block,
            count=1
        )
    else:
        # If V6 isn't present, still do a small delayed ensure+hydrate
        block = block.replace(
            "hydrate();",
            "setTimeout(function(){ try{ mmReoEnsureCard(); }catch(e){} try{ hydrate(); }catch(e){} }, 50);",
            1
        )

    new_txt = txt[:m.start()] + block + txt[m.end():]
    path.write_text(new_txt, encoding="utf-8")
    print("PATCHED ->", path)

print("DONE.")
