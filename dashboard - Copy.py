from flask import Flask
from api import api                           # existing /api blueprint
from static_bp import static_bp               # existing static assets blueprint
from blueprints.alerts.views import alerts_bp
from blueprints.simulation.views import simulation_bp
from blueprints.status.views import status_bp

def create_app():
    app = Flask(
        __name__,
        static_folder='static',
        template_folder='.'    # root directory holds templates
    )

    # Register blueprints
    app.register_blueprint(static_bp)         # serves /static assets
    app.register_blueprint(api)               # serves /api endpoints
    app.register_blueprint(alerts_bp)         # mounts at '/'
    app.register_blueprint(simulation_bp, url_prefix='/simulation')
    app.register_blueprint(status_bp)         # for /reconnect_api

    return app

if __name__ == '__main__':
    create_app().run(debug=True)
