Get-CimInstance Win32_Process -Filter "Name='python.exe'" |
  Where-Object { $_.CommandLine -match 'sell_guard.py' } |
  ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
