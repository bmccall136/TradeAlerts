from flask import Flask, render_template, request
from api import api_bp
from services.alert_service import init_db, get_alerts, clear_alerts_by_filter

app = Flask(__name__)
# ensure our DB schema is fresh on first run
init_db()

app.register_blueprint(api_bp, url_prefix='/api')

@app.route('/alerts')
def alerts_index():
    current_filter = request.args.get('filter', 'all')
    return render_template('alerts.html', current_filter=current_filter)

@app.route('/alerts/clear', methods=['POST'])
def clear_filtered():
    f = request.form.get('filter', 'all')
    clear_alerts_by_filter(f)
    return '', 204

@app.route('/simulation')
def simulation_dashboard():
    return render_template('simulation.html')

if __name__ == '__main__':
    app.run(debug=True)
