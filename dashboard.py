from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from etrade_auth import get_etrade_session
from services.alert_service import get_alerts, insert_alert, clear_alert, clear_alerts_by_filter
from services.chart_service import get_sparkline_svg

from api import api as api_bp

app = Flask(__name__)
# Register API blueprint to handle POST /api/alerts
app.register_blueprint(api_bp)


@app.route('/')
def root():
    return redirect(url_for('alerts_index', filter='all'))

@app.route('/alerts')
def alerts_index():
    current_filter = request.args.get('filter', 'all')
    alerts_list = get_alerts(current_filter)
    return render_template('alerts.html',
                           alerts=alerts_list,
                           current_filter=current_filter)

@app.route('/alerts/clear', methods=['POST'])
def clear_filtered():
    current_filter = request.form.get('filter', 'all')
    clear_alerts_by_filter(current_filter)
    return redirect(url_for('alerts_index', filter=current_filter))

@app.route('/alerts/<alert_id>/clear', methods=['POST'])
def clear_one(alert_id):
    clear_alert(alert_id)
    return redirect(url_for('alerts_index',
                            filter=request.args.get('filter', 'all')))

# Removed dashboard's GET-only /api/alerts in favor of api blueprint

@app.route('/api/status', methods=['GET'])
def api_status():
    """Return connectivity/status info for the UI badges."""
    return jsonify({
        "yahoo": "open",
        "etrade": "ok"
    })

@app.route('/sparkline/<int:alert_id>.svg')
def sparkline_svg(alert_id):
    """Generate and return the sparkline SVG for a given alert."""
    svg = get_sparkline_svg(alert_id)
    return Response(svg, mimetype='image/svg+xml') if svg else ('', 404)

if __name__ == '__main__':
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(debug=True)
