import os, json
from services.contributions import CONTRIB_PATH, _load, get_total_contributions

print("CONTRIB_PATH:", CONTRIB_PATH)
print("os.path.exists:", os.path.exists(CONTRIB_PATH))

if os.path.exists(CONTRIB_PATH):
    print("\n--- Raw bytes (first 120) ---")
    with open(CONTRIB_PATH, "rb") as f:
        data = f.read()
    print(repr(data[:120]))

    try:
        text = data.decode("utf-8", errors="replace")
        print("\n--- Decoded text ---")
        print(text)
        parsed = json.loads(text)
        print("\n--- json.loads(parsed) ---")
        print(parsed)
    except Exception as e:
        print("\n!!! json.loads failed:", e)

print("\n_load():", _load())
print("get_total_contributions('2025-08-22'):", get_total_contributions("2025-08-22"))
