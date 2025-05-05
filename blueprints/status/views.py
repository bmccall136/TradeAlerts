from flask import redirect, url_for
from . import status_bp

@status_bp.route('/reconnect_api')
def reconnect_api():
    # same as your old route in dashboard.py
    return redirect(url_for('alerts.index'))
