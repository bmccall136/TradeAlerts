import re, shutil, datetime, pathlib

paths = [
  pathlib.Path(r"C:\TradeAlerts\templates\settings_buy.html"),
  pathlib.Path(r"C:\TradeAlerts\templates\settings_sell.html"),
]
ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

MARK_START = "MM_REGIME_EXIT_OVERLAY_UI_V5_START"
MARK_END   = "MM_REGIME_EXIT_OVERLAY_UI_V5_END"

def build_rows():
    tpl = """
    <div class="col-12">
      <div class="d-flex align-items-center justify-content-between flex-wrap gap-2">
        <div class="fw-bold" style="min-width:110px">{r}</div>
        <div class="d-flex align-items-center gap-2 flex-wrap">
          <label class="small text-secondary mb-0">target</label>
          <input class="form-control form-control-sm" style="width:120px" type="number" step="0.01" data-mm-reo="{r}.target_mult">
          <label class="small text-secondary mb-0">stop</label>
          <input class="form-control form-control-sm" style="width:120px" type="number" step="0.01" data-mm-reo="{r}.stop_mult">
          <label class="small text-secondary mb-0">time</label>
          <input class="form-control form-control-sm" style="width:120px" type="number" step="0.01" data-mm-reo="{r}.time_mult">
        </div>
      </div>
    </div>
    """.rstrip()
    rows = []
    for r in ["TREND","CHOP","DEAD","UNKNOWN"]:
        rows.append(tpl.format(r=r))
    return "\n".join(rows)

UI_BLOCK = r"""
<!-- __MM_START__ -->
<div class="card mb-3" id="mm-regime-exit-overlay-card">
  <div class="card-header d-flex align-items-center justify-content-between">
    <div class="fw-bold">Regime Exit Overlay</div>
    <div class="small text-secondary">target_mult / stop_mult / time_mult</div>
  </div>
  <div class="card-body">
    <div class="row g-2">
__MM_ROWS__
    </div>
    <div class="mt-2 small text-secondary">
      Applies on regime changes only. Stored in <code>regime_exit_overlay</code>.
      Active file is chosen by <code>live_mode.txt</code>.
    </div>
  </div>
</div>

<!-- keep JSON hidden (human-first UI) -->
<textarea id="settings_json" name="settings_json" style="display:none" aria-hidden="true"></textarea>

<script>
(function(){
  function qs(sel){ return document.querySelector(sel); }
  function qsa(sel){ return Array.prototype.slice.call(document.querySelectorAll(sel)); }

  var regimes = ["TREND","CHOP","DEAD","UNKNOWN"];
  var keys = ["target_mult","stop_mult","time_mult"];

  function tryReadSettingsObject(){
    try {
      if (window.MM_SETTINGS && typeof window.MM_SETTINGS === "object") return window.MM_SETTINGS;
      if (window.mmSettings && typeof window.mmSettings === "object") return window.mmSettings;
      if (window.settings && typeof window.settings === "object") return window.settings;
    } catch(e) {}

    try {
      var el = qs("#mm-settings-json");
      if (el && (el.type || "").toLowerCase() === "application/json") {
        return JSON.parse(el.textContent || "{}");
      }
    } catch(e) {}

    return null;
  }

  function ensureOverlay(obj){
    if(!obj || typeof obj !== "object") obj = {};
    if(!obj.regime_exit_overlay || typeof obj.regime_exit_overlay !== "object") obj.regime_exit_overlay = {};
    regimes.forEach(function(r){
      if(!obj.regime_exit_overlay[r] || typeof obj.regime_exit_overlay[r] !== "object") obj.regime_exit_overlay[r] = {};
      keys.forEach(function(k){
        var v = obj.regime_exit_overlay[r][k];
        if(typeof v !== "number" || !isFinite(v)) obj.regime_exit_overlay[r][k] = 1.0;
      });
    });
    return obj;
  }

  function readCurrentJSON(){
    var ta = qs("#settings_json");
    if (ta && (ta.value || "").trim()) {
      try { return JSON.parse(ta.value); } catch(e) {}
    }
    var obj = tryReadSettingsObject();
    if (obj) return obj;
    return {};
  }

  function writeCurrentJSON(obj){
    var ta = qs("#settings_json");
    if(!ta) return;
    try { ta.value = JSON.stringify(obj, null, 2); } catch(e) {}
  }

  function hydrate(){
    var obj = ensureOverlay(readCurrentJSON());
    qsa("[data-mm-reo]").forEach(function(inp){
      var path = (inp.getAttribute("data-mm-reo") || "");
      var parts = path.split(".");
      if(parts.length !== 2) return;
      var r = parts[0], k = parts[1];
      try {
        var v = obj.regime_exit_overlay[r][k];
        if(typeof v === "number" && isFinite(v)) inp.value = String(v);
      } catch(e){}
    });
    writeCurrentJSON(obj);
    // keep any global mirrors aligned if they exist
    try { if(window.MM_SETTINGS && typeof window.MM_SETTINGS === "object") window.MM_SETTINGS = obj; } catch(e){}
    try { if(window.mmSettings && typeof window.mmSettings === "object") window.mmSettings = obj; } catch(e){}
  }

  function push(){
    var obj = ensureOverlay(readCurrentJSON());
    qsa("[data-mm-reo]").forEach(function(inp){
      var path = (inp.getAttribute("data-mm-reo") || "");
      var parts = path.split(".");
      if(parts.length !== 2) return;
      var r = parts[0], k = parts[1];
      var num = parseFloat(inp.value);
      if(!isFinite(num)) return;
      obj.regime_exit_overlay[r][k] = num;
    });
    writeCurrentJSON(obj);
    try { if(window.MM_SETTINGS && typeof window.MM_SETTINGS === "object") window.MM_SETTINGS = obj; } catch(e){}
    try { if(window.mmSettings && typeof window.mmSettings === "object") window.mmSettings = obj; } catch(e){}
  }

  qsa("[data-mm-reo]").forEach(function(inp){
    inp.addEventListener("input", push);
    inp.addEventListener("change", push);
  });

  hydrate();
})();
</script>
<!-- __MM_END__ -->
""".lstrip("\n").replace("__MM_ROWS__", build_rows()).replace("__MM_START__", MARK_START).replace("__MM_END__", MARK_END)

patched = []
for path in paths:
    if not path.exists():
        print("SKIP (missing) ->", path)
        continue

    txt = path.read_text(encoding="utf-8", errors="replace")

    if MARK_START in txt and MARK_END in txt:
        print("SKIP (already patched) ->", path.name)
        continue

    bak = path.with_suffix(path.suffix + f".bak_reo_ui_v5_{ts}")
    shutil.copy2(path, bak)

    # Prefer insert before </form>, else before </body>, else append
    m = re.search(r"(?i)</form\s*>", txt)
    if m:
        insert_at = m.start()
    else:
        m2 = re.search(r"(?i)</body\s*>", txt)
        insert_at = m2.start() if m2 else len(txt)

    new_txt = txt[:insert_at] + "\n" + UI_BLOCK + "\n" + txt[insert_at:]
    path.write_text(new_txt, encoding="utf-8")
    patched.append((path.name, bak.name))
    print("Backup ->", bak)
    print("PATCHED ->", path)

print("PATCHED_FILES=" + str(len(patched)))
for n,b in patched:
    print("  -", n, "backup:", b)
