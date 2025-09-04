Set-Location C:\TradeAlerts
New-Item -ItemType Directory -Force -Path .\logs | Out-Null
$env:PYTHONUNBUFFERED = 1
python .\sell_guard.py *>&1 | Tee-Object -FilePath .\logs\sell_guard.log -Append
