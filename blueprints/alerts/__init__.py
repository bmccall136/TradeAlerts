from flask import Blueprint

alerts_bp = Blueprint(
    'alerts',
    __name__,
    template_folder='../../templates',
    static_folder='../../static'
)

from . import views
