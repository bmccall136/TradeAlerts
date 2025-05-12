from flask import Flask, render_template, request, redirect, url_for, jsonify, Response
from services.alert_service import get_alerts, insert_alert, clear_alert, clear_alerts_by_filter
from services.chart_service import get_sparkline_svg  # make sure this module exists

app = Flask(__name__)

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

@app.route('/api/alerts', methods=['GET'])
def api_get_alerts():
    """Return current alerts as JSON for the UI’s polling script."""
    current_filter = request.args.get('filter', 'all')
    alerts_list = get_alerts(current_filter)
    return jsonify(alerts_list)

@app.route('/api/alerts', methods=['POST'])
def api_alerts():
    data = request.get_json(force=True)
    insert_alert(data)
    return ('', 201)

@app.route('/sparkline/<int:alert_id>.svg')
def sparkline_svg(alert_id):
    """
    Generate and return the sparkline SVG for a given alert.
    Expects services.chart_service.get_sparkline_svg to return
    an SVG string (or None if not found).
    """
    svg = get_sparkline_svg(alert_id)
    if svg:
        return Response(svg, mimetype='image/svg+xml')
    else:
        return ('', 404)

if __name__ == '__main__':
    app.config['TEMPLATES_AUTO_RELOAD'] = True
    app.run(debug=True)
