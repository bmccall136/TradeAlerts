# test_sim.py
from services.simulation_service import init_db, process_trade, get_simulation_state
from config import Config

print("DB path:", Config.SIM_DB)
init_db()
process_trade("REPLTEST", 2, 123.45)
state = get_simulation_state()
print(state)
