from flask import Flask, render_template, request, url_for, redirect
from api import api as api_bp, init_db
from services.alert_service import get_alerts, clear_alerts_by_filter

app = Flask(__name__)
app.register_blueprint(api_bp)

# ensure alerts table exists immediately
init_db()

@app.route('/')
def root():
    return redirect(url_for('alerts_index'))

@app.route('/alerts')
def alerts_index():
    current_filter = request.args.get('filter', 'all')
    alerts_list = get_alerts(current_filter)
    return render_template('alerts.html', alerts=alerts_list, current_filter=current_filter)

@app.route('/alerts/clear', methods=['POST'])
def clear_filtered():
    f = request.form.get('filter', 'all')
    clear_alerts_by_filter(f)
    return redirect(url_for('alerts_index', filter=f))

@app.route('/sparkline/<int:alert_id>.svg')
def sparkline_svg(alert_id):
    from services.chart_service import get_sparkline_svg
    svg = get_sparkline_svg(alert_id)
    return svg, 200, {'Content-Type': 'image/svg+xml'}

if __name__ == '__main__':
    app.run(debug=True)
