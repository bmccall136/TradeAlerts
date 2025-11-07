# C:\TradeAlerts\auth_shortcut.py
import subprocess
import sys
from pathlib import Path

# 👇 update this path if your .bat lives elsewhere or has a different name
BAT_PATH = Path(r"C:\TradeAlerts\Etrade Auth.bat")

def launch():
    """
    Launch the E*TRADE auth batch file in a NEW console window (Windows).
    Returns (ok: bool, error: str|None)
    """
    try:
        if not BAT_PATH.exists():
            return False, f"Batch file not found: {BAT_PATH}"

        # start "" "C:\path\file.bat"
        # Using START so it spawns a separate console and doesn't block Flask.
        subprocess.Popen(
            ["cmd.exe", "/c", "start", "", str(BAT_PATH)],
            creationflags=0x00000010,  # CREATE_NEW_CONSOLE
            shell=False
        )
        return True, None
    except Exception as e:
        return False, str(e)

if __name__ == "__main__":
    ok, err = launch()
    print("ok" if ok else f"error: {err}")
    sys.exit(0 if ok else 1)
