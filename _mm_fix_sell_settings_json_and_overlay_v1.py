import json, shutil, datetime, pathlib, re

TS = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

ROOT = pathlib.Path(r"C:\TradeAlerts")
DAY  = ROOT / "sell_guard_settings_day.json"
SWING= ROOT / "sell_guard_settings_swing.json"

TSELL = ROOT / "templates" / "settings_sell.html"
TBUY  = ROOT / "templates" / "settings_buy.html"

def backup(p: pathlib.Path, tag: str):
    bak = p.with_suffix(p.suffix + f".bak_{tag}_{TS}")
    shutil.copy2(p, bak)
    print(f"Backup -> {bak}")
    return bak

def write_json(p: pathlib.Path, obj: dict, tag: str):
    if p.exists():
        backup(p, tag)
    txt = json.dumps(obj, indent=2, sort_keys=True)
    p.write_text(txt + "\n", encoding="utf-8")
    print(f"WROTE -> {p}")

# These are the keys settings_sell.html is already trying to render (sell_guard.*)
# Goal: make the JSON actually contain them so the UI has something to bind to.
def build_day():
    return {
      "ai": {
        "enabled": False,
        "use_entries": False,
        "use_exits": True
      },
      "sell_guard": {
        "mode": "DAY",

        # execution window / pacing
        "sell_window_start_et": "09:31",
        "sell_window_end_et": "15:58",
        "interval_sec": 15,
        "throttle_ms": 300,
        "use_extended_hours": False,

        # order placement
        "limit_from": "BID",
        "limit_offset_bps": -1,
        "normalize_tick": True,
        "max_place_attempts": 6,

        # targets / stops (primary)
        "target_gain_pct": 1.00,
        "target_bps": 100,
        "stop_bps": 80,

        # intraday stoploss guard
        "allow_intraday_stoploss": True,
        "intraday_stoploss_pct": 0.85,
        "pdt_allow_stop": True,

        # timeout/hold behavior
        "enable_timeout_exits": True,
        "min_hold_minutes": 3,
        "max_hold_minutes": 180,
        "timeout_exit_pct": 0.35,
        "min_hold_days": 0,

        # protect/trail (let winners run)
        "sell_protect_after_mins": 6,
        "protect_min_gain_pct": 0.35,
        "trail_arm_gain_pct": 0.70,
        "protect_trail_arm_pct": 0.70,
        "protect_trail_pct": 0.45,
        "trail_backoff_pct": 0.25,

        # misc safety knobs
        "avoid_daytrades": False,
        "blocklist": [],
        "only_allow_symbol": ""
      },

      # Stale relief is for SWING “bags”. Keep it off for DAY.
      "stale_relief_exit": {
        "enabled": False,
        "min_hold_days": 2,
        "relief_gain_pct": 0.8,
        "runner_max_gain_pct": 1.5,
        "require_non_trend_regime": False,
        "regime_conf_max": 75
      }
    }

def build_swing():
    return {
      "ai": {
        "enabled": False,
        "use_entries": False,
        "use_exits": True
      },
      "sell_guard": {
        "mode": "SWING",

        "sell_window_start_et": "09:31",
        "sell_window_end_et": "15:58",
        "interval_sec": 30,
        "throttle_ms": 500,
        "use_extended_hours": False,

        "limit_from": "BID",
        "limit_offset_bps": -1,
        "normalize_tick": True,
        "max_place_attempts": 8,

        "target_gain_pct": 2.50,
        "target_bps": 250,
        "stop_bps": 120,

        "allow_intraday_stoploss": True,
        "intraday_stoploss_pct": 1.10,
        "pdt_allow_stop": True,

        "enable_timeout_exits": True,
        "min_hold_minutes": 15,
        "max_hold_minutes": 7200,
        "timeout_exit_pct": 0.50,
        "min_hold_days": 1,

        "sell_protect_after_mins": 30,
        "protect_min_gain_pct": 0.75,
        "trail_arm_gain_pct": 1.25,
        "protect_trail_arm_pct": 1.25,
        "protect_trail_pct": 0.85,
        "trail_backoff_pct": 0.35,

        "avoid_daytrades": False,
        "blocklist": [],
        "only_allow_symbol": ""
      },

      "stale_relief_exit": {
        "enabled": True,
        "min_hold_days": 2,
        "relief_gain_pct": 0.8,
        "runner_max_gain_pct": 1.5,
        "require_non_trend_regime": False,
        "regime_conf_max": 75
      }
    }

def patch_overlay_template(p: pathlib.Path):
    if not p.exists():
        print(f"SKIP (missing): {p}")
        return
    txt = p.read_text(encoding="utf-8", errors="replace")

    # Find the overlay UI block by your existing V5 markers and swap it with a dark-themed version.
    rx = re.compile(r"(?s)<!--\s*MM_REGIME_EXIT_OVERLAY_UI_V5_START\s*-->.*?<!--\s*MM_REGIME_EXIT_OVERLAY_UI_V5_END\s*-->")
    if not rx.search(txt):
        print(f"NO_OVERLAY_MARKERS -> {p} (not changed)")
        return

    backup(p, "overlay_dark_v1")

    block = r'''<!-- MM_REGIME_EXIT_OVERLAY_UI_V5_START -->
<style>
  /* MM_REO_DARKSTYLE_V1 */
  #mm-regime-exit-overlay-card{
    background: rgba(255,255,255,.04);
    border: 1px solid rgba(255,255,255,.10);
    color: rgba(255,255,255,.92);
  }
  #mm-regime-exit-overlay-card .card-header{
    background: rgba(0,0,0,.25);
    border-bottom: 1px solid rgba(255,255,255,.10);
    color: rgba(255,255,255,.95);
    font-weight: 600;
  }
  #mm-regime-exit-overlay-card label{
    color: rgba(255,255,255,.70);
    font-size: 12px;
  }
  #mm-regime-exit-overlay-card .form-control,
  #mm-regime-exit-overlay-card .form-select{
    background: rgba(0,0,0,.35);
    border: 1px solid rgba(255,255,255,.12);
    color: rgba(255,255,255,.92);
  }
</style>

<div class="card mb-3" id="mm-regime-exit-overlay-card">
  <div class="card-header d-flex align-items-center justify-content-between">
    <div>Regime Exit Overlay</div>
    <div style="opacity:.65;font-size:12px;">target_mult / stop_mult / time_mult</div>
  </div>
  <div class="card-body">
    <div class="row g-2 align-items-center">
      <div class="col-12" style="opacity:.65;font-size:12px;">
        Applies on regime changes only. Stored in <code>regime_exit_overlay</code>. Active file is chosen by <code>live_mode.txt</code>.
      </div>

      {% for r in ["TREND","CHOP","DEAD","UNKNOWN"] %}
      <div class="col-12 col-lg-3"><strong>{{r}}</strong></div>
      <div class="col-4 col-lg-3">
        <label class="form-label mb-1">target</label>
        <input class="form-control form-control-sm" type="number" step="0.01" data-reo="{{r}}" data-reo-k="target_mult">
      </div>
      <div class="col-4 col-lg-3">
        <label class="form-label mb-1">stop</label>
        <input class="form-control form-control-sm" type="number" step="0.01" data-reo="{{r}}" data-reo-k="stop_mult">
      </div>
      <div class="col-4 col-lg-3">
        <label class="form-label mb-1">time</label>
        <input class="form-control form-control-sm" type="number" step="0.01" data-reo="{{r}}" data-reo-k="time_mult">
      </div>
      {% endfor %}
    </div>
  </div>
</div>
<!-- MM_REGIME_EXIT_OVERLAY_UI_V5_END -->'''

    txt2 = rx.sub(block, txt)
    p.write_text(txt2, encoding="utf-8")
    print(f"PATCHED -> {p} (overlay dark style)")

# 1) JSONs first (this is the “real fix” so the SELL UI has something to show)
write_json(DAY, build_day(), "sell_json_full_v1")
write_json(SWING, build_swing(), "sell_json_full_v1")

# 2) Make overlay card match the theme (cosmetic but removes the “white slab”)
patch_overlay_template(TSELL)
patch_overlay_template(TBUY)

print("DONE.")
print("Next:")
print("  1) Ctrl+F5 the SELL Settings page")
print("  2) Expand TARGET/STOP, TIMEOUT/HOLD, PROTECT/TRAIL, FILTERS/SAFETY -> you should now see fields")
print("  3) Hit Save and confirm the JSONs now contain sell_guard.* keys")