param(
    [string]$Root = (Get-Location).Path,
    [string]$CandidatesFile = "graveyard_candidates.txt",
    [string]$DestDir = "graveyard",
    [string[]]$Exclude = @(
        "settings.py",
        "etrade_auth.py",
        "etrade_auth_flow.py",
        "etrade_auth_helper.py"
    ),
    [switch]$WhatIf
)

$ErrorActionPreference = "Stop"

function Resolve-IfExists {
    param([string]$Path)
    try {
        $rp = Resolve-Path -LiteralPath $Path -ErrorAction Stop
        return $rp.Path
    } catch {
        return $null
    }
}

$Root = (Resolve-Path -LiteralPath $Root).Path
$CandidatesPath = Join-Path $Root $CandidatesFile

if (-not (Test-Path -LiteralPath $CandidatesPath)) {
    Write-Error "Missing candidates file: $CandidatesPath"
    exit 1
}

$DestRoot = Join-Path $Root $DestDir
if (-not (Test-Path -LiteralPath $DestRoot)) {
    if ($WhatIf) {
        Write-Host "WHATIF: would create $DestRoot"
    } else {
        New-Item -ItemType Directory -Path $DestRoot | Out-Null
    }
}

# Normalize exclusions to lowercase fullnames for comparison
$ExcludeSet = New-Object 'System.Collections.Generic.HashSet[string]'
foreach ($e in $Exclude) { [void]$ExcludeSet.Add(($e.ToLower())) }

$moved = 0
$skipped = 0
$missing = 0

$lines = Get-Content -LiteralPath $CandidatesPath | Where-Object { $_ -and $_.Trim() -ne "" }

foreach ($line in $lines) {
    $p = $line.Trim()

    # Support either full path or relative path in the file
    if ([System.IO.Path]::IsPathRooted($p)) {
        $src = $p
    } else {
        $src = Join-Path $Root $p
    }

    $srcResolved = Resolve-IfExists -Path $src
    if (-not $srcResolved) {
        $missing++
        continue
    }

    $leaf = [System.IO.Path]::GetFileName($srcResolved).ToLower()
    if ($ExcludeSet.Contains($leaf)) {
        $skipped++
        continue
    }

    # Preserve relative structure under Root
    $rel = $srcResolved.Substring($Root.Length).TrimStart('\','/')
    $dst = Join-Path $DestRoot $rel
    $dstDir = Split-Path -Parent $dst

    if ($WhatIf) {
        Write-Host "WHATIF: move `"$srcResolved`" -> `"$dst`""
        $moved++
        continue
    }

    if (-not (Test-Path -LiteralPath $dstDir)) {
        New-Item -ItemType Directory -Path $dstDir -Force | Out-Null
    }

    Move-Item -LiteralPath $srcResolved -Destination $dst -Force
    $moved++
}

Write-Host "Done."
Write-Host "Moved:   $moved"
Write-Host "Skipped: $skipped (excluded)"
Write-Host "Missing: $missing (not found)"
Write-Host "Dest:    $DestRoot"
