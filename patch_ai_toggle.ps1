# ============================
# TradeAlerts – AI Toggle Patch
# ============================

Write-Host "[1/5] Backing up files..." -ForegroundColor Cyan

$files = @("layout.html", "script.js", "dashboard.py")
foreach ($f in $files) {
    $src = "C:\TradeAlerts\$f"
    if (Test-Path $src) {
        Copy-Item $src "$src.bak-ai-$(Get-Date -Format 'yyyyMMdd-HHmmss')" -Force
        Write-Host "Backed up $f"
    }
}

# -----------------------------
# 2. Patch layout.html
# -----------------------------

Write-Host "[2/5] Patching layout.html..." -ForegroundColor Cyan
$layout = "C:\TradeAlerts\layout.html"
(Get-Content $layout) -replace '<div id="live-mode-toggle"(.*?)</div>',
'$0
    <div class="ai-toggle">
      <label class="ai-toggle-label">
        <input type="checkbox" id="ai-enabled-toggle">
        <span>AI Advisor 🤖</span>
      </label>
    </div>' | Set-Content $layout -Encoding UTF8


# -----------------------------
# 3. Patch script.js
# -----------------------------

Write-Host "[3/5] Patching script.js..." -ForegroundColor Cyan
$script = "C:\TradeAlerts\script.js"
$js = Get-Content $script -Raw

if ($js -notmatch "AI TOGGLE") {
    $insert = @"
  
// --- AI TOGGLE ---
const aiToggle = document.querySelector("#ai-enabled-toggle");
if (aiToggle) {
    aiToggle.addEventListener("change", async () => {
        try {
            const resp = await fetch("/live/ai_toggle", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ enabled: aiToggle.checked })
            });
            console.log("[AI]", await resp.json());
        } catch (e) {
            console.error("AI toggle error", e);
        }
    });
}

"@

    $js -replace '// LIVE MODE LOADED', "// LIVE MODE LOADED`n$insert" |
    Set-Content $script -Encoding UTF8
}


# -----------------------------
# 4. Patch dashboard.py
# -----------------------------

Write-Host "[4/5] Patching dashboard.py..." -ForegroundColor Cyan
$dash = "C:\TradeAlerts\dashboard.py"
$py = Get-Content $dash -Raw

if ($py -notmatch "def live_ai_toggle"):
    $patch = @"
@app.route("/live/ai_toggle", methods=["POST"])
@always_json
def live_ai_toggle():
    \"\"\"Toggle AI Advisor on/off for Day mode via UI.\"\"\"
    try:
        body = request.get_json(force=True, silent=True) or {}
        enabled = bool(body.get("enabled"))
    except Exception:
        enabled = False

    day_settings_path = Path("C:/TradeAlerts/live_settings_day.json")
    data = json.loads(day_settings_path.read_text("utf-8"))

    ai_cfg = data.get("ai") or {}
    ai_cfg.setdefault("use_entries", True)
    ai_cfg.setdefault("use_exits", True)
    ai_cfg["enabled"] = enabled
    data["ai"] = ai_cfg

    day_settings_path.write_text(json.dumps(data, indent=2), "utf-8")

    return {
        "ok": True,
        "ai": {
            "enabled": ai_cfg["enabled"],
            "use_entries": ai_cfg["use_entries"],
            "use_exits": ai_cfg["use_exits"],
        },
    }

"@

    # Insert the route above live_mode()
    $py -replace 'def live_mode', "$patch`ndef live_mode" |
    Set-Content $dash -Encoding UTF8
}


# -----------------------------
# 5. Ensure live_settings_day.json has ai block
# -----------------------------

Write-Host "[5/5] Ensuring live_settings_day.json contains ai config..." -ForegroundColor Cyan

$settings = "C:\TradeAlerts\live_settings_day.json"
$json = Get-Content $settings -Raw | ConvertFrom-Json

if (-not $json.PSObject.Properties.Name.Contains("ai")) {
    $json | Add-Member -Name ai -Value @{ 
        enabled = $false
        use_entries = $true
        use_exits = $true
    } -MemberType NoteProperty
}

($json | ConvertTo-Json -Depth 6) | Set-Content $settings -Encoding UTF8

Write-Host "`nPatch complete! Restart dashboard:" -ForegroundColor Green
Write-Host "    python C:\TradeAlerts\dashboard.py" -ForegroundColor Yellow
