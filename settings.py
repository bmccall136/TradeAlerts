import os  # ← make sure you have this line!

BASE_DIR = os.path.dirname(__file__)
SIMULATION_DB = os.path.join(BASE_DIR, "simulation.db")
BACKTEST_DB = os.path.join(BASE_DIR, "backtest.db")
# Used to control simulation loop externally (e.g., stop it gracefully)
_sim_stop = False
nuke_db: bool = False
