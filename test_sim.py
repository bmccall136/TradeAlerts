# test_sim.py
from config import Config
from services.simulation_service import get_simulation_state, init_db, process_trade

print("DB path:", Config.SIM_DB)
init_db()
process_trade("REPLTEST", 2, 123.45)
state = get_simulation_state()
print(state)
