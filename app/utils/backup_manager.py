"""Database backup manager with FTP upload support."""
import os
import subprocess
import tempfile
import gzip
import tarfile
import shutil
from datetime import datetime, timedelta
from ftplib import FTP, FTP_TLS
from urllib.parse import urlparse
import logging

logger = logging.getLogger(__name__)

# Backup format: .tar.gz containing database.sql.gz and uploads/
BACKUP_PREFIX = 'backup_'
BACKUP_SUFFIX = '.tar.gz'


class BackupManager:
    """Handles database backups and FTP uploads."""

    def __init__(self, settings=None):
        """
        Initialize backup manager.

        Args:
            settings: SiteSettings instance or None to fetch from DB
        """
        self.settings = settings

    def _get_settings(self):
        """Get settings from DB if not provided."""
        if self.settings:
            return self.settings
        from app.models.settings import SiteSettings
        return SiteSettings.get_settings()

    def _parse_database_url(self):
        """Parse DATABASE_URL into components."""
        db_url = os.environ.get('DATABASE_URL', '')
        if not db_url:
            raise ValueError("DATABASE_URL not configured")

        # Parse: mysql+pymysql://user:pass@host:port/dbname
        if db_url.startswith('mysql+pymysql://'):
            db_url = db_url.replace('mysql+pymysql://', 'mysql://')

        parsed = urlparse(db_url)

        return {
            'host': parsed.hostname or 'localhost',
            'port': parsed.port or 3306,
            'user': parsed.username or 'root',
            'password': parsed.password or '',
            'database': parsed.path.lstrip('/') if parsed.path else 'quizdb'
        }

    def _get_uploads_path(self):
        """Get the uploads directory path."""
        from flask import current_app
        return current_app.config.get('UPLOAD_FOLDER', 'uploads')

    def create_backup(self):
        """
        Create a full backup (database + uploads).

        Returns:
            tuple: (success: bool, filepath: str or None, message: str, size: int)
        """
        try:
            db_config = self._parse_database_url()

            # Create timestamped filename
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filename = f"{BACKUP_PREFIX}{db_config['database']}_{timestamp}{BACKUP_SUFFIX}"

            # Create temp directory for backup
            backup_dir = tempfile.mkdtemp(prefix='backup_')
            backup_path = os.path.join(backup_dir, filename)
            sql_path = os.path.join(backup_dir, 'database.sql.gz')

            # Step 1: Create database dump
            cmd = [
                'mysqldump',
                f"--host={db_config['host']}",
                f"--port={db_config['port']}",
                f"--user={db_config['user']}",
                '--single-transaction',
                '--routines',
                '--triggers',
                '--quick',
                db_config['database']
            ]

            env = os.environ.copy()
            if db_config['password']:
                env['MYSQL_PWD'] = db_config['password']

            logger.info(f"Starting backup of database {db_config['database']}")

            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env
            )

            with gzip.open(sql_path, 'wb') as f:
                while True:
                    chunk = process.stdout.read(8192)
                    if not chunk:
                        break
                    f.write(chunk)

            process.wait()

            if process.returncode != 0:
                stderr = process.stderr.read().decode()
                logger.error(f"mysqldump failed: {stderr}")
                return False, None, f"mysqldump error: {stderr[:200]}", 0

            # Step 2: Create tar.gz archive with database + uploads
            logger.info("Creating archive with database and uploads...")

            with tarfile.open(backup_path, 'w:gz') as tar:
                # Add database dump
                tar.add(sql_path, arcname='database.sql.gz')

                # Add uploads folder if exists
                uploads_path = self._get_uploads_path()
                if os.path.isdir(uploads_path):
                    # Count files for logging
                    file_count = sum(len(files) for _, _, files in os.walk(uploads_path))
                    logger.info(f"Adding {file_count} files from uploads folder")
                    tar.add(uploads_path, arcname='uploads')
                else:
                    logger.info("No uploads folder found, skipping")

            # Cleanup temp SQL file
            os.remove(sql_path)

            # Get file size
            file_size = os.path.getsize(backup_path)
            logger.info(f"Backup created: {backup_path} ({file_size} bytes)")

            return True, backup_path, "Backup created successfully (DB + uploads)", file_size

        except FileNotFoundError:
            msg = "mysqldump not found. Is MySQL client installed?"
            logger.error(msg)
            return False, None, msg, 0
        except Exception as e:
            msg = f"Backup error: {str(e)}"
            logger.error(msg)
            return False, None, msg, 0

    def upload_to_ftp(self, local_path):
        """
        Upload backup file to FTP server.

        Args:
            local_path: Path to the backup file

        Returns:
            tuple: (success: bool, message: str)
        """
        settings = self._get_settings()

        if not settings.ftp_enabled:
            return False, "FTP backup not enabled"

        if not settings.ftp_host or not settings.ftp_username:
            return False, "FTP configuration incomplete"

        ftp = None
        try:
            # Connect to FTP
            if settings.ftp_use_tls:
                ftp = FTP_TLS()
            else:
                ftp = FTP()

            logger.info(f"Connecting to FTP: {settings.ftp_host}:{settings.ftp_port}")
            ftp.connect(settings.ftp_host, settings.ftp_port, timeout=30)

            password = settings.get_ftp_password() or ''
            ftp.login(settings.ftp_username, password)

            if settings.ftp_use_tls:
                ftp.prot_p()  # Enable data channel encryption

            # Navigate to backup directory (create if needed)
            remote_path = settings.ftp_path or '/backups'
            self._ensure_ftp_directory(ftp, remote_path)

            # Upload file
            filename = os.path.basename(local_path)
            with open(local_path, 'rb') as f:
                ftp.storbinary(f'STOR {filename}', f)

            logger.info(f"Backup uploaded to FTP: {remote_path}/{filename}")

            # Cleanup old backups
            self._cleanup_old_backups(ftp, remote_path, settings.backup_retention_days)

            ftp.quit()
            return True, f"Uploaded to {remote_path}/{filename}"

        except Exception as e:
            msg = f"FTP error: {str(e)}"
            logger.error(msg)
            if ftp:
                try:
                    ftp.quit()
                except Exception:
                    pass
            return False, msg

    def _ensure_ftp_directory(self, ftp, path):
        """Create FTP directory if it doesn't exist."""
        dirs = path.strip('/').split('/')
        current = ''
        for d in dirs:
            if not d:
                continue
            current += f'/{d}'
            try:
                ftp.cwd(current)
            except Exception:
                try:
                    ftp.mkd(current)
                    ftp.cwd(current)
                except Exception:
                    pass

    def _cleanup_old_backups(self, ftp, path, retention_days):
        """Remove backups older than retention_days."""
        if retention_days <= 0:
            return

        try:
            ftp.cwd(path)
            files = ftp.nlst()

            cutoff_date = datetime.utcnow() - timedelta(days=retention_days)

            for filename in files:
                # Support both old (.sql.gz) and new (.tar.gz) formats
                if not filename.startswith(BACKUP_PREFIX):
                    continue
                if not (filename.endswith(BACKUP_SUFFIX) or filename.endswith('.sql.gz')):
                    continue

                # Extract date from filename: backup_dbname_YYYYMMDD_HHMMSS.tar.gz
                try:
                    base = filename.replace(BACKUP_SUFFIX, '').replace('.sql.gz', '')
                    parts = base.split('_')
                    if len(parts) >= 3:
                        date_str = parts[-2]  # YYYYMMDD
                        file_date = datetime.strptime(date_str, '%Y%m%d')
                        if file_date < cutoff_date:
                            ftp.delete(filename)
                            logger.info(f"Deleted old backup: {filename}")
                except Exception:
                    continue

        except Exception as e:
            logger.warning(f"Cleanup error: {str(e)}")

    def run_backup(self):
        """
        Run full backup process: create backup and upload to FTP.

        Returns:
            dict: Result with status, message, and details
        """
        from app import db
        settings = self._get_settings()

        result = {
            'success': False,
            'message': '',
            'backup_size': 0,
            'timestamp': datetime.utcnow()
        }

        # Step 1: Create backup
        success, backup_path, message, size = self.create_backup()
        if not success:
            result['message'] = message
            self._update_backup_status(settings, 'failed', message, 0)
            return result

        result['backup_size'] = size

        # Step 2: Upload to FTP (if enabled)
        if settings.ftp_enabled:
            upload_success, upload_message = self.upload_to_ftp(backup_path)
            if not upload_success:
                result['message'] = f"Backup created but upload failed: {upload_message}"
                self._update_backup_status(settings, 'failed', result['message'], size)
                # Cleanup local file
                self._cleanup_local(backup_path)
                return result
            result['message'] = f"Backup completed and uploaded ({size} bytes)"
        else:
            result['message'] = f"Backup created locally ({size} bytes). FTP upload disabled."

        # Cleanup local backup
        self._cleanup_local(backup_path)

        result['success'] = True
        self._update_backup_status(settings, 'success', result['message'], size)

        return result

    def _cleanup_local(self, backup_path):
        """Remove local backup file and temp directory."""
        try:
            if backup_path and os.path.exists(backup_path):
                os.remove(backup_path)
                # Remove temp directory
                parent = os.path.dirname(backup_path)
                if parent and os.path.isdir(parent):
                    os.rmdir(parent)
        except Exception as e:
            logger.warning(f"Local cleanup error: {str(e)}")

    def _update_backup_status(self, settings, status, message, size):
        """Update backup status in settings."""
        from app import db
        settings.last_backup_at = datetime.utcnow()
        settings.last_backup_status = status
        settings.last_backup_message = message[:500] if message else None
        settings.last_backup_size = size
        try:
            db.session.commit()
        except Exception as e:
            logger.error(f"Failed to update backup status: {str(e)}")
            db.session.rollback()

    def test_ftp_connection(self):
        """
        Test FTP connection with current settings.

        Returns:
            tuple: (success: bool, message: str)
        """
        settings = self._get_settings()

        if not settings.ftp_host or not settings.ftp_username:
            return False, "FTP host and username required"

        ftp = None
        try:
            if settings.ftp_use_tls:
                ftp = FTP_TLS()
            else:
                ftp = FTP()

            ftp.connect(settings.ftp_host, settings.ftp_port, timeout=10)

            password = settings.get_ftp_password() or ''
            ftp.login(settings.ftp_username, password)

            if settings.ftp_use_tls:
                ftp.prot_p()

            # Test directory access
            self._ensure_ftp_directory(ftp, settings.ftp_path or '/backups')

            # List files to verify read access
            files = ftp.nlst()

            ftp.quit()
            return True, f"Connection successful. {len(files)} files in backup directory."

        except Exception as e:
            if ftp:
                try:
                    ftp.quit()
                except Exception:
                    pass
            return False, f"Connection failed: {str(e)}"

    def list_ftp_backups(self):
        """
        List available backups on FTP server.

        Returns:
            tuple: (success: bool, files: list, message: str)
        """
        settings = self._get_settings()

        if not settings.ftp_enabled or not settings.ftp_host:
            return False, [], "FTP not configured"

        ftp = None
        try:
            if settings.ftp_use_tls:
                ftp = FTP_TLS()
            else:
                ftp = FTP()

            ftp.connect(settings.ftp_host, settings.ftp_port, timeout=10)
            password = settings.get_ftp_password() or ''
            ftp.login(settings.ftp_username, password)

            if settings.ftp_use_tls:
                ftp.prot_p()

            # Navigate to backup directory
            try:
                ftp.cwd(settings.ftp_path or '/backups')
            except Exception:
                return True, [], "Backup directory empty or not found"

            # Get file list with details
            files = []
            def parse_line(line):
                parts = line.split()
                if len(parts) >= 9:
                    filename = ' '.join(parts[8:])
                    # Support both old (.sql.gz) and new (.tar.gz) formats
                    if filename.startswith(BACKUP_PREFIX) and \
                       (filename.endswith(BACKUP_SUFFIX) or filename.endswith('.sql.gz')):
                        size = int(parts[4]) if parts[4].isdigit() else 0
                        # Determine backup type
                        backup_type = 'full' if filename.endswith(BACKUP_SUFFIX) else 'database_only'
                        files.append({
                            'name': filename,
                            'size': size,
                            'date': ' '.join(parts[5:8]),
                            'type': backup_type
                        })

            ftp.retrlines('LIST', parse_line)
            ftp.quit()

            # Sort by name (date is in filename) - newest first
            files.sort(key=lambda x: x['name'], reverse=True)

            return True, files, f"{len(files)} backups found"

        except Exception as e:
            if ftp:
                try:
                    ftp.quit()
                except Exception:
                    pass
            return False, [], f"FTP error: {str(e)}"

    def download_from_ftp(self, filename):
        """
        Download a backup file from FTP server.

        Args:
            filename: Name of the backup file to download

        Returns:
            tuple: (success: bool, local_path: str or None, message: str)
        """
        settings = self._get_settings()

        if not settings.ftp_enabled or not settings.ftp_host:
            return False, None, "FTP not configured"

        # Validate filename (security) - support both formats
        if not filename.startswith(BACKUP_PREFIX):
            return False, None, "Invalid backup filename"
        if not (filename.endswith(BACKUP_SUFFIX) or filename.endswith('.sql.gz')):
            return False, None, "Invalid backup filename"
        if '/' in filename or '\\' in filename:
            return False, None, "Invalid filename"

        ftp = None
        try:
            if settings.ftp_use_tls:
                ftp = FTP_TLS()
            else:
                ftp = FTP()

            ftp.connect(settings.ftp_host, settings.ftp_port, timeout=30)
            password = settings.get_ftp_password() or ''
            ftp.login(settings.ftp_username, password)

            if settings.ftp_use_tls:
                ftp.prot_p()

            ftp.cwd(settings.ftp_path or '/backups')

            # Create temp file for download
            backup_dir = tempfile.mkdtemp(prefix='restore_')
            local_path = os.path.join(backup_dir, filename)

            logger.info(f"Downloading backup: {filename}")

            with open(local_path, 'wb') as f:
                ftp.retrbinary(f'RETR {filename}', f.write)

            ftp.quit()

            file_size = os.path.getsize(local_path)
            logger.info(f"Downloaded: {local_path} ({file_size} bytes)")

            return True, local_path, f"Downloaded {filename}"

        except Exception as e:
            if ftp:
                try:
                    ftp.quit()
                except Exception:
                    pass
            return False, None, f"Download error: {str(e)}"

    def restore_backup(self, backup_path):
        """
        Restore from a backup file.

        Args:
            backup_path: Path to the backup file (.sql.gz or .tar.gz)

        Returns:
            tuple: (success: bool, message: str)
        """
        try:
            if not os.path.exists(backup_path):
                return False, "Backup file not found"

            # Determine format and extract if needed
            if backup_path.endswith(BACKUP_SUFFIX):
                # New format: .tar.gz with database + uploads
                return self._restore_full_backup(backup_path)
            else:
                # Old format: .sql.gz database only
                return self._restore_database_only(backup_path)

        except FileNotFoundError:
            msg = "mysql client not found. Is MySQL client installed?"
            logger.error(msg)
            return False, msg
        except Exception as e:
            msg = f"Restore error: {str(e)}"
            logger.error(msg)
            return False, msg

    def _safe_extract_tar(self, tar, extract_dir):
        """
        Safely extract tar archive with path traversal protection.

        Args:
            tar: TarFile object
            extract_dir: Destination directory

        Raises:
            ValueError: If malicious path detected
        """
        extract_dir = os.path.realpath(extract_dir)

        for member in tar.getmembers():
            # Get the full resolved path where this member would be extracted
            member_path = os.path.realpath(os.path.join(extract_dir, member.name))

            # Verify it's within the extraction directory
            if not member_path.startswith(extract_dir + os.sep) and member_path != extract_dir:
                raise ValueError(f"Path traversal attempt detected: {member.name}")

            # Block absolute paths and symlinks outside extract_dir
            if member.issym() or member.islnk():
                link_target = os.path.realpath(os.path.join(extract_dir, member.linkname))
                if not link_target.startswith(extract_dir + os.sep):
                    raise ValueError(f"Symlink traversal attempt detected: {member.name}")

        # Safe to extract
        tar.extractall(extract_dir)

    def _restore_full_backup(self, backup_path):
        """
        Restore from a full backup (.tar.gz with database + uploads).

        Args:
            backup_path: Path to the .tar.gz backup file

        Returns:
            tuple: (success: bool, message: str)
        """
        extract_dir = tempfile.mkdtemp(prefix='restore_extract_')
        try:
            logger.info(f"Extracting full backup: {backup_path}")

            # Extract tar.gz with path traversal protection
            with tarfile.open(backup_path, 'r:gz') as tar:
                self._safe_extract_tar(tar, extract_dir)

            # Restore database
            sql_path = os.path.join(extract_dir, 'database.sql.gz')
            if os.path.exists(sql_path):
                success, message = self._restore_database_only(sql_path)
                if not success:
                    return False, message
            else:
                return False, "Backup archive missing database.sql.gz"

            # Restore uploads folder
            uploads_in_archive = os.path.join(extract_dir, 'uploads')
            if os.path.isdir(uploads_in_archive):
                uploads_dest = self._get_uploads_path()

                # Backup existing uploads (just in case)
                if os.path.isdir(uploads_dest):
                    backup_existing = uploads_dest + '_backup_' + datetime.utcnow().strftime('%Y%m%d_%H%M%S')
                    logger.info(f"Moving existing uploads to {backup_existing}")
                    shutil.move(uploads_dest, backup_existing)

                # Copy restored uploads
                logger.info(f"Restoring uploads to {uploads_dest}")
                shutil.copytree(uploads_in_archive, uploads_dest)

                file_count = sum(len(files) for _, _, files in os.walk(uploads_dest))
                logger.info(f"Restored {file_count} files to uploads folder")

            logger.info("Full backup restore completed successfully")
            return True, "Database and uploads restored successfully"

        finally:
            # Cleanup extracted files
            if os.path.isdir(extract_dir):
                shutil.rmtree(extract_dir, ignore_errors=True)

    def _restore_database_only(self, sql_path):
        """
        Restore database from a .sql.gz file.

        Args:
            sql_path: Path to the .sql.gz file

        Returns:
            tuple: (success: bool, message: str)
        """
        db_config = self._parse_database_url()

        # Build mysql command
        cmd = [
            'mysql',
            f"--host={db_config['host']}",
            f"--port={db_config['port']}",
            f"--user={db_config['user']}",
            db_config['database']
        ]

        # Set password via environment
        env = os.environ.copy()
        if db_config['password']:
            env['MYSQL_PWD'] = db_config['password']

        logger.info(f"Starting restore to database {db_config['database']}")

        # Decompress and pipe to mysql
        with gzip.open(sql_path, 'rb') as f:
            process = subprocess.Popen(
                cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env
            )

            # Stream decompressed data to mysql
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                process.stdin.write(chunk)

            process.stdin.close()
            process.wait()

        if process.returncode != 0:
            stderr = process.stderr.read().decode()
            logger.error(f"mysql restore failed: {stderr}")
            return False, f"Restore error: {stderr[:200]}"

        logger.info("Database restore completed successfully")
        return True, "Database restored successfully"

    def restore_from_ftp(self, filename):
        """
        Download and restore a backup from FTP.

        Args:
            filename: Name of the backup file on FTP

        Returns:
            dict: Result with status and message
        """
        result = {
            'success': False,
            'message': ''
        }

        # Step 1: Download
        success, local_path, message = self.download_from_ftp(filename)
        if not success:
            result['message'] = f"Download failed: {message}"
            return result

        try:
            # Step 2: Restore
            success, message = self.restore_backup(local_path)
            if not success:
                result['message'] = f"Restore failed: {message}"
                return result

            result['success'] = True
            result['message'] = f"Successfully restored from {filename}"

        finally:
            # Cleanup downloaded file
            self._cleanup_local(local_path)

        return result
