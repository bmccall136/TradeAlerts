from flask import Blueprint

simulation_bp = Blueprint(
    'simulation',
    __name__,
    template_folder='../../templates',
    static_folder='../../static'
)

from . import views
