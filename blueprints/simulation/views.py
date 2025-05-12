from . import simulation_bp
from flask import render_template, request, jsonify
from services.simulation_service import init_db, reset_state, get_simulation_state, process_trade, delete_trade
from services.market_service import fetch_yahoo_intraday
from config import Config

@simulation_bp.route('/', methods=['GET'])
def sim_dashboard():
    init_db()
    state = get_simulation_state()
    cash = state['cash']
    holdings_raw = state['holdings']       # list of (symbol, qty, avg_price)

    # Calculate open value and realized P&L
    open_value = sum(q * avg for (_s, q, avg) in holdings_raw)
    realized = cash - Config.STARTING_CASH

    # Build holdings summary
    holdings = []
    for symbol, quantity, avg_price in holdings_raw:
        try:
            data = fetch_yahoo_intraday(symbol)
            current_price = data['chart']['result'][0]['meta']['regularMarketPrice']
        except:
            current_price = avg_price
        total_cost     = quantity * avg_price
        current_value  = quantity * current_price
        profit_loss    = current_value - total_cost
        profit_pct     = (profit_loss / total_cost * 100) if total_cost else 0
        holdings.append({
            'symbol':        symbol,
            'avg_price':     avg_price,
            'current_price': current_price,
            'quantity':      quantity,
            'current_value': current_value,
            'profit_loss':   profit_loss,
            'profit_pct':    profit_pct
        })

    # Use trades directly from service (list of dicts with id, timestamp, symbol, action, quantity, price)
    trades = state['trades']

    simulation = {
        'cash':     cash,
        'open':     open_value,
        'realized': realized,
        'holdings': holdings,
        'trades':   trades
    }

    return render_template('simulation.html', simulation=simulation)

@simulation_bp.route('/reset', methods=['POST'])
def sim_reset():
    init_db()
    reset_state()
    return ('', 204)

@simulation_bp.route('/simulate', methods=['POST'])
def simulate_trade():
    data = request.get_json(force=True)
    process_trade(
        data.get('timestamp'),
        data.get('symbol'),
        data.get('action'),
        data.get('quantity'),
        data.get('price')
    )
    return ('', 204)

@simulation_bp.route('/trades/<int:trade_id>/clear', methods=['POST'])
def clear_trade(trade_id):
    delete_trade(trade_id)
    return ('', 204)

@simulation_bp.route('/holdings/<symbol>/clear', methods=['POST'])
def clear_holding(symbol):
    delete_trade(symbol)  # Note: Uses delete_trade to remove by symbol if appropriate
    return ('', 204)

@simulation_bp.route('/api/simulation_state', methods=['GET'])
def api_simulation_state():
    init_db()
    state = get_simulation_state()
    return jsonify(state)

@simulation_bp.route('/api/simulation_trades', methods=['GET'])
def api_simulation_trades():
    init_db()
    state = get_simulation_state()
    return jsonify(state['trades'])
