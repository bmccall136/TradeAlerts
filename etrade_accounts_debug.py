from services.etrade_service import _eget, get_account_summary, get_positions

print("list.json:", _eget("/v1/accounts/list.json").status_code)
print("balance.json ok:", bool(get_account_summary()))
print("portfolio.json ok:", bool(get_positions()))
