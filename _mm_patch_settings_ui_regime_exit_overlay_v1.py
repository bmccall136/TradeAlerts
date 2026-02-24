import re, shutil, datetime, pathlib

ROOT = pathlib.Path(r"C:\TradeAlerts\templates")
assert ROOT.exists(), f"missing templates dir: {ROOT}"

ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

MARK_START = "MM_REGIME_EXIT_OVERLAY_UI_V1_START"
MARK_END   = "MM_REGIME_EXIT_OVERLAY_UI_V1_END"

# Heuristic: patch templates that look like "settings" and contain a JSON textarea
candidates = sorted([p for p in ROOT.glob("*.html") if "setting" in p.name.lower()])

ui_block = f"""
<!-- {MARK_START} -->
<div class="card mb-3" id="mm-regime-exit-overlay-card">
  <div class="card-header d-flex align-items-center justify-content-between">
    <div class="fw-bold">Regime Exit Overlay</div>
    <div class="small text-secondary">target_mult / stop_mult / time_mult</div>
  </div>
  <div class="card-body">
    <div class="row g-2">
      <!-- Regime rows -->
      {""}
    </div>
    <div class="mt-2 small text-secondary">
      Applies on regime changes only. Stored in <code>regime_exit_overlay</code>.
    </div>
  </div>
</div>

<script>
(function(){
  function qs(sel){ return document.querySelector(sel); }
  function qsa(sel){ return Array.prototype.slice.call(document.querySelectorAll(sel)); }

  // Find the JSON textarea (best-effort)
  var ta = qs('textarea[name="settings_json"]') || qs('#settings_json') || qs('textarea#json') || qs('textarea');
  if(!ta) return;

  var regimes = ["TREND","CHOP","DEAD","UNKNOWN"];
  var keys = ["target_mult","stop_mult","time_mult"];

  function parseJSON(){
    try { return JSON.parse(ta.value || "{}"); } catch(e){ return null; }
  }
  function writeJSON(obj){
    try { ta.value = JSON.stringify(obj, null, 2); } catch(e){}
  }
  function ensureOverlay(obj){
    if(!obj || typeof obj !== "object") obj = {};
    if(!obj.regime_exit_overlay || typeof obj.regime_exit_overlay !== "object") obj.regime_exit_overlay = {};
    regimes.forEach(function(r){
      if(!obj.regime_exit_overlay[r] || typeof obj.regime_exit_overlay[r] !== "object") obj.regime_exit_overlay[r] = {};
      keys.forEach(function(k){
        if(typeof obj.regime_exit_overlay[r][k] !== "number"){
          // default 1.0 if missing
          obj.regime_exit_overlay[r][k] = 1.0;
        }
      });
    });
    return obj;
  }

  function hydrateFromJSON(){
    var obj = parseJSON();
    if(!obj) return;
    obj = ensureOverlay(obj);
    regimes.forEach(function(r){
      keys.forEach(function(k){
        var el = qs('[data-mm-reo="'+r+'."+ "'+k+'"]'); // not used
      });
    });
    qsa('[data-mm-reo]').forEach(function(inp){
      var path = (inp.getAttribute("data-mm-reo") || "");
      var parts = path.split(".");
      if(parts.length !== 2) return;
      var r = parts[0], k = parts[1];
      try {
        var v = obj.regime_exit_overlay[r][k];
        if(typeof v === "number" && isFinite(v)) inp.value = String(v);
      } catch(e){}
    });
    // Write back normalized object once so it persists on save
    writeJSON(obj);
  }

  function pushToJSON(){
    var obj = parseJSON();
    if(!obj) return;
    obj = ensureOverlay(obj);
    qsa('[data-mm-reo]').forEach(function(inp){
      var path = (inp.getAttribute("data-mm-reo") || "");
      var parts = path.split(".");
      if(parts.length !== 2) return;
      var r = parts[0], k = parts[1];
      var num = parseFloat(inp.value);
      if(!isFinite(num)) return;
      obj.regime_exit_overlay[r][k] = num;
    });
    writeJSON(obj);
  }

  // Wire input events
  qsa('[data-mm-reo]').forEach(function(inp){
    inp.addEventListener("input", function(){
      pushToJSON();
    });
  });

  // Initial hydrate
  hydrateFromJSON();
})();
</script>
<!-- {MARK_END} -->
"""

def build_rows():
  # Simple bootstrap rows: 4 regimes, each with 3 inputs
  rows = []
  for r in ["TREND","CHOP","DEAD","UNKNOWN"]:
    rows.append(f"""
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
    """)
  return "\n".join(rows)

ui_block = ui_block.replace("{\"\"}", build_rows())

patched = []
skipped = []

for path in candidates:
  txt = path.read_text(encoding="utf-8", errors="replace")

  if MARK_START in txt and MARK_END in txt:
    skipped.append((path.name, "already patched"))
    continue

  # must look like a settings editor page with a textarea
  if "<textarea" not in txt.lower():
    skipped.append((path.name, "no textarea"))
    continue

  # Must look like a settings page (extra heuristic)
  if "settings" not in txt.lower() and "live_settings" not in txt.lower():
    skipped.append((path.name, "doesn't look like settings"))
    continue

  # backup + insert: place block right ABOVE the first textarea (so it's near the editor)
  bak = path.with_suffix(path.suffix + f".bak_reo_ui_v1_{ts}")
  shutil.copy2(path, bak)

  m = re.search(r"(?is)(<textarea\b[^>]*>)", txt)
  if not m:
    skipped.append((path.name, "textarea not found by regex"))
    continue

  insert_at = m.start()
  new_txt = txt[:insert_at] + ui_block + "\n" + txt[insert_at:]

  path.write_text(new_txt, encoding="utf-8")
  patched.append((path.name, str(bak.name)))

print("PATCHED_FILES=" + str(len(patched)))
for n,b in patched:
  print("  -", n, "backup:", b)

print("SKIPPED_FILES=" + str(len(skipped)))
for n,why in skipped:
  print("  -", n, "reason:", why)
