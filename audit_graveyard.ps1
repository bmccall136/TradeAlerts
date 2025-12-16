# C:\TradeAlerts\audit_graveyard.ps1
$ErrorActionPreference = "Stop"

$Root = "C:\TradeAlerts"

# Runtime roots (hard-coded strings to avoid Join-Path array parsing weirdness)
$Roots = @(
  "$Root\live_start.py"
  "$Root\dashboard.py"
  "$Root\sell_guard.py"
)

# Collect all project files (exclude _graveyard)
$All = Get-ChildItem $Root -Recurse -File |
  Where-Object { $_.Extension -in ".py",".html",".js",".css" } |
  Where-Object { $_.FullName -notmatch "\\_graveyard\\" } |
  Select-Object -ExpandProperty FullName

# Import patterns (capture module token)
$Patterns = @(
  "from\s+services\.(\w+)\s+import",
  "import\s+services\.(\w+)",
  "from\s+(\w+)\s+import",
  "import\s+(\w+)"
)

$Hit     = New-Object System.Collections.Generic.HashSet[string]
$Visited = New-Object System.Collections.Generic.HashSet[string]
$Queue   = New-Object System.Collections.Generic.Queue[string]
$Used    = New-Object System.Collections.Generic.HashSet[string]

function Add-HitsFromFile([string]$path) {
  if (-not (Test-Path $path)) { return }
  $txt = Get-Content $path -Raw -ErrorAction SilentlyContinue
  if (-not $txt) { return }

  foreach ($p in $Patterns) {
    [regex]::Matches($txt, $p) | ForEach-Object {
      $mod = $_.Groups[1].Value
      if ($mod) { [void]$Hit.Add($mod.ToLower()) }
    }
  }
}

# Seed queue
foreach ($r in $Roots) { $Queue.Enqueue($r) }

while ($Queue.Count -gt 0) {
  $f = $Queue.Dequeue()
  if (-not (Test-Path $f)) { continue }
  if ($Visited.Contains($f)) { continue }
  [void]$Visited.Add($f)

  Add-HitsFromFile $f

  # enqueue discovered modules if they exist
  foreach ($m in $Hit) {
    $cand1 = "$Root\$m.py"
    $cand2 = "$Root\services\$m.py"
    if (Test-Path $cand1) { $Queue.Enqueue($cand1) }
    if (Test-Path $cand2) { $Queue.Enqueue($cand2) }
  }
}

# Mark visited as used
foreach ($v in $Visited) { [void]$Used.Add($v) }

# Mark any hit modules that exist as used
foreach ($m in $Hit) {
  $cand1 = "$Root\$m.py"
  $cand2 = "$Root\services\$m.py"
  if (Test-Path $cand1) { [void]$Used.Add($cand1) }
  if (Test-Path $cand2) { [void]$Used.Add($cand2) }
}

$UsedList  = $Used | Sort-Object
$GraveList = $All | Where-Object { -not $Used.Contains($_) } | Sort-Object

$UsedList  | Set-Content "$Root\used_files.txt"
$GraveList | Set-Content "$Root\graveyard_candidates.txt"

Write-Host "Used files written to used_files.txt"
Write-Host "Candidates written to graveyard_candidates.txt"
Write-Host ("Used: {0}   Graveyard candidates: {1}" -f $UsedList.Count, $GraveList.Count)
