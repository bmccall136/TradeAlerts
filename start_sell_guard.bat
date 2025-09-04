param(
  [ValidateSet('shadow','live')]
  [string]$Mode = 'live'
)

Set-Location C:\TradeAlerts
New-Item -ItemType Directory -Path .\logs -Force | Out-Null

# If this shell doesn't already have it, uncomment and set your key:
# $env:ETRADE_ACCOUNT_ID_KEY = 'kW8LbkuGisPCK9Ey7C8iWA'

# Path so Python can import your package
$env:PYTHONPATH = 'C:\TradeAlerts'

# ---- Scalp / gate config ----
$env:LIVE_SELL_MODE          = $Mode      # 'shadow' logs only; 'live' places orders
$env:SELL_LIMIT_FROM         = 'bid'      # 'bid' | 'last' | 'mid'
$env:SELL_LIMIT_OFFSET_BPS   = '0'        # e.g., 10 = 0.10% below chosen ref
$env:SELL_THROTTLE_MS        = '30000'    # 30s per symbol
$env:SCALP_TARGET_BPS        = '40'       # +0.40% target
$env:SCALP_STOP_BPS          = '80'       # -0.80% stop
$env:SCALP_MAX_HOLD_MINS     = '120'      # max hold time

$log = 'C:\TradeAlerts\logs\sell_guard.log'

# Run and tee output to a log file
python -u .\sell_guard.py 2>&1 | Tee-Object -FilePath $log -Append
