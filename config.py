import os

basedir = os.path.abspath(os.path.dirname(__file__))

class Config:
    # Database paths
    ALERT_DB        = os.environ.get('ALERT_DB', os.path.join(basedir, 'alerts_clean.db'))
    SIM_DB          = os.environ.get('SIM_DB',   os.path.join(basedir, 'simulation_state.db'))

    # API endpoints
    ETRADE_BASE_URL = os.environ.get(
        'ETRADE_BASE_URL',
        'https://api.etrade.com/v1/market/quote'
    )
    YAHOO_BASE_URL  = os.environ.get(
        'YAHOO_BASE_URL',
        'https://query1.finance.yahoo.com/v8/finance/chart'
    )

    # Simulation defaults
    STARTING_CASH   = float(os.environ.get('STARTING_CASH', 10000.0))

    # UI constants
    SPARKLINE_LENGTH = int(os.environ.get('SPARKLINE_LENGTH', 6))
