import json
from flask import Blueprint, request, jsonify, abort, Response
from services.alert_service import get_alerts, insert_alert, clear_alerts_by_filter

api_bp = Blueprint('api', __name__)

@api_bp.route('/alerts', methods=['GET', 'POST'])
def alerts_collection():
    if request.method == 'GET':
        f = request.args.get('filter', 'all')
        return jsonify(get_alerts(f))
    else:
        data = request.get_json(force=True)
        insert_alert(**data)
        return '', 201

@api_bp.route('/alerts/clear', methods=['POST'])
def alerts_clear():
    f = request.form.get('filter', 'all')
    clear_alerts_by_filter(f)
    return '', 204

@api_bp.route('/alerts/<int:alert_id>/sparkline.svg')
def sparkline_svg(alert_id):
    all_alerts = get_alerts('all')
    alert = next((a for a in all_alerts if a['id'] == alert_id), None)
    if not alert or not alert['spark']:
        abort(404)
    data = json.loads(alert['spark'])
    width, height = 100, 30
    lo, hi = min(data), max(data)
    xs = [i * (width / (len(data)-1)) for i in range(len(data))]
    ys = (height - (v - lo)/(hi-lo)*height if hi>lo else height/2
          for v in data)
    path = 'M' + ' L'.join(f'{x:.1f},{y:.1f}' for x,y in zip(xs, ys))
    svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}">
    <path d="{path}" fill="none" stroke="#0f0" stroke-width="1"/>
    </svg>'''
    return Response(svg, mimetype='image/svg+xml')
