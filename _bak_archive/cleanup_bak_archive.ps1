# --- MOVE instead of DELETE (drop-in) ---
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$archiveRoot = Join-Path $Root "_bak_archive"
$archiveDest = Join-Path $archiveRoot ("moved_baks_" + $ts)

New-Item -ItemType Directory -Force -Path $archiveDest | Out-Null

function Move-SafeFile {
  param(
    [Parameter(Mandatory=$true)][string]$Path,
    [Parameter(Mandatory=$true)][string]$DestDir,
    [switch]$WhatIf
  )

  $leaf = Split-Path $Path -Leaf
  $dest = Join-Path $DestDir $leaf

  # avoid overwrite if same filename already exists
  if (Test-Path $dest) {
    $base = [System.IO.Path]::GetFileNameWithoutExtension($leaf)
    $ext  = [System.IO.Path]::GetExtension($leaf)
    $i = 1
    do {
      $dest = Join-Path $DestDir ("{0}__{1}{2}" -f $base, $i, $ext)
      $i++
    } while (Test-Path $dest)
  }

  if ($WhatIf) {
    "WHATIF  move $Path -> $dest"
  } else {
    Move-Item -LiteralPath $Path -Destination $dest -Force
    "MOVED       $Path -> $dest"
  }
}

# Wherever you currently loop delete candidates, do this instead:
foreach ($f in $DeleteCandidates) {
  Move-SafeFile -Path $f.FullName -DestDir $archiveDest -WhatIf:$WhatIf
}
# --- end move block ---