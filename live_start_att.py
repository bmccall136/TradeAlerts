# C:\TradeAlerts\live_start_att.py
import logging, sys
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

# ensure the patch is applied before anything else touches LiveBroker
import services.broker_patch  # noqa: F401

# now run your existing launcher
import live_start as _ls

if hasattr(_ls, "main"):
    sys.exit(_ls.main())
# Fallback if main() isn’t exposed for some reason:
exec(open(r"C:\TradeAlerts\live_start.py", "r", encoding="utf-8").read(), {"__name__":"__main__"})
