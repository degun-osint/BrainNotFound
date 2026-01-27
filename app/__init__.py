from flask import Flask, url_for, request, abort, session, current_app
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, current_user
from flask_socketio import SocketIO
from flask_wtf.csrf import CSRFProtect
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_babel import Babel, get_locale as babel_get_locale
from jinja2 import ChoiceLoader, FileSystemLoader
from markupsafe import Markup
from config import Config
import os
import re

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
socketio = SocketIO()
csrf = CSRFProtect()
mail = Mail()
limiter = Limiter(
    key_func=get_remote_address,
    storage_uri="memory://",
    default_limits=["200 per day", "50 per hour"]
)
babel = Babel()


def get_locale():
    """Select the best language for the user."""
    # 1. Check user preference (if authenticated)
    if hasattr(current_user, 'is_authenticated') and current_user.is_authenticated:
        if hasattr(current_user, 'language_preference') and current_user.language_preference:
            return current_user.language_preference

    # 2. Check session
    if 'language' in session:
        return session['language']

    # 3. Check Accept-Language header
    return request.accept_languages.best_match(
        current_app.config.get('LANGUAGES', ['fr', 'en'])
    ) or 'fr'

def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    # Configure Jinja2 to look in private/ first, then app/templates/
    # This allows customizing templates without modifying the codebase
    private_templates = os.path.join(app.root_path, '..', 'private')
    app.jinja_loader = ChoiceLoader([
        FileSystemLoader(private_templates),
        app.jinja_loader  # Default app/templates/ loader
    ])

    db.init_app(app)

    # Import all models before initializing migrate (for Alembic discovery)
    from app import models  # noqa: F401

    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    csrf.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)
    babel.init_app(app, locale_selector=get_locale)
    # WebSocket CORS: Use ALLOWED_HOSTS or restrict to same origin
    allowed_origins = app.config.get('ALLOWED_HOSTS', [])
    if allowed_origins:
        cors_origins = [f"http://{h}" for h in allowed_origins] + [f"https://{h}" for h in allowed_origins]
    else:
        # Default: only allow same origin (empty list = same origin only in Flask-SocketIO)
        cors_origins = []
    socketio.init_app(app, cors_allowed_origins=cors_origins if cors_origins else None, async_mode='gevent')

    from app.models.user import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Security: Check allowed hosts
    @app.before_request
    def check_host():
        allowed_hosts = app.config.get('ALLOWED_HOSTS', [])
        if allowed_hosts:
            host = request.host.split(':')[0]  # Remove port
            if host not in allowed_hosts:
                abort(403)

    # Security: Add security headers
    @app.after_request
    def add_security_headers(response):
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        response.headers['X-XSS-Protection'] = '1; mode=block'
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'

        # HSTS - Only enable when HTTPS is configured (SESSION_COOKIE_SECURE=true)
        if app.config.get('SESSION_COOKIE_SECURE'):
            # max-age=1 year, includeSubDomains for full protection
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

        # Content Security Policy - Restrict resource loading
        csp_directives = [
            "default-src 'self'",
            "script-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com",  # cdnjs for socket.io
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net https://fonts.googleapis.com https://cdnjs.cloudflare.com",
            "font-src 'self' https://cdn.jsdelivr.net https://fonts.gstatic.com",
            "img-src 'self' data: blob:",  # data: for inline images, blob: for uploads
            "connect-src 'self' wss: ws: https://cdnjs.cloudflare.com",  # WebSocket + CDN source maps
            "frame-ancestors 'self'",
            "form-action 'self'",
            "base-uri 'self'"
        ]
        response.headers['Content-Security-Policy'] = '; '.join(csp_directives)

        return response

    # Register blueprints
    from app.routes.auth import auth_bp
    from app.routes.admin import admin_bp
    from app.routes.quiz import quiz_bp
    from app.routes.tenant import tenant_bp
    from app.routes.docs import docs_bp
    from app.routes.interview import interview_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(quiz_bp, url_prefix='/quiz')
    app.register_blueprint(tenant_bp, url_prefix='/admin/tenants')
    app.register_blueprint(docs_bp, url_prefix='/docs')
    app.register_blueprint(interview_bp, url_prefix='/interview')

    # Register WebSocket handlers
    from app import sockets  # noqa: F401

    # Register Jinja2 filter for rendering quiz content (images + code)
    def render_quiz_images(text, quiz_id):
        """Convert markdown syntax to HTML (images, inline code, code blocks)."""
        import html
        if not text:
            return text

        def replace_image(match):
            # Escape alt text to prevent XSS
            alt = html.escape(match.group(1), quote=True)
            # Validate and escape filename
            filename = match.group(2)
            # Only allow alphanumeric, dash, underscore, and dot in filename
            if not re.match(r'^[\w\-\.]+$', filename):
                return f'[Invalid image: {html.escape(filename)}]'
            # Build URL for the image
            image_url = url_for('admin.serve_quiz_image', quiz_id=quiz_id, filename=filename)
            return f'<img src="{image_url}" alt="{alt}" class="quiz-image">'

        # Process images first (before escaping, as URLs need special chars)
        pattern = r'!\[([^\]]*)\]\(([^)]+)\)'
        result = re.sub(pattern, replace_image, text)

        # Handle code blocks first: ```code``` -> <pre><code>code</code></pre>
        def replace_code_block(match):
            lang = match.group(1) or ''
            code_content = html.escape(match.group(2))
            lang_class = f' class="language-{lang}"' if lang else ''
            return f'<pre><code{lang_class}>{code_content}</code></pre>'

        result = re.sub(r'```(\w*)\n?([\s\S]*?)```', replace_code_block, result)

        # Then handle inline code: `code` -> <code>code</code>
        def replace_code(match):
            code_content = html.escape(match.group(1))
            return f'<code>{code_content}</code>'

        result = re.sub(r'`([^`]+)`', replace_code, result)

        return Markup(result)

    app.jinja_env.filters['render_quiz_images'] = render_quiz_images

    # Timezone conversion filters for templates
    from app.utils import format_datetime, format_time

    app.jinja_env.filters['localtime'] = format_datetime
    app.jinja_env.filters['localtime_short'] = format_time

    # Context processor for site settings and custom pages (available in all templates)
    @app.context_processor
    def inject_site_settings():
        from app.models.settings import SiteSettings
        try:
            settings = SiteSettings.get_settings()
            site_title = settings.site_title or 'BrainNotFound'
            contact_email = settings.contact_email or 'thebot@brainnotfound.app'
        except Exception:
            site_title = 'BrainNotFound'
            contact_email = 'thebot@brainnotfound.app'

        # Get custom pages for menu and footer
        try:
            from app.models.page import Page
            menu_pages = Page.get_menu_pages()
            footer_pages = Page.get_footer_pages()
        except Exception:
            menu_pages = []
            footer_pages = []

        return {
            'site_title': site_title,
            'contact_email': contact_email,
            'menu_pages': menu_pages,
            'footer_pages': footer_pages,
            'get_locale': get_locale
        }

    # Initialize backup scheduler (only in main process, not in reloader)
    if not app.debug or os.environ.get('WERKZEUG_RUN_MAIN') == 'true':
        try:
            from app.utils.backup_scheduler import init_backup_scheduler
            init_backup_scheduler(app)
        except Exception as e:
            app.logger.warning(f"Failed to initialize backup scheduler: {str(e)}")

    return app
