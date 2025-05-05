from flask import Blueprint, send_from_directory, abort

static_bp = Blueprint(
    'static_assets',
    __name__,
    static_folder='static',
    url_prefix='/assets'
)

@static_bp.route('/<path:filename>')
def serve_asset(filename):
    try:
        return send_from_directory(static_bp.static_folder, filename)
    except FileNotFoundError:
        abort(404)

@static_bp.route('/view/<path:filename>')
def view_asset(filename):
    try:
        with open(f"{static_bp.static_folder}/{filename}", 'r', encoding='utf-8') as f:
            content = f.read()
        return f"<pre>{content.replace('<','&lt;').replace('>','&gt;')}</pre>"
    except FileNotFoundError:
        abort(404)
