$py="C:\Users\bmccall\AppData\Local\Programs\Python\Python311\python.exe"
if(!(Test-Path $py)){ $py="python.exe" }

$env:GUARDRAILS_ENABLED="true"
$env:LIVE_SAFE_MODE="true"
$env:YF_USE_CURL="1"

Set-Location "C:\TradeAlerts"

Write-Host "--------------------------------------------------"
Write-Host "GUARDRAILS_ENABLED=$env:GUARDRAILS_ENABLED"
Write-Host "LIVE_SAFE_MODE=$env:LIVE_SAFE_MODE"
Write-Host "YF_USE_CURL=$env:YF_USE_CURL"
Write-Host "Python: $py"
Write-Host "CWD: $(Get-Location)"
Write-Host "Launching: $py -u C:\TradeAlerts\live_start.py"
Write-Host "--------------------------------------------------"

& $py -u "C:\TradeAlerts\live_start.py"

Write-Host ""
Write-Host "--------------------------------------------------"
Write-Host "Window will stay open. Close it when you are done."
Write-Host "--------------------------------------------------"
Read-Host
