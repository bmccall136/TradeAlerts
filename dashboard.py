from flask import Flask, render_template, request, redirect, url_for, Response, abort
from services.alert_service import insert_alert, get_alerts, clear_alert as svc_clear_alert
from api import api as api_blueprint

app = Flask(__name__)
app.register_blueprint(api_blueprint)

@app.route('/', methods=['GET'])
def alerts_index():
    # Determine current filter (all, prime, sharpshooter, opportunist, sell)
    current_filter = request.args.get('filter', 'all')
    alerts_list = get_alerts(current_filter)
    return render_template('alerts.html', alerts=alerts_list, current_filter=current_filter)

@app.route('/alerts', methods=['POST'])
def scanner_insert_alert():
    # Insert incoming alert (JSON)
    data = request.get_json(force=True) if request.is_json else request.form.to_dict()
    insert_alert(data)
    return ('', 201)

@app.route('/alerts/<int:alert_id>/<action>', methods=['POST'])
def alert_action(alert_id, action):
    # Clear or record a buy/sell action
    if action.lower() == 'clear':
        svc_clear_alert(str(alert_id))
    else:
        # Placeholder for buy/sell logic
        pass
    return redirect(url_for('alerts_index', filter=request.args.get('filter', 'all')))

@app.route('/alerts/clear', methods=['POST'])
def clear_filtered():
    current_filter = request.form.get('filter', 'all')
    svc_clear_alert(current_filter)
    return redirect(url_for('alerts_index', filter=current_filter))

@app.route('/simulation')
def simulation():
    return render_template('simulation.html')

# --- Sparkline SVG endpoint ---
@app.route('/sparkline/<int:alert_id>.svg')
def sparkline_svg(alert_id):
    # Fetch all alerts and locate by ID
    alerts = get_alerts('all')
    alert = next((a for a in alerts if a['id'] == alert_id), None)
    if not alert or not alert.get('sparkline'):
        return abort(404)
    # Parse data
    try:
        vals = [float(x) for x in alert['sparkline'].split(',') if x]
    except ValueError:
        return abort(500)
    # Build SVG
    w, h = 60, 20
    mn, mx = min(vals), max(vals)
    rng = mx - mn or 1
    points = []
    for i, v in enumerate(vals):
        x = (i * w) / (len(vals) - 1)
        y = h - ((v - mn) / rng) * h
        points.append(f"{x:.1f},{y:.1f}")
    poly = ' '.join(points)
    svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <polyline fill="none" stroke="#4eaaff" stroke-width="1" points="{poly}" />
</svg>'''
    return Response(svg, mimetype='image/svg+xml')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
