"""Shared helpers of the admin blueprint: decorators, redirects, organization context."""
import unicodedata
import re
from flask import redirect, url_for, flash, request
from flask_login import login_required, current_user
from flask_babel import lazy_gettext as _l
from functools import wraps
from urllib.parse import urlparse
from app.models.tenant import Tenant
from app.utils.scope import get_tenant_context, get_accessible_tenants, set_tenant_context as set_scope_tenant
from app.routes.admin import admin_bp


ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def sanitize_filename(text):
    """Sanitize text for use in HTTP Content-Disposition filename header."""
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\w\s\-\.]', '', text)
    text = re.sub(r'[\s\-]+', '_', text)
    return text.strip('_')


def allowed_image_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS


def validate_slug(slug):
    """Validate slug format - only allow safe URL characters."""
    if not slug:
        return True, None  # Empty slug is OK (optional)
    # Slug must be 3-100 chars, only lowercase letters, numbers, and hyphens
    # Must start and end with alphanumeric
    if len(slug) < 3:
        return False, 'Le slug doit contenir au moins 3 caracteres'
    if len(slug) > 100:
        return False, 'Le slug ne peut pas depasser 100 caracteres'
    if not re.match(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$', slug) and len(slug) > 2:
        return False, 'Le slug ne peut contenir que des lettres minuscules, chiffres et tirets'
    if '--' in slug:
        return False, 'Le slug ne peut pas contenir deux tirets consecutifs'
    return True, None


def safe_redirect_referrer(default_url):
    """
    Safely redirect to referrer if it's on the same host, otherwise to default.
    Prevents open redirect attacks.
    """
    referrer = request.referrer
    if referrer:
        ref_url = urlparse(request.host_url)
        test_url = urlparse(referrer)
        # Only allow same host redirects
        if test_url.netloc == ref_url.netloc:
            return redirect(referrer)
    return redirect(default_url)


def admin_required(f):
    """Require superadmin OR group admin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_any_admin:
            flash(_l('Acces non autorise'), 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function


def superadmin_required(f):
    """Require superadmin (full) access only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_superadmin:
            flash(_l('Acces reserve aux super-administrateurs'), 'error')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


@admin_bp.app_context_processor  # the navbar selector shows on every page, not only /admin ones
def inject_tenant_context():
    """Navbar organization selector, on every page an admin sees."""
    if current_user.is_authenticated and current_user.is_any_admin:
        tenant_context = get_tenant_context()
        accessible_tenants = get_accessible_tenants()
        return {
            'tenant_context': tenant_context,
            'accessible_tenants': accessible_tenants,
            'show_tenant_selector': len(accessible_tenants) > 0
        }
    return {
        'tenant_context': None,
        'accessible_tenants': [],
        'show_tenant_selector': False
    }


@admin_bp.route('/set-tenant-context/<identifier>')
@login_required
@admin_required
def set_tenant_context(identifier):
    """Set the tenant context filter."""
    tenant = Tenant.get_by_identifier(identifier)
    if not tenant:
        flash(_l('Etablissement introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Verify access
    if not current_user.is_superadmin and not current_user.is_admin_of_tenant(tenant.id):
        flash(_l('Acces non autorise a cet etablissement'), 'error')
        return redirect(url_for('admin.dashboard'))

    set_scope_tenant(tenant)
    flash(_l('Contexte: %(name)s', name=tenant.name), 'info')

    # Redirect back to referrer (validated) or dashboard
    return safe_redirect_referrer(url_for('admin.dashboard'))


@admin_bp.route('/clear-tenant-context')
@login_required
@admin_required
def clear_tenant_context():
    """Clear the tenant context filter (show all)."""
    set_scope_tenant(None)
    flash(_l('Contexte : tous les etablissements'), 'info')
    return safe_redirect_referrer(url_for('admin.dashboard'))
