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

    bak = path.with_suffix(path.suffix + f".bak_reo_ui_v9_ensure_card_{ts}")
    shutil.copy2(path, bak)
    print("Backup ->", bak)

    block_pat = re.compile(r"(?s)(<!--\s*%s\s*-->.*?<!--\s*%s\s*-->)" % (re.escape(MARK_START), re.escape(MARK_END)))
    m = block_pat.search(txt)
    if not m:
        print("WARN block not found ->", path.name)
        continue

    block = m.group(1)

    if "MM_REO_ENSURE_CARD_V9" in block:
        print("SKIP already V9 ->", path.name)
        continue

    # Grab the existing card+hidden textarea from within the block (robust)
    chunk_pat = re.compile(r"(?s)(<div\b[^>]*id\s*=\s*['\"]mm-regime-exit-overlay-card['\"][^>]*>.*?</div>\s*<!-- keep JSON hidden.*?</textarea>)", re.I)
    cm = chunk_pat.search(block)
    if not cm:
        # fallback: card div through textarea id=settings_json
        chunk_pat2 = re.compile(r"(?s)(<div\b[^>]*id\s*=\s*['\"]mm-regime-exit-overlay-card['\"][^>]*>.*?</div>.*?<textarea\b[^>]*id\s*=\s*['\"]settings_json['\"][^>]*>.*?</textarea>)", re.I)
        cm = chunk_pat2.search(block)

    if not cm:
        print("WARN could not extract card+textarea from block ->", path.name)
        continue

    card_chunk = cm.group(1)

    ensure_js = r"""
  // MM_REO_ENSURE_CARD_V9
  // The settings pages are fetch-driven; DOM can be rebuilt. Ensure the overlay card exists in the visible flow.
  function MM_REO_ENSURE_CARD(){
    try{
      var card = document.getElementById("mm-regime-exit-overlay-card");
      if(!card) return;

      // Prefer placing it before "Other Settings" section if present
      var anchors = [
        document.querySelector('h5, h4, h3'),
        document.querySelector('[data-mm-section="other-settings"]'),
        document.querySelector('#mm-other-settings'),
        document.querySelector('.mm-other-settings'),
      ].filter(Boolean);

      // If we can find the "Other Settings" header by text, use it
      var hs = Array.prototype.slice.call(document.querySelectorAll("h1,h2,h3,h4,h5,div,span"));
      var other = null;
      for(var i=0;i<hs.length;i++){
        var t = (hs[i].textContent||"").trim().toLowerCase();
        if(t === "other settings" || t.indexOf("other settings") >= 0){
          other = hs[i];
          break;
        }
      }

      var insertBefore = other || anchors[0] || null;

      // Fallback: insert near the top of the main content container
      var main = document.querySelector("main") || document.querySelector(".container") || document.body;

      // If card isn't currently inside main visible area, move it
      if(main && !main.contains(card)){
        main.insertBefore(card, main.firstChild);
      }

      // If we have a good insertBefore anchor within main, move card right above it
      if(insertBefore && insertBefore.parentNode){
        insertBefore.parentNode.insertBefore(card, insertBefore);
      }
    }catch(e){}
  }
""".rstrip("\n")

    # Insert ensure_js inside the marker block: put it just after qsa()/qs() helpers if possible
    if "function qs(sel)" in block and "function qsa(sel)" in block:
        # after qsa definition line
        qsa_idx = block.find("function qsa(sel)")
        nl = block.find("\n", qsa_idx)
        nl2 = block.find("\n", nl+1)
        ins = nl2 if nl2 > 0 else nl
        block2 = block[:ins] + "\n" + ensure_js + "\n" + block[ins:]
    else:
        # just append before </script> inside block
        si = block.rfind("</script>")
        if si < 0:
            print("WARN no </script> in block ->", path.name)
            continue
        block2 = block[:si] + "\n" + ensure_js + "\n" + block[si:]

    # Ensure we call it repeatedly (after async loads)
    # Replace the V6 retry tick's hydrate() call with hydrate(); MM_REO_ENSURE_CARD();
    block2 = block2.replace("hydrate();", "hydrate();\n          try{ MM_REO_ENSURE_CARD(); }catch(e){}\n")

    # Also call once immediately on DOM ready
    if "MM_REO_ENSURE_CARD_DOMREADY_V9" not in block2:
        domready = r"""
  // MM_REO_ENSURE_CARD_DOMREADY_V9
  try{
    if(document.readyState === "loading"){
      document.addEventListener("DOMContentLoaded", function(){ try{ MM_REO_ENSURE_CARD(); }catch(e){} });
    }else{
      MM_REO_ENSURE_CARD();
    }
  }catch(e){}
""".rstrip("\n")
        si = block2.rfind("</script>")
        block2 = block2[:si] + "\n" + domready + "\n" + block2[si:]

    # Replace the old card chunk with itself (keeps it), but we now have ensure logic
    new_txt = txt[:m.start()] + block2 + txt[m.end():]
    path.write_text(new_txt, encoding="utf-8")
    print("PATCHED ->", path)

print("DONE.")
