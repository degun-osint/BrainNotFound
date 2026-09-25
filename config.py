import os
import sys
from dotenv import load_dotenv

load_dotenv()

class Config:
    # SECRET_KEY security check
    _secret_key = os.environ.get('SECRET_KEY')
    _is_production = os.environ.get('FLASK_ENV') == 'production' or not os.environ.get('FLASK_DEBUG', 'false').lower() == 'true'

    if not _secret_key:
        if _is_production:
            print("ERREUR CRITIQUE: SECRET_KEY non definie en production!", file=sys.stderr)
            print("Definissez SECRET_KEY dans votre .env avec une cle aleatoire de 32+ caracteres.", file=sys.stderr)
            # Generate a secure random key for this session (will invalidate on restart)
            import secrets
            _secret_key = secrets.token_hex(32)
            print("AVERTISSEMENT: Cle temporaire generee. Les sessions seront invalidees au redemarrage.", file=sys.stderr)
        else:
            _secret_key = 'dev-secret-key-DO-NOT-USE-IN-PRODUCTION'

    SECRET_KEY = _secret_key

    # Database URL with UTF-8 charset
    _db_url = os.environ.get('DATABASE_URL') or 'mysql+pymysql://quizuser:quizpassword@localhost:3306/quizdb'
    if '?' not in _db_url:
        _db_url += '?charset=utf8mb4'
    elif 'charset=' not in _db_url:
        _db_url += '&charset=utf8mb4'
    SQLALCHEMY_DATABASE_URI = _db_url

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # MariaDB drops idle connections after wait_timeout (8 h): test each pooled
    # connection before use and renew it every 30 min, instead of failing the
    # first request after a quiet night with "MySQL server has gone away"
    SQLALCHEMY_ENGINE_OPTIONS = {'pool_pre_ping': True, 'pool_recycle': 1800}
    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')
    CLAUDE_MODEL = os.environ.get('CLAUDE_MODEL') or 'claude-opus-5-5'
    # Non-Anthropic LLM provider fallback (see app/utils/ai_client.py)
    AI_PROVIDER = os.environ.get('AI_PROVIDER')
    AI_BASE_URL = os.environ.get('AI_BASE_URL')
    AI_API_KEY = os.environ.get('AI_API_KEY')
    AI_MODEL = os.environ.get('AI_MODEL')
    UPLOAD_FOLDER = 'uploads'
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size

    # Backups kept on the server (manual backups without FTP, pre-restore snapshots)
    BACKUP_LOCAL_DIR = os.environ.get('BACKUP_LOCAL_DIR', 'backups')
    BACKUP_MAX_UPLOAD_MB = int(os.environ.get('BACKUP_MAX_UPLOAD_MB', 2048))

    # Security: Allowed hosts (comma-separated, empty = allow all)
    _allowed_hosts_raw = os.environ.get('ALLOWED_HOSTS', '').strip()
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_raw.split(',') if h.strip()] if _allowed_hosts_raw else []

    # Session security
    # SESSION_COOKIE_SECURE requires HTTPS - only enable if you have SSL configured
    SESSION_COOKIE_SECURE = os.environ.get('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
    SESSION_COOKIE_HTTPONLY = True  # No JS access to session cookie
    SESSION_COOKIE_SAMESITE = 'Lax'  # CSRF protection for cookies
    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour session timeout

    # Email SMTP configuration
    MAIL_SERVER = os.environ.get('MAIL_SERVER', 'localhost')
    MAIL_PORT = int(os.environ.get('MAIL_PORT', 587))
    MAIL_USE_TLS = os.environ.get('MAIL_USE_TLS', 'true').lower() == 'true'
    MAIL_USE_SSL = os.environ.get('MAIL_USE_SSL', 'false').lower() == 'true'
    MAIL_USERNAME = os.environ.get('MAIL_USERNAME')
    MAIL_PASSWORD = os.environ.get('MAIL_PASSWORD')
    MAIL_DEFAULT_SENDER = os.environ.get('MAIL_DEFAULT_SENDER', 'noreply@localhost')

    # Public address of the site, for links in emails sent outside a request (grader digest)
    PUBLIC_URL = os.environ.get('PUBLIC_URL', '').strip().rstrip('/')
    # Grader digest: at most one email per quiz every N minutes
    GRADER_DIGEST_MINUTES = max(5, int(os.environ.get('GRADER_DIGEST_MINUTES', 30)))

    # Internationalization
    LANGUAGES = ['fr', 'en']
    BABEL_DEFAULT_LOCALE = 'fr'
    BABEL_DEFAULT_TIMEZONE = 'Europe/Paris'
    BABEL_TRANSLATION_DIRECTORIES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'translations')
