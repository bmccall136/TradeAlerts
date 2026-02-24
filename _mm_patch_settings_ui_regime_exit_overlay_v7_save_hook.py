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

for path in paths:
    if not path.exists():
        print("SKIP missing ->", path)
        continue

    txt = path.read_text(encoding="utf-8", errors="replace")

    if MARK_START not in txt or MARK_END not in txt:
        print("SKIP no V5 markers ->", path.name)
        continue

    bak = backup(path, "reo_ui_v7_save_hook")
    print("Backup ->", bak)

    # 1) Export overlay helpers to window inside our marker block (once)
    block_pat = re.compile(r"(?s)(<!--\s*%s\s*-->.*?<!--\s*%s\s*-->)" % (re.escape(MARK_START), re.escape(MARK_END)))
    m = block_pat.search(txt)
    if not m:
        print("SKIP block not found ->", path.name)
        continue

    block = m.group(1)
    if "MM_REO_EXPORT_V7" not in block:
        # Insert export right after push() function definition (after "writeCurrentJSON(obj);" area)
        # We anchor near the end of push() where it writes JSON, then add export.
        anchor = "writeCurrentJSON(obj);"
        idx = block.find(anchor)
        if idx < 0:
            print("WARN: anchor not found for export ->", path.name)
        else:
            insert_at = idx + len(anchor)
            export_js = r'''
     // MM_REO_EXPORT_V7
     // Expose small API so the page's Save flow can force-sync overlay -> settings object
     try {
       window.MM_REO = window.MM_REO || {};
       window.MM_REO.push = push;
       window.MM_REO.hydrate = hydrate;
       window.MM_REO.getOverlay = function(){
         try {
           var obj = ensureOverlay(readCurrentJSON());
           return (obj && obj.regime_exit_overlay) ? obj.regime_exit_overlay : null;
         } catch(e){ return null; }
       };
     } catch(e) {}
'''.rstrip("\n")
            block = block[:insert_at] + export_js + block[insert_at:]

    # Put block back
    txt = txt[:m.start()] + block + txt[m.end():]

    # 2) Hook save payload: right before the /api/settings/save fetch, force push() and merge overlay
    # We do NOT assume variable names; instead we patch the body-building section to merge
    # `regime_exit_overlay` into the first JSON.stringify(...) object literal we can find in that save call.
    #
    # Strategy:
    #   Find "fetch(`/api/settings/save" then within the next ~500 chars find "body:" ... "JSON.stringify("
    #   and wrap it with a small prelude that merges overlay into the object being stringified.
    #
    if "MM_REO_SAVE_HOOK_V7" not in txt:
        save_i = txt.find("/api/settings/save")
        if save_i < 0:
            print("WARN: could not find /api/settings/save ->", path.name)
        else:
            # Find a nearby JSON.stringify(
            jsi = txt.find("JSON.stringify(", save_i)
            if jsi < 0 or jsi - save_i > 1200:
                print("WARN: could not locate JSON.stringify near save ->", path.name)
            else:
                # Find end paren of JSON.stringify call (best effort, shallow scan)
                # We'll inject a wrapper: MM_REO_MERGE( <original_obj_expr> )
                # where MM_REO_MERGE mutates and returns the object.
                #
                # Parse argument expression start
                arg_start = jsi + len("JSON.stringify(")
                # Find matching ')' for this JSON.stringify by counting parens
                depth = 1
                k = arg_start
                while k < len(txt) and depth > 0:
                    ch = txt[k]
                    if ch == "(":
                        depth += 1
                    elif ch == ")":
                        depth -= 1
                    k += 1
                if depth != 0:
                    print("WARN: could not match JSON.stringify parens ->", path.name)
                else:
                    arg_end = k-1  # index of the closing ')'
                    original_arg = txt[arg_start:arg_end]

                    merge_fn = r'''
// MM_REO_SAVE_HOOK_V7
function MM_REO_MERGE_SETTINGS_OBJ(obj){
  try{
    if(!obj || typeof obj !== "object") return obj;
    var ov = null;
    try { ov = (window.MM_REO && window.MM_REO.getOverlay) ? window.MM_REO.getOverlay() : null; } catch(e){ ov = null; }
    if(ov && typeof ov === "object"){
      obj.regime_exit_overlay = ov;
    }
  }catch(e){}
  return obj;
}
'''.strip("\n")

                    # Ensure merge_fn exists once (near top of the main script area).
                    # Insert it just before the first occurrence of "/api/settings/save"
                    insert_merge_at = txt.rfind("<script", 0, save_i)
                    if insert_merge_at < 0:
                        insert_merge_at = save_i
                    else:
                        insert_merge_at = txt.find(">", insert_merge_at)
                        if insert_merge_at < 0:
                            insert_merge_at = save_i
                        else:
                            insert_merge_at += 1

                    txt = txt[:insert_merge_at] + "\n" + merge_fn + "\n" + txt[insert_merge_at:]

                    # Also force a push() just before save
                    prelude = r'''
    // MM_REO_SAVE_HOOK_V7: force-sync overlay -> hidden JSON/global mirrors before saving
    try { if (window.MM_REO && window.MM_REO.push) window.MM_REO.push(); } catch(e) {}
'''.rstrip("\n")

                    # Insert prelude just before fetch(`/api/settings/save`
                    fetch_i = txt.find("fetch(`/api/settings/save", save_i)
                    if fetch_i < 0:
                        fetch_i = txt.find("fetch(\"/api/settings/save", save_i)
                    if fetch_i > 0:
                        line_start = txt.rfind("\n", 0, fetch_i) + 1
                        txt = txt[:line_start] + prelude + "\n" + txt[line_start:]

                    # Wrap JSON.stringify arg
                    # Need to re-find because txt changed; do a fresh search after save_i
                    save_i2 = txt.find("/api/settings/save")
                    jsi2 = txt.find("JSON.stringify(", save_i2)
                    arg_start2 = jsi2 + len("JSON.stringify(")
                    # find matching )
                    depth = 1
                    k = arg_start2
                    while k < len(txt) and depth > 0:
                        ch = txt[k]
                        if ch == "(":
                            depth += 1
                        elif ch == ")":
                            depth -= 1
                        k += 1
                    arg_end2 = k-1
                    txt = txt[:arg_start2] + "MM_REO_MERGE_SETTINGS_OBJ(" + txt[arg_start2:arg_end2] + ")" + txt[arg_end2:]

    path.write_text(txt, encoding="utf-8")
    print("PATCHED ->", path)

print("DONE.")
