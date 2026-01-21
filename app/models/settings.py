"""Site settings model for global configuration."""
from app import db
from datetime import datetime
from cryptography.fernet import Fernet
import os
import base64


class SiteSettings(db.Model):
    """Singleton model for site-wide settings."""
    __tablename__ = 'site_settings'

    id = db.Column(db.Integer, primary_key=True)

    # Site branding
    site_title = db.Column(db.String(100), default='BrainNotFound')
    contact_email = db.Column(db.String(255), default='thebot@brainnotfound.app')

    # FTP Backup settings
    ftp_enabled = db.Column(db.Boolean, default=False)
    ftp_host = db.Column(db.String(255), nullable=True)
    ftp_port = db.Column(db.Integer, default=21)
    ftp_username = db.Column(db.String(255), nullable=True)
    ftp_password_encrypted = db.Column(db.Text, nullable=True)  # Encrypted
    ftp_path = db.Column(db.String(500), default='/backups')
    ftp_use_tls = db.Column(db.Boolean, default=True)

    # Backup schedule (cron-like)
    backup_frequency = db.Column(db.String(20), default='daily')  # hourly, daily, weekly
    backup_hour = db.Column(db.Integer, default=3)  # Hour of day (0-23)
    backup_day = db.Column(db.Integer, default=0)  # Day of week (0=Monday) for weekly
    backup_retention_days = db.Column(db.Integer, default=30)  # Keep backups for X days

    # Last backup info
    last_backup_at = db.Column(db.DateTime, nullable=True)
    last_backup_status = db.Column(db.String(20), nullable=True)  # success, failed
    last_backup_message = db.Column(db.Text, nullable=True)
    last_backup_size = db.Column(db.BigInteger, nullable=True)  # bytes

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @classmethod
    def get_settings(cls):
        """Get the singleton settings instance, creating if needed."""
        settings = cls.query.first()
        if not settings:
            settings = cls()
            db.session.add(settings)
            db.session.commit()
        return settings

    @staticmethod
    def _get_encryption_key():
        """Get or generate encryption key for sensitive data."""
        key = os.environ.get('SETTINGS_ENCRYPTION_KEY')
        if not key:
            # Derive from SECRET_KEY if not set
            from flask import current_app
            secret = current_app.config.get('SECRET_KEY', 'default-key')
            # Create a valid Fernet key from SECRET_KEY
            key_bytes = secret.encode()[:32].ljust(32, b'\0')
            key = base64.urlsafe_b64encode(key_bytes).decode()
        return key

    def set_ftp_password(self, password):
        """Encrypt and store FTP password."""
        if not password:
            self.ftp_password_encrypted = None
            return
        try:
            key = self._get_encryption_key()
            f = Fernet(key)
            self.ftp_password_encrypted = f.encrypt(password.encode()).decode()
        except Exception:
            # Fallback: store base64 encoded (not ideal but functional)
            self.ftp_password_encrypted = base64.b64encode(password.encode()).decode()

    def get_ftp_password(self):
        """Decrypt and return FTP password."""
        if not self.ftp_password_encrypted:
            return None
        try:
            key = self._get_encryption_key()
            f = Fernet(key)
            return f.decrypt(self.ftp_password_encrypted.encode()).decode()
        except Exception:
            # Fallback: try base64 decode
            try:
                return base64.b64decode(self.ftp_password_encrypted.encode()).decode()
            except Exception:
                return None

    def to_dict(self):
        """Return settings as dictionary (without sensitive data)."""
        return {
            'site_title': self.site_title,
            'contact_email': self.contact_email,
            'ftp_enabled': self.ftp_enabled,
            'ftp_host': self.ftp_host,
            'ftp_port': self.ftp_port,
            'ftp_username': self.ftp_username,
            'ftp_path': self.ftp_path,
            'ftp_use_tls': self.ftp_use_tls,
            'backup_frequency': self.backup_frequency,
            'backup_hour': self.backup_hour,
            'backup_day': self.backup_day,
            'backup_retention_days': self.backup_retention_days,
            'last_backup_at': self.last_backup_at.isoformat() if self.last_backup_at else None,
            'last_backup_status': self.last_backup_status,
            'last_backup_message': self.last_backup_message,
            'last_backup_size': self.last_backup_size
        }
