from flask import Blueprint

status_bp = Blueprint(
    'status',
    __name__
)

from . import views
