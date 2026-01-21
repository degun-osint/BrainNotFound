import os
from app import create_app, socketio
from werkzeug.middleware.proxy_fix import ProxyFix

app = create_app()

# Trust reverse proxy headers (X-Forwarded-Proto, X-Forwarded-Host, etc.)
# This is required when running behind Nginx/CloudPanel
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

if __name__ == "__main__":
    debug_mode = os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'
    socketio.run(app, debug=debug_mode)
