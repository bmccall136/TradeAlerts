(function () {
  "use strict";

  // -------- helpers --------
  function $(id) { return document.getElementById(id); }

  function enc(x) { return encodeURIComponent(String(x ?? "")); }

  async function fetchJson(url, opts) {
    const resp = await fetch(url, Object.assign({ cache: "no-store" }, opts || {}));
    const text = await resp.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch (e) {}

    if (!resp.ok) {
      const msg = (data && (data.error || data.message)) ? (data.error || data.message) : ("HTTP " + resp.status);
      throw new Error(msg);
    }
    return data;
  }

  function showMsg(txt, ok) {
    const box = $("mm-msg");
    if (!box) return;
    box.textContent = txt || "";
    box.className = ok ? "mm-msg mm-ok" : "mm-msg mm-bad";
    box.style.display = txt ? "block" : "none";
  }

  function setStatus(txt, ok) {
    const el = $("mm-status");
    if (!el) return;
    el.textContent = txt || "";
    el.style.color = ok ? "#ffe900" : "#ff5c5c";
  }

  function getKind() {
    const el = $("mm-kind");
    return el ? String(el.value || "buy").toLowerCase() : "buy";
  }

  function getProfile() {
    const sel = $("mm-profile");
    const v = sel ? String(sel.value || "DAY") : "DAY";
    return v.toUpperCase().includes("SWING") ? "SWING" : "DAY";
  }

  function getBucket() {
    const sel = $("mm-bucket");
    const v = sel ? String(sel.value || "today") : "today";
    const vv = v.toLowerCase();
    if (vv === "7d" || vv === "30d" || vv === "all") return vv;
    return "today";
  }

  function setProfileUI(mode) {
    const sel = $("mm-profile");
    if (!sel) return;
    sel.value = (String(mode || "DAY").toUpperCase().includes("SWING")) ? "SWING" : "DAY";
  }

  function setBucketUI(bucket) {
    const sel = $("mm-bucket");
    if (!sel) return;
    sel.value = bucket || "today";
  }

  // -------- grouping (BUY + SELL) --------
  // Indicator toggles (these drive the scoreboard rows)
  const INDICATORS = [
    { id: "macd",  label: "MACD",  onKey: "macd_on" },
    { id: "rsi",   label: "RSI",   onKey: "rsi_on" },
    { id: "vwap",  label: "VWAP",  onKey: "vwap_on" },
    { id: "bb",    label: "BB",    onKey: "bb_on" },
    { id: "adx",   label: "ADX",   onKey: "adx_on" },
    { id: "vol",   label: "VOL",   onKey: "vol_on" },
    { id: "atr",   label: "ATR",   onKey: "atr_on" },
    { id: "gap",   label: "GAP",   onKey: "gap_on" },
    { id: "range", label: "RANGE", onKey: "range_on" },
    { id: "sma",   label: "SMA",   onKey: "sma_on" },
    { id: "super", label: "SUPER", onKey: "super_on" },
  ];

  // Indicator tuning keys ? shown under indicators section (not in required/other)
  const INDICATOR_KEYS = new Set([
    "macd_fast","macd_slow","macd_signal","macd_hist_on",
    "rsi_len","rsi_overbought","rsi_oversold","rsi_slope_on",
    "vwap_threshold",
    "bb_length","bb_std","bb_breakout_on",
    "adx_len","adx_threshold",
    "vol_multiplier",
    "atr_pct","atr_pct_on","atr_threshold",
    "gap_pct",
    "range_pct",
    "sma_length",
    "price_sma_len","price_sma_on",
    "super_fast","super_slow","super_signal",
  ]);

  // Required Signals section: strict_buy_signals + required_filters + require_sma20
  const REQUIRED_KEYS = new Set(["strict_buy_signals","required_filters","require_sma20","min_signals"]);

  // Units (display only)
  const UNITS = {
    "sell_after_days": "days",
    "poll_interval": "sec",
    "scan_sleep_secs": "sec",
    "buy_cooldown_min": "min",
    "max_per_trade": "$",
  };

  // -------- UI builders --------
  function mkRow(labelText) {
    const row = document.createElement("div");
    row.className = "mm-row";
    const lab = document.createElement("div");
    lab.className = "mm-lab";
    lab.textContent = labelText;
    const ctl = document.createElement("div");
    ctl.className = "mm-ctl";
    row.appendChild(lab);
    row.appendChild(ctl);
    return { row, ctl };
  }

  function mkToggle(checked) {
    const inp = document.createElement("input");
    inp.type = "checkbox";
    inp.className = "mm-toggle";
    inp.checked = !!checked;
    return inp;
  }

  function mkNum(val) {
    const inp = document.createElement("input");
    inp.type = "number";
    inp.step = "any";
    inp.className = "mm-input";
    inp.value = (val === null || val === undefined) ? "" : String(val);
    return inp;
  }

  function mkText(val) {
    const inp = document.createElement("input");
    inp.type = "text";
    inp.className = "mm-input";
    inp.value = (val === null || val === undefined) ? "" : String(val);
    return inp;
  }

  function mkSelect(options, selected) {
    const sel = document.createElement("select");
    sel.className = "mm-select";
    for (const o of options) {
      const opt = document.createElement("option");
      opt.value = String(o.value);
      opt.textContent = o.label;
      sel.appendChild(opt);
    }
    sel.value = String(selected);
    return sel;
  }

  function niceLabel(k) {
    return String(k || "")
      .replace(/_/g, " ")
      .replace(/\b(on)\b/g, "enabled")
      .replace(/\b(len)\b/g, "length")
      .replace(/\bpct\b/g, "%")
      .replace(/\bmax\b/g, "max")
      .replace(/\bmin\b/g, "min")
      .replace(/\bai\b/g, "AI")
      .replace(/\bvwap\b/g, "VWAP")
      .replace(/\bmacd\b/g, "MACD")
      .replace(/\brsi\b/g, "RSI")
      .replace(/\badx\b/g, "ADX")
      .toUpperCase();
  }

  function renderScoreboard(host, data, counts) {
    host.innerHTML = "";

    const table = document.createElement("div");
    table.className = "mm-scoreboard";

    // header
    const head = document.createElement("div");
    head.className = "mm-sb mm-sb-head";
    head.innerHTML = '<div>INDICATOR</div><div>ENABLED</div><div>HITS</div>';
    table.appendChild(head);

    for (const ind of INDICATORS) {
      const row = document.createElement("div");
      row.className = "mm-sb";

      const c1 = document.createElement("div");
      c1.textContent = ind.label;

      const c2 = document.createElement("div");
      const t = mkToggle(!!data[ind.onKey]);
      t.dataset.key = ind.onKey;
      t.dataset.kind = "bool";
      c2.appendChild(t);

      const c3 = document.createElement("div");
      const n = counts && typeof counts[ind.id] === "number" ? counts[ind.id] : 0;
      c3.textContent = String(n);

      row.appendChild(c1);
      row.appendChild(c2);
      row.appendChild(c3);
      table.appendChild(row);
    }

    host.appendChild(table);
  }

  function renderForm(host, data, keys) {
    host.innerHTML = "";
    const d = (data && typeof data === "object") ? data : {};

    for (const k of keys) {
      if (!(k in d)) continue;

      const v = d[k];
      const { row, ctl } = mkRow(niceLabel(k));
      let control = null;

      if (k === "required_filters" && Array.isArray(v)) {
        // checkbox list for required_filters based on known indicator ids
        const wrap = document.createElement("div");
        wrap.className = "mm-checklist";

        const setV = new Set((v || []).map(x => String(x || "").toLowerCase()));
        const opts = ["macd","rsi","vwap","bb","adx","vol","atr","gap","range","sma","super"];

        for (const opt of opts) {
          const item = document.createElement("label");
          item.className = "mm-check";
          const cb = document.createElement("input");
          cb.type = "checkbox";
          cb.checked = setV.has(opt);
          cb.dataset.key = k;
          cb.dataset.kind = "arr";
          cb.dataset.item = opt;
          item.appendChild(cb);
          const txt = document.createElement("span");
          txt.textContent = opt.toUpperCase();
          item.appendChild(txt);
          wrap.appendChild(item);
        }

        ctl.appendChild(wrap);
      }
      else if (k === "strict_buy_signals" || k === "min_signals") {
        const opts = [];
        for (let i = 1; i <= 10; i++) opts.push({ value: i, label: String(i) });
        control = mkSelect(opts, Number(v || 1));
        control.dataset.key = k;
        control.dataset.kind = "num";
        ctl.appendChild(control);
      }
      else if (typeof v === "boolean") {
        control = mkToggle(!!v);
        control.dataset.key = k;
        control.dataset.kind = "bool";
        ctl.appendChild(control);
      }
      else if (typeof v === "number") {
        control = mkNum(v);
        control.dataset.key = k;
        control.dataset.kind = "num";
        ctl.appendChild(control);
      }
      else if (typeof v === "string") {
        control = mkText(v);
        control.dataset.key = k;
        control.dataset.kind = "str";
        ctl.appendChild(control);
      }
      else {
        // ignore complex objects in this human UI (no raw JSON shown)
        const note = document.createElement("div");
        note.className = "mm-note";
        note.textContent = "Hidden (advanced object).";
        ctl.appendChild(note);
      }

      // units (display only)
      const unit = UNITS[k];
      if (unit) {
        const u = document.createElement("span");
        u.className = "mm-unit";
        u.textContent = unit;
        ctl.appendChild(u);
      }

      host.appendChild(row);
    }
  }

  function readInputsInto(base) {
    const out = Object.assign({}, base || {});
    const root = $("mm-root") || document;

    // standard inputs
    const nodes = root.querySelectorAll("[data-key]");
    for (const n of nodes) {
      const k = n.dataset.key;
      const kind = n.dataset.kind;

      if (!k) continue;

      if (kind === "bool") out[k] = !!n.checked;
      else if (kind === "num") {
        const x = Number(n.value);
        out[k] = Number.isFinite(x) ? x : 0;
      }
      else if (kind === "str") out[k] = String(n.value ?? "");
      // arrays handled below
    }

    // required_filters checklist
    const arrNodes = root.querySelectorAll('input[type="checkbox"][data-kind="arr"][data-key="required_filters"]');
    if (arrNodes && arrNodes.length) {
      const vals = [];
      for (const cb of arrNodes) {
        if (cb.checked) vals.push(String(cb.dataset.item || "").toLowerCase());
      }
      out["required_filters"] = vals;
    }

    // Ensure defaults
    if (!out["strict_buy_signals"] || out["strict_buy_signals"] < 1) out["strict_buy_signals"] = 1;

    return out;
  }

  // -------- API --------
  async function apiLoad(kind, mode) {
    return await fetchJson(`/api/settings/load?kind=${enc(kind)}&mode=${enc(mode)}&cb=${Date.now()}`);
  }

  async function apiSave(kind, mode, dataObj) {
    const payload = { kind, mode, data: dataObj || {} };
    return await fetchJson("/api/settings/save", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
  }

  async function apiCounts(bucket) {
    return await fetchJson(`/api/signal_fires?bucket=${enc(bucket)}&cb=${Date.now()}`);
  }

  // -------- boot --------
  const STATE = { kind: getKind(), mode: "DAY", data: {}, counts: {} };

  async function reloadAll() {
    showMsg("");
    setStatus("Loading?", true);

    const kind = getKind();
    const mode = getProfile();
    const bucket = getBucket();

    const loaded = await apiLoad(kind, mode);
    if (!loaded || loaded.ok === false) throw new Error((loaded && loaded.error) ? loaded.error : "Load failed");

    STATE.kind = kind;
    STATE.mode = mode;
    STATE.data = (loaded.data && typeof loaded.data === "object") ? loaded.data : {};

    // Counts (scoreboard) ? independent of enabled flags
    let counts = {};
    try {
      const c = await apiCounts(bucket);
      counts = (c && c.counts && typeof c.counts === "object") ? c.counts : {};
    } catch (e) {
      counts = {};
    }
    STATE.counts = counts;

    setProfileUI(mode);
    setBucketUI(bucket);

    // Partition keys
    const keys = Object.keys(STATE.data || {}).sort((a,b) => a.localeCompare(b));

    const indicatorKeys = [];
    const requiredKeys = [];
    const otherKeys = [];

    for (const k of keys) {
      if (INDICATORS.some(x => x.onKey === k) || INDICATOR_KEYS.has(k)) indicatorKeys.push(k);
      else if (REQUIRED_KEYS.has(k)) requiredKeys.push(k);
      else otherKeys.push(k);
    }

    // Render
    renderScoreboard($("mm-scoreboard"), STATE.data, STATE.counts);
    renderForm($("mm-indicators-form"), STATE.data, indicatorKeys.filter(k => INDICATOR_KEYS.has(k)));

    // Required section: prefer strict_buy_signals as the ?Required Signals? control
    // If both exist, show strict_buy_signals and hide min_signals (still preserved in JSON)
    const reqShow = [];
    if ("strict_buy_signals" in STATE.data) reqShow.push("strict_buy_signals");
    if ("required_filters" in STATE.data) reqShow.push("required_filters");
    if ("require_sma20" in STATE.data) reqShow.push("require_sma20");
    $("mm-required-form").innerHTML = "";
    renderForm($("mm-required-form"), STATE.data, reqShow);

    renderForm($("mm-other-form"), STATE.data, otherKeys);

    setStatus(`Loaded ${kind.toUpperCase()}/${mode} (${bucket.toUpperCase()})`, true);
    showMsg(`Loaded ${kind.toUpperCase()}/${mode} (${bucket.toUpperCase()})`, true);
  }

  async function saveAll() {
    showMsg("");
    setStatus("Saving?", true);

    // Apply UI edits into the loaded JSON (preserve unknown keys)
    const merged = readInputsInto(STATE.data);
    STATE.data = merged;

    const out = await apiSave(STATE.kind, STATE.mode, merged);
    if (!out || out.ok === false) throw new Error((out && out.error) ? out.error : "Save failed");

    setStatus("Saved ?", true);
    showMsg(out.path ? ("Saved: " + out.path) : "Saved", true);

    // Reload for truth
    await reloadAll();
  }

  function hook() {
    const btnReload = $("mm-reload");
    const btnSave = $("mm-save");
    const selProfile = $("mm-profile");
    const selBucket = $("mm-bucket");

    if (btnReload) btnReload.addEventListener("click", (e) => { e.preventDefault(); reloadAll().catch(onErr); });
    if (btnSave) btnSave.addEventListener("click", (e) => { e.preventDefault(); saveAll().catch(onErr); });

    if (selProfile) selProfile.addEventListener("change", () => reloadAll().catch(onErr));
    if (selBucket) selBucket.addEventListener("change", () => reloadAll().catch(onErr));
  }

  function onErr(e) {
    console.error("[settings] error:", e);
    const msg = (e && e.message) ? e.message : String(e);
    showMsg(msg, false);
    setStatus("Error", false);
  }

  document.addEventListener("DOMContentLoaded", () => {
    try {
      hook();
      reloadAll().catch(onErr);
    } catch (e) {
      onErr(e);
    }
  }, { once: true });

})();