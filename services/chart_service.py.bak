import sqlite3

DB_PATH = 'alerts.db'

def compute_vwap_for_symbol(symbol, limit=20):
    """
    Compute simple VWAP (average) over last `limit` alerts for the symbol.
    Returns None if insufficient data.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT price FROM alerts WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?",
        (symbol, limit)
    )
    rows = cur.fetchall()
    conn.close()
    prices = [r['price'] for r in rows]
    if not prices:
        return None
    return sum(prices) / len(prices)

def get_sparkline_svg(alert_id, limit=20, width=100, height=30):
    """
    Generate sparkline SVG for last `limit` prices of the alert's symbol.
    Returns empty string if not enough data.
    """
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("SELECT symbol FROM alerts WHERE id = ?", (alert_id,))
    row = cur.fetchone()
    conn.close()
    if not row:
        return ''
    symbol = row['symbol']

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT price FROM alerts WHERE symbol = ? ORDER BY timestamp DESC LIMIT ?",
        (symbol, limit)
    )
    price_rows = cur.fetchall()
    conn.close()

    prices = [r['price'] for r in price_rows]
    if len(prices) < 2:
        return ''
    # reverse to chronological
    prices = prices[::-1]
    min_p, max_p = min(prices), max(prices)
    span = max_p - min_p if max_p != min_p else 1.0
    step = width / (len(prices) - 1)
    pts = []
    for i, p in enumerate(prices):
        x = i * step
        y = height - ((p - min_p) / span) * height
        pts.append(f"{x:.1f},{y:.1f}")
    polyline = ' '.join(pts)

    svg = (
        f'<svg width="{width}" height="{height}" xmlns="http://www.w3.org/2000/svg" preserveAspectRatio="none">'
        f'<polyline fill="none" stroke="#0f0" stroke-width="1" points="{polyline}"/>'
        '</svg>'
    )
    return svg
