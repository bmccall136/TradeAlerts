import os

def get_sparkline_svg(alert_id):
    """
    Retrieve the sparkline SVG content for a given alert ID.
    Falls back to an empty SVG if not found.
    """
    # Assume SVGs are stored in 'static/sparkline/{id}.svg' relative to app root
    base_dir = os.path.dirname(os.path.dirname(__file__))
    svg_path = os.path.join(base_dir, 'static', 'sparkline', f'{alert_id}.svg')
    try:
        with open(svg_path, 'r', encoding='utf-8') as svg_file:
            return svg_file.read()
    except FileNotFoundError:
        # Return an empty 1x20 placeholder SVG
        return '<svg width="100" height="20" xmlns="http://www.w3.org/2000/svg"></svg>'
