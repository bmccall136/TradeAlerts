from flask import Response, abort
from services.alert_service import get_alerts

def register_sparkline_endpoint(app):
    """
    Register a route on the Flask `app` to serve sparkline SVGs for alerts.
    """
    @app.route('/sparkline/<int:alert_id>.svg')
    def sparkline_svg(alert_id):
        # Fetch all alerts and find the one matching alert_id
        alerts = get_alerts('all')
        alert = next((a for a in alerts if a['id'] == alert_id), None)
        if not alert or not alert.get('sparkline'):
            return abort(404)

        # Parse sparkline CSV into float list
        try:
            vals = [float(x) for x in alert['sparkline'].split(',')]
        except ValueError:
            return abort(500)

        # Build SVG polyline
        w, h = 60, 20
        mn, mx = min(vals), max(vals)
        rng = mx - mn or 1
        pts = []
        for i, v in enumerate(vals):
            x = (i * w) / (len(vals) - 1)
            y = h - ((v - mn) / rng) * h
            pts.append(f"{x:.1f},{y:.1f}")
        points_attr = " ".join(pts)

        svg = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <polyline fill="none" stroke="#4eaaff" stroke-width="1" points="{points_attr}" />
</svg>'''

        return Response(svg, mimetype='image/svg+xml')
