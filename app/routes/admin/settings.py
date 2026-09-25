"""Site settings (superadmin): identity, AI provider, backups and restore."""
import os
import shutil
import tempfile
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app, send_file, abort
from flask_login import login_required, current_user
from flask_babel import lazy_gettext as _l
from app import db, csrf
from app.routes.admin import admin_bp
from app.routes.admin.common import superadmin_required


# Site Settings routes - Superadmin only
@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@superadmin_required
def site_settings():
    """Manage site settings and backup configuration."""
    from app.models.settings import SiteSettings
    from app.utils.backup_scheduler import get_next_backup_time, update_backup_schedule

    settings = SiteSettings.get_settings()

    if request.method == 'POST':
        action = request.form.get('action', 'save')

        if action == 'save':
            # Site branding
            settings.site_title = request.form.get('site_title', 'BrainNotFound').strip()[:100]
            settings.contact_email = request.form.get('contact_email', '').strip()[:255]

            # FTP settings
            settings.ftp_enabled = request.form.get('ftp_enabled') == 'on'
            settings.ftp_host = request.form.get('ftp_host', '').strip()[:255]
            settings.ftp_port = int(request.form.get('ftp_port', 21) or 21)
            settings.ftp_username = request.form.get('ftp_username', '').strip()[:255]
            settings.ftp_path = request.form.get('ftp_path', '/backups').strip()[:500]
            settings.ftp_use_tls = request.form.get('ftp_use_tls') == 'on'

            # Only update password if provided
            new_password = request.form.get('ftp_password', '')
            if new_password:
                settings.set_ftp_password(new_password)

            error = save_ai_settings(settings, request.form)
            if error:
                flash(error, 'error')

            # Backup schedule
            settings.backup_frequency = request.form.get('backup_frequency', 'daily')
            settings.backup_hour = int(request.form.get('backup_hour', 3) or 3)
            settings.backup_day = int(request.form.get('backup_day', 0) or 0)
            settings.backup_retention_days = int(request.form.get('backup_retention_days', 30) or 30)

            db.session.commit()

            # Update scheduler
            try:
                update_backup_schedule()
            except Exception as e:
                current_app.logger.error(f"Failed to update backup schedule: {str(e)}")

            flash(_l('Parametres sauvegardes avec succes'), 'success')
            return redirect(url_for('admin.site_settings'))

    # Get next backup time
    next_backup = get_next_backup_time()

    return render_template('admin/settings.html',
                          settings=settings,
                          next_backup=next_backup,
                          ai=ai_settings_summary(settings))


def save_ai_settings(settings, form):
    """Apply the LLM section of the settings form. Returns an error message or None."""
    from app.utils import ai_client

    provider = form.get('ai_provider', ai_client.ANTHROPIC)
    if provider not in ai_client.PROVIDERS:
        provider = ai_client.ANTHROPIC
    base_url = None
    if provider == ai_client.OPENAI_COMPATIBLE:
        base_url = form.get('ai_base_url', '').strip()[:255] or None
    model = form.get('ai_model', '').strip()[:100] or None
    new_key = form.get('ai_api_key', '').strip()

    if provider == ai_client.OPENAI_COMPATIBLE and not base_url:
        return _l('URL du fournisseur requise')
    if provider == ai_client.OPENAI_COMPATIBLE and not model:
        return _l('Modele requis pour ce fournisseur')
    if ai_client.is_grok(provider, base_url, model) and form.get('grok_confirmed') != '1':
        return _l('Configuration non enregistree : utilisation de Grok non confirmee')

    endpoint_changed = (provider != (settings.ai_provider or ai_client.ANTHROPIC)
                        or base_url != settings.ai_base_url)
    key = new_key or (None if endpoint_changed or form.get('clear_ai_api_key') == 'on'
                      else settings.get_ai_api_key())

    model_error = check_ai_model(provider, base_url, model, key)
    if model_error:
        return model_error

    settings.ai_provider = provider
    settings.ai_base_url = base_url
    settings.ai_model = model
    # A key belongs to one provider/server: it's dropped when switching, never sent elsewhere
    settings.set_ai_api_key(key)
    return None


def ai_settings_summary(settings):
    """Where the LLM config comes from, for display (never the key itself)."""
    from app.utils import ai_client
    config = ai_client.get_config()
    db_key = settings.get_ai_api_key()
    key = config['api_key']
    return {
        'provider': config['provider'],
        'key_source': 'admin' if db_key else ('env' if key else None),
        'key_hint': f"...{key[-4:]}" if key else None,
        'key_unreadable': bool(settings.ai_api_key_encrypted and not db_key),
        'env_model': current_app.config.get('CLAUDE_MODEL') or ai_client.DEFAULT_MODEL,
    }


def check_ai_model(provider, base_url, model, api_key=None):
    """Return an error message if the provider says this model doesn't exist, None otherwise.

    Network/auth problems don't block saving: the model may be valid and the
    admin can use the test button once the key is fixed.
    """
    from app.utils import ai_client
    if not model:
        return None
    try:
        available = {m_id for m_id, _ in ai_client.list_models(provider, api_key, base_url)}
    except Exception as e:  # no key, auth, network, server without /models...
        current_app.logger.warning(f"Could not verify AI model {model}: {e}")
        return None
    if available and model not in available:
        return _l('Modele inconnu chez ce fournisseur : %(model)s. Configuration non modifiee.', model=model)
    return None


@admin_bp.route('/settings/ai-models', methods=['POST'])
@login_required
@superadmin_required
def ai_models():
    """List the models of a provider (typed values or configured ones) - also tests the key."""
    import anthropic
    import openai
    from app.utils import ai_client

    data = request.get_json(silent=True) or {}
    provider = data.get('provider') if data.get('provider') in ai_client.PROVIDERS else None
    try:
        models = ai_client.list_models(provider, data.get('api_key', '').strip() or None,
                                       data.get('base_url', '').strip() or None)
    except (anthropic.AuthenticationError, openai.AuthenticationError):
        return jsonify({'success': False, 'message': str(_l('Cle API refusee par le fournisseur'))})
    except (anthropic.APIConnectionError, openai.APIConnectionError):
        return jsonify({'success': False, 'message': str(_l('Impossible de joindre le fournisseur'))})
    except (anthropic.APIStatusError, openai.APIStatusError) as e:
        return jsonify({'success': False, 'message': f'API error {e.status_code}'})
    except (anthropic.AnthropicError, openai.OpenAIError, ai_client.AIConfigError):
        return jsonify({'success': False, 'message': str(_l('Configuration incomplete (cle ou URL manquante)'))})
    return jsonify({'success': True, 'models': [{'id': m_id, 'name': name} for m_id, name in models]})


@admin_bp.route('/settings/test-ftp', methods=['POST'])
@login_required
@superadmin_required
def test_ftp_connection():
    """Test FTP connection with current settings."""
    from app.utils.backup_manager import BackupManager

    manager = BackupManager()
    success, message = manager.test_ftp_connection()

    return jsonify({
        'success': success,
        'message': message
    })


@admin_bp.route('/settings/run-backup', methods=['POST'])
@login_required
@superadmin_required
def run_manual_backup():
    """Run a manual backup now."""
    from app.utils.backup_manager import BackupManager

    manager = BackupManager()
    result = manager.run_backup()

    return jsonify(result)


@admin_bp.route('/settings/backup-history')
@login_required
@superadmin_required
def backup_history():
    """Backups available for download/restore: on this server and on FTP."""
    from app.utils.backup_manager import BackupManager

    manager = BackupManager()
    local = [{k: v for k, v in f.items() if k != 'mtime'} for f in manager.list_local_backups()]
    ftp_ok, ftp_files, ftp_message = manager.list_ftp_backups()
    return jsonify({
        'local': local,
        'ftp': ftp_files[:50] if ftp_ok else [],
        'ftp_error': None if ftp_ok or not manager._get_settings().ftp_enabled else ftp_message,
    })


@admin_bp.route('/settings/backups/<name>/download')
@login_required
@superadmin_required
def download_backup(name):
    """Download a backup stored on this server."""
    from app.utils.backup_manager import BackupManager

    path = BackupManager().local_backup_path(name)
    if not path:
        abort(404)
    return send_file(path, as_attachment=True, download_name=name)


@admin_bp.route('/settings/backups/download-now', methods=['POST'])
@login_required
@superadmin_required
def download_backup_now():
    """Create a full backup (DB + uploads) and send it straight to the browser."""
    from app.utils.backup_manager import BackupManager

    manager = BackupManager()
    ok, path, message, _ = manager.create_backup()
    if not ok:
        flash(message, 'error')
        return redirect(url_for('admin.site_settings'))
    response = send_file(path, as_attachment=True, download_name=os.path.basename(path))
    response.call_on_close(lambda: manager._cleanup_local(path))
    return response


def _restore_confirmed(value):
    return (value or '').strip().upper() in ('RESTAURER', 'RESTORE')  # FR / EN interface


def _finish_restore(ok, message):
    """After a restore: migrate the restored schema, then log the admin out.

    The restored users table may not contain the current account (or give its
    id to someone else), so the current session must not survive.
    """
    from flask_login import logout_user
    from app.utils.db_schema import upgrade_schema

    admin = current_user.username if current_user.is_authenticated else '?'
    if ok:
        try:
            message += '. ' + upgrade_schema()
        except Exception as e:
            current_app.logger.error(f"Schema upgrade after restore failed: {e}")
            ok, message = False, f"{message}. Schema upgrade failed, restart the container: {e}"
        db.session.remove()
        logout_user()
    current_app.logger.warning(f"Backup restore by {admin}: {message}")
    return ok, message


@admin_bp.route('/settings/restore-backup', methods=['POST'])
@login_required
@superadmin_required
def restore_backup():
    """Restore a backup stored on this server (source=local) or on FTP (source=ftp)."""
    from app.utils.backup_manager import BackupManager

    data = request.get_json(silent=True) or request.form
    filename = data.get('filename', '')
    source = data.get('source', 'ftp')
    manager = BackupManager()

    if not manager.is_valid_backup_name(filename):
        return jsonify({'success': False, 'message': 'Invalid backup filename'}), 400
    if not _restore_confirmed(data.get('confirm')):
        return jsonify({'success': False, 'message': str(_l('Tapez RESTAURER pour confirmer'))}), 400

    if source == 'local':
        path = manager.local_backup_path(filename)
        if not path:
            return jsonify({'success': False, 'message': 'Backup not found'}), 404
        ok, message = manager.restore_backup(path)
    else:
        result = manager.restore_from_ftp(filename)
        ok, message = result['success'], result['message']

    ok, message = _finish_restore(ok, message)
    return jsonify({'success': ok, 'message': message, 'redirect': url_for('auth.login') if ok else None})


@admin_bp.route('/settings/restore-upload', methods=['POST'])
@csrf.exempt  # checked below, once the upload size limit has been raised
@login_required
@superadmin_required
def restore_upload():
    """Restore a backup file uploaded from the admin's computer."""
    from flask_wtf.csrf import validate_csrf
    from wtforms import ValidationError
    from app.utils.backup_manager import BackupManager, BACKUP_SUFFIX

    # Backups (DB + uploads) are larger than the global 16 MB request limit
    request.max_content_length = current_app.config['BACKUP_MAX_UPLOAD_MB'] * 1024 * 1024
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        abort(400)

    upload = request.files.get('backup_file')
    if not upload or not upload.filename:
        flash(_l('Aucun fichier selectionne'), 'error')
        return redirect(url_for('admin.site_settings'))
    if not _restore_confirmed(request.form.get('confirm')):
        flash(_l('Tapez RESTAURER pour confirmer'), 'error')
        return redirect(url_for('admin.site_settings'))

    suffix = BACKUP_SUFFIX if upload.filename.endswith(BACKUP_SUFFIX) else '.sql.gz'
    if not upload.filename.endswith(suffix):
        flash(_l('Format attendu : .tar.gz ou .sql.gz'), 'error')
        return redirect(url_for('admin.site_settings'))

    manager = BackupManager()
    tmp_dir = tempfile.mkdtemp(prefix='restore_upload_')
    path = os.path.join(tmp_dir, f'upload{suffix}')
    try:
        upload.save(path)
        ok, message = manager.restore_backup(path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    ok, message = _finish_restore(ok, message)
    flash(message, 'success' if ok else 'error')
    return redirect(url_for('auth.login') if ok else url_for('admin.site_settings'))
