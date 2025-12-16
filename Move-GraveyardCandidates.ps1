param(
  [string]$Root = (Get-Location).Path,
  [string]$CandidatesFile = ".\graveyard_candidates.txt",

  # Put the 3 files you want to *not* move here:
  [string[]]$ExcludeFiles = @(
    "etrade_auth.py",
    "etrade_auth_flow.py",
    "etrade_auth_helper.py"
  ),

  # Also allow excluding by regex patterns (optional)
  [string[]]$ExcludePatterns = @(
    # example: "^\.git\\", "^venv\\"
  ),

  # Set -DoIt to actually move; otherwise it dry-runs
  [switch]$DoIt
)

$ErrorActionPreference = "Stop"

function Normalize-Path([string]$p) {
  if ([string]::IsNullOrWhiteSpace($p)) { return $null }
  # Allow both absolute and relative paths in the candidates list
  if ([System.IO.Path]::IsPathRooted($p)) { return (Resolve-Path $p).Path }
  return (Resolve-Path (Join-Path $Root $p)).Path
}

if (-not (Test-Path $CandidatesFile)) {
  throw "Missing candidates file: $CandidatesFile"
}

$stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$graveRoot = Join-Path $Root ("graveyard\_graveyard_" + $stamp)
New-Item -ItemType Directory -Force -Path $graveRoot | Out-Null

$raw = Get-Content -LiteralPath $CandidatesFile | Where-Object { $_ -and $_.Trim() }
$moved = 0
$skipped = 0
$missing = 0

foreach ($line in $raw) {
  $p = $line.Trim().Trim('"')

  # quick exclude by filename
  $leaf = Split-Path $p -Leaf
  if ($ExcludeFiles -contains $leaf) {
    Write-Host "EXCLUDE (filename): $p"
    $skipped++
    continue
  }

  # exclude by regex pattern (path string)
  $excludedByPattern = $false
  foreach ($pat in $ExcludePatterns) {
    if ($p -match $pat) { $excludedByPattern = $true; break }
  }
  if ($excludedByPattern) {
    Write-Host "EXCLUDE (pattern): $p"
    $skipped++
    continue
  }

  # resolve to absolute file path
  try {
    $abs = Normalize-Path $p
  } catch {
    # If Resolve-Path fails, maybe it was already moved/deleted
    Write-Host "MISSING: $p"
    $missing++
    continue
  }

  if (-not (Test-Path -LiteralPath $abs)) {
    Write-Host "MISSING: $abs"
    $missing++
    continue
  }

  # compute relative path under root
  $rel = $abs.Substring($Root.Length).TrimStart('\','/')
  $dest = Join-Path $graveRoot $rel
  $destDir = Split-Path $dest -Parent
  New-Item -ItemType Directory -Force -Path $destDir | Out-Null

  if ($DoIt) {
    Move-Item -LiteralPath $abs -Destination $dest -Force
    Write-Host "MOVED: $rel"
  } else {
    Write-Host "DRYRUN: would move $rel -> graveyard"
  }
  $moved++
}

Write-Host ""
Write-Host "Done."
Write-Host "Graveyard: $graveRoot"
Write-Host "Moved: $moved   Excluded: $skipped   Missing: $missing"
