from flask import render_template, request
from . import alerts_bp
from services.alert_service import insert_alert, get_alerts, clear_alert as svc_clear_alert

@alerts_bp.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        data = request.get_json(force=True)
        insert_alert(data)
        return ('', 204)
    filter_val = request.args.get('filter', 'all')
    alerts = get_alerts(filter_val)
    return render_template('alerts.html', alerts=alerts, filter=filter_val)

@alerts_bp.route('/alerts', methods=['POST'])
def post_alert():
    return index()

@alerts_bp.route('/alerts/<int:alert_id>/clear', methods=['POST'])
def clear_alert(alert_id):
    svc_clear_alert(alert_id)
    return ('', 204)
