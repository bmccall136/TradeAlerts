import os
from datetime import datetime

# Create restart_scanner.sh script content
restart_script = """#!/bin/bash
# Kill scanner if running
if [ -f scanner_pid.txt ]; then
  pid=$(cat scanner_pid.txt)
  echo "Killing scanner PID $pid"
  kill $pid 2>/dev/null
  rm scanner_pid.txt
fi

# Start scanner.py in background
echo "Starting scanner..."
nohup python3 scanner.py > scanner.log 2>&1 &
echo $! > scanner_pid.txt
echo "Scanner started with PID $(cat scanner_pid.txt)"
"""

# Save the script to a file
script_path = "/mnt/data/restart_scanner.sh"
with open(script_path, "w") as f:
    f.write(restart_script)

# Make it executable
os.chmod(script_path, 0o755)

script_path
