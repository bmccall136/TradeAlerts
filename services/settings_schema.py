# services/settings_schema.py

from dataclasses import dataclass
from typing    import Optional

@dataclass
class SimulationSettings:
    # ─── Required toggles (no defaults) ────────────────────────────
    sma_on:         bool
    rsi_on:         bool
    macd_on:        bool
    bb_on:          bool
    vol_on:         bool
    vwap_on:        bool
    news_on:        bool
    rsi_slope_on:   bool
    macd_hist_on:   bool
    bb_breakout_on: bool

    # ─── Required indicator parameters ────────────────────────────
    sma_length:     int
    rsi_len:        int
    rsi_overbought: int
    rsi_oversold:   int
    macd_fast:      int
    macd_slow:      int
    macd_signal:    int
    bb_length:      int
    bb_std:         float
    vol_multiplier: float
    vwap_threshold: float

    # ─── Defaults for optional filters & risk rules ───────────────
    atr_threshold:         float         = 0.0
    trailing_stop_pct:     float         = 0.05
    sell_after_days:       Optional[int] = None
    single_entry_only:     bool          = True
    use_trailing_stop:     bool          = True

    # ─── New run‐control flags ─────────────────────────────────────
    nuke_db:               bool          = False
    pause_when_market_closed: bool       = True
    # maximum dollars to commit per single trade
    max_per_trade:        float  = 1000.0
    # ─── Starting capital ─────────────────────────────────────────
    starting_cash:         float         = 10000.0

def extract_simulation_settings(args) -> SimulationSettings:
    """
    Build a SimulationSettings from form or query args.
    """
    return SimulationSettings(
        # toggles
        sma_on                    = "sma_on" in args,
        rsi_on                    = "rsi_on" in args,
        macd_on                   = "macd_on" in args,
        bb_on                     = "bb_on" in args,
        vol_on                    = "vol_on" in args,
        vwap_on                   = "vwap_on" in args,
        news_on                   = "news_on" in args,
        rsi_slope_on              = "rsi_slope_on" in args,
        macd_hist_on              = "macd_hist_on" in args,
        bb_breakout_on            = "bb_breakout_on" in args,

        # core parameters
        sma_length                = int(args.get("sma_length",       50)),
        rsi_len                   = int(args.get("rsi_len",          14)),
        rsi_overbought            = int(args.get("rsi_overbought",   70)),
        rsi_oversold              = int(args.get("rsi_oversold",     30)),
        macd_fast                 = int(args.get("macd_fast",        12)),
        macd_slow                 = int(args.get("macd_slow",        26)),
        macd_signal               = int(args.get("macd_signal",      9)),
        bb_length                 = int(args.get("bb_length",        20)),
        bb_std                    = float(args.get("bb_std",         2.0)),
        vol_multiplier            = float(args.get("vol_multiplier", 2.0)),
        vwap_threshold            = float(args.get("vwap_threshold", 0.0)),

        # filters & risk rules
        atr_threshold             = float(args.get("atr_threshold",    0.0)),
        trailing_stop_pct         = float(args.get("trailing_stop_pct", 0.05)),
        sell_after_days           = int(args.get("sell_after_days")) if args.get("sell_after_days") else None,
        single_entry_only         = "single_entry_only" in args,
        use_trailing_stop         = "use_trailing_stop" in args,

        # run‐control flags
        pause_when_market_closed  = bool(args.get("pause_when_market_closed", True)),
        nuke_db                   = bool(args.get("nuke_db", False)),

        # sizing
        max_per_trade             = float(args.get("max_per_trade",    1000.0)),

        # starting capital
        starting_cash             = float(args.get("starting_cash",   10000.0)),
    )



from dataclasses import dataclass, field
from typing import Optional
from datetime import date, timedelta

@dataclass
class BacktestSettings:
    # date & capital (defaults: last 30 days)
    start_date: str = field(
        default_factory=lambda: (date.today() - timedelta(days=30)).isoformat()
    )
    end_date: str = field(
        default_factory=lambda: date.today().isoformat()
    )

    # financial settings
    starting_cash:  float = 10000.0
    max_per_trade:  float = 1000.0
    timeframe:      str   = "1d"

    # core entry filters
    sma_on:         bool  = False
    rsi_on:         bool  = False
    macd_on:        bool  = False
    bb_on:          bool  = False
    vol_on:         bool  = False
    vwap_on:        bool  = False
    news_on:        bool  = False

    # optional toggles
    rsi_slope_on:   bool  = False
    macd_hist_on:   bool  = False
    bb_breakout_on: bool  = False

    # indicator parameters
    sma_length:     int   = 50
    rsi_len:        int   = 14
    rsi_overbought: int   = 70
    rsi_oversold:   int   = 30
    macd_fast:      int   = 12
    macd_slow:      int   = 26
    macd_signal:    int   = 9
    bb_length:      int   = 20
    bb_std:         float = 2.0
    vol_multiplier: float = 2.0
    vwap_threshold: float = 0.0

    # risk management (if used)
    trailing_stop_pct: float         = 0.05
    sell_after_days:   Optional[int] = None
    single_entry_only: bool          = True
    use_trailing_stop: bool          = True

def extract_backtest_settings(args) -> BacktestSettings:
    """
    Build a BacktestSettings from form/query args.
    """
    return BacktestSettings(
        start_date       = args.get("start_date"),
        end_date         = args.get("end_date"),
        starting_cash    = float(args.get("starting_cash",    10000)),
        max_per_trade    = float(args.get("max_per_trade",    1000)),
        timeframe        = args.get("timeframe",             "1d"),
        sma_on           = "sma_on"          in args,
        rsi_on           = "rsi_on"          in args,
        macd_on          = "macd_on"         in args,
        bb_on            = "bb_on"           in args,
        vol_on           = "vol_on"          in args,
        vwap_on          = "vwap_on"         in args,
        news_on          = "news_on"         in args,
        rsi_slope_on     = "rsi_slope_on"    in args,
        macd_hist_on     = "macd_hist_on"    in args,
        bb_breakout_on   = "bb_breakout_on"  in args,
        sma_length       = int(args.get("sma_length",       50)),
        rsi_len          = int(args.get("rsi_len",          14)),
        rsi_overbought   = int(args.get("rsi_overbought",   70)),
        rsi_oversold     = int(args.get("rsi_oversold",     30)),
        macd_fast        = int(args.get("macd_fast",        12)),
        macd_slow        = int(args.get("macd_slow",        26)),
        macd_signal      = int(args.get("macd_signal",      9)),
        bb_length        = int(args.get("bb_length",        20)),
        bb_std           = float(args.get("bb_std",         2.0)),
        vol_multiplier   = float(args.get("vol_multiplier", 2.0)),
        vwap_threshold   = float(args.get("vwap_threshold", 0.0)),
        trailing_stop_pct= float(args.get("trailing_stop_pct", 0.05)),
        sell_after_days  = int(args.get("sell_after_days")) if args.get("sell_after_days") else None,
        single_entry_only= "single_entry_only" in args,
        use_trailing_stop= "use_trailing_stop" in args,
    )
# if true, recreate the simulation schema (wipe state/trades) before starting
nuke_db: bool = False

# starting cash
starting_cash: float = 10000.0
