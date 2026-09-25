"""
Routes pour la gestion des tenants (organisations).
"""
from flask import current_app, Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from flask_babel import lazy_gettext as _l
from functools import wraps
import os
import re
from app import db
from app.models.tenant import Tenant, tenant_admins
from app.models.user import User
from app.models.group import Group
from app.models.quiz import Quiz, quiz_groups
from app.models.interview import Interview, interview_groups

tenant_bp = Blueprint('tenant', __name__)


def superadmin_required(f):
    """Require superadmin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_superadmin:
            flash(_l('Acces reserve aux super-administrateurs'), 'error')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def tenant_admin_required(f):
    """Require tenant admin or superadmin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not (current_user.is_superadmin or current_user.is_tenant_admin):
            flash(_l('Acces non autorise'), 'error')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def validate_slug(slug):
    """Valide le format du slug."""
    if not slug:
        return False, _l("Le slug est requis")
    if len(slug) < 3 or len(slug) > 50:
        return False, _l("Le slug doit faire entre 3 et 50 caracteres")
    if not re.match(r'^[a-z][a-z0-9-]*[a-z0-9]$', slug) and len(slug) > 2:
        return False, _l("Le slug doit commencer par une lettre et ne contenir que des lettres minuscules, chiffres et tirets")
    if '--' in slug:
        return False, _l("Le slug ne peut pas contenir deux tirets consecutifs")
    return True, None


# ==================== Routes Superadmin ====================

@tenant_bp.route('/list')
@login_required
@tenant_admin_required
def list_tenants():
    """All organizations for a superadmin; one's own for an organization admin
    (straight to its page when there is only one)."""
    if current_user.is_superadmin:
        tenants = Tenant.query.order_by(Tenant.name).all()
    else:
        tenants = current_user.admin_tenants.order_by(Tenant.name).all()
        if len(tenants) == 1:
            return redirect(url_for('tenant.view_tenant', identifier=tenants[0].get_url_identifier()))
    return render_template('admin/tenants/list.html', tenants=tenants)


@tenant_bp.route('/create', methods=['GET', 'POST'])
@login_required
@superadmin_required
def create_tenant():
    """Créer un nouveau tenant (superadmin only)."""
    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        slug = request.form.get('slug', '').strip().lower()
        description = request.form.get('description', '').strip()
        contact_email = request.form.get('contact_email', '').strip()
        contact_name = request.form.get('contact_name', '').strip()
        max_users = request.form.get('max_users', 0, type=int)
        max_quizzes = request.form.get('max_quizzes', 0, type=int)
        max_groups = request.form.get('max_groups', 0, type=int)

        # Validation
        errors = []
        if not name:
            errors.append(_l("Le nom est requis"))

        if not slug:
            slug = Tenant.generate_slug(name)
        else:
            valid, error = validate_slug(slug)
            if not valid:
                errors.append(error)
            elif Tenant.query.filter_by(slug=slug).first():
                errors.append(_l("Ce slug est deja utilise"))

        # Limites mensuelles IA
        monthly_ai_corrections = request.form.get('monthly_ai_corrections', 0, type=int)
        monthly_quiz_generations = request.form.get('monthly_quiz_generations', 0, type=int)
        monthly_class_analyses = request.form.get('monthly_class_analyses', 0, type=int)
        monthly_interviews = request.form.get('monthly_interviews', 0, type=int)

        # Alertes quota
        quota_alert_enabled = 'quota_alert_enabled' in request.form
        quota_alert_threshold = request.form.get('quota_alert_threshold', 10, type=int)

        # Date d'expiration
        subscription_expires_at = None
        expires_str = request.form.get('subscription_expires_at', '').strip()
        if expires_str:
            from datetime import datetime
            try:
                subscription_expires_at = datetime.strptime(expires_str, '%Y-%m-%d').date()
            except ValueError:
                errors.append(_l("Format de date invalide"))

        if errors:
            for error in errors:
                flash(error, 'error')
            return render_template('admin/tenants/create.html')

        tenant = Tenant(
            name=name,
            slug=slug,
            description=description,
            contact_email=contact_email,
            contact_name=contact_name,
            max_users=max_users,
            max_quizzes=max_quizzes,
            max_groups=max_groups,
            monthly_ai_corrections=monthly_ai_corrections,
            monthly_quiz_generations=monthly_quiz_generations,
            monthly_class_analyses=monthly_class_analyses,
            monthly_interviews=monthly_interviews,
            quota_alert_enabled=quota_alert_enabled,
            quota_alert_threshold=quota_alert_threshold,
            subscription_expires_at=subscription_expires_at
        )
        db.session.add(tenant)
        db.session.commit()

        flash(_l('Etablissement "%(name)s" cree avec succes', name=name), 'success')
        return redirect(url_for('tenant.view_tenant', identifier=tenant.get_url_identifier()))

    return render_template('admin/tenants/create.html')


def _tenant_or_redirect(identifier, endpoint='tenant.view_tenant'):
    """(tenant, None) if the organization exists and is ours, else (None, redirect)."""
    tenant = Tenant.get_by_identifier(identifier)
    if not tenant:
        flash(_l('Etablissement introuvable'), 'error')
        return None, redirect(url_for('admin.dashboard'))
    if not current_user.is_superadmin and not current_user.is_admin_of_tenant(tenant.id):
        flash(_l('Acces non autorise'), 'error')
        return None, redirect(url_for('admin.dashboard'))
    return tenant, None


def _tenant_page(tenant, tab):
    """The organization page, opened on a tab (former sub-pages redirect here)."""
    return redirect(url_for('tenant.view_tenant', identifier=tenant.get_url_identifier(), _anchor=tab))


@tenant_bp.route('/<identifier>')
@login_required
@tenant_admin_required
def view_tenant(identifier):
    """Everything about one organization: groups, admins, content, quotas."""
    tenant, error = _tenant_or_redirect(identifier)
    if error:
        return error
    if identifier != tenant.get_url_identifier():
        return redirect(url_for('tenant.view_tenant', identifier=tenant.get_url_identifier()), code=301)

    groups = tenant.groups.order_by(Group.name).all()
    learner_counts, instructor_counts = Group.role_counts(groups)

    quizzes = tenant.quizzes.order_by(Quiz.created_at.desc()).all()
    interviews = Interview.query.filter_by(tenant_id=tenant.id).order_by(Interview.created_at.desc()).all()
    # Content no learner can see (no group)
    quiz_ids = [q.id for q in quizzes]
    interview_ids = [i.id for i in interviews]
    quizzes_with_group = {r[0] for r in db.session.query(quiz_groups.c.quiz_id).filter(
        quiz_groups.c.quiz_id.in_(quiz_ids))} if quiz_ids else set()
    interviews_with_group = {r[0] for r in db.session.query(interview_groups.c.interview_id).filter(
        interview_groups.c.interview_id.in_(interview_ids))} if interview_ids else set()

    return render_template(
        'admin/tenants/view.html',
        tenant=tenant,
        stats=tenant.get_usage_stats(),
        ai_stats=tenant.get_ai_usage_stats(),
        admins=tenant.admins.order_by(User.last_name, User.username).all(),
        groups=groups,
        learner_counts=learner_counts,
        instructor_counts=instructor_counts,
        quizzes=quizzes,
        interviews=interviews,
        quizzes_with_group=quizzes_with_group,
        interviews_with_group=interviews_with_group,
    )


@tenant_bp.route('/<identifier>/edit', methods=['GET', 'POST'])
@login_required
@superadmin_required
def edit_tenant(identifier):
    """Modifier un tenant (superadmin only)."""
    tenant = Tenant.get_by_identifier(identifier)
    if not tenant:
        flash(_l('Etablissement introuvable'), 'error')
        return redirect(url_for('tenant.list_tenants'))

    # Redirect if accessed by old numeric ID
    if identifier != tenant.get_url_identifier():
        return redirect(url_for('tenant.edit_tenant', identifier=tenant.get_url_identifier()), code=301)

    if request.method == 'POST':
        tenant.name = request.form.get('name', tenant.name).strip()
        tenant.description = request.form.get('description', '').strip()
        tenant.contact_email = request.form.get('contact_email', '').strip()
        tenant.contact_name = request.form.get('contact_name', '').strip()
        tenant.max_users = request.form.get('max_users', 0, type=int)
        tenant.max_quizzes = request.form.get('max_quizzes', 0, type=int)
        tenant.max_groups = request.form.get('max_groups', 0, type=int)
        tenant.is_active = 'is_active' in request.form
        tenant.internal_notes = request.form.get('internal_notes', '').strip()

        # Limites mensuelles IA
        tenant.monthly_ai_corrections = request.form.get('monthly_ai_corrections', 0, type=int)
        tenant.monthly_quiz_generations = request.form.get('monthly_quiz_generations', 0, type=int)
        tenant.monthly_class_analyses = request.form.get('monthly_class_analyses', 0, type=int)
        tenant.monthly_interviews = request.form.get('monthly_interviews', 0, type=int)

        # Alertes quota
        tenant.quota_alert_enabled = 'quota_alert_enabled' in request.form
        tenant.quota_alert_threshold = request.form.get('quota_alert_threshold', 10, type=int)

        # Date d'expiration
        expires_str = request.form.get('subscription_expires_at', '').strip()
        if expires_str:
            from datetime import datetime
            try:
                tenant.subscription_expires_at = datetime.strptime(expires_str, '%Y-%m-%d').date()
            except ValueError:
                flash(_l('Format de date d\'expiration invalide'), 'error')
                return render_template('admin/tenants/edit.html', tenant=tenant)
        else:
            tenant.subscription_expires_at = None

        db.session.commit()
        flash(_l('Etablissement mis a jour'), 'success')
        return redirect(url_for('tenant.view_tenant', identifier=tenant.get_url_identifier()))

    return render_template('admin/tenants/edit.html', tenant=tenant)


@tenant_bp.route('/<identifier>/delete', methods=['GET', 'POST'])
@login_required
@superadmin_required
def delete_tenant(identifier):
    """Delete an organization with its groups and content, after confirmation."""
    from app.utils.backup_manager import BackupManager
    from app.utils.deletion import delete_tenant as remove_tenant, tenant_deletion_plan

    tenant = Tenant.get_by_identifier(identifier)
    if not tenant:
        flash(_l('Etablissement introuvable'), 'error')
        return redirect(url_for('tenant.list_tenants'))

    if request.method == 'GET':
        return render_template('admin/tenants/delete.html', tenant=tenant, plan=tenant_deletion_plan(tenant))

    if request.form.get('confirm_name', '').strip() != tenant.name:
        flash(_l("Le nom saisi ne correspond pas : rien n'a ete supprime"), 'error')
        return redirect(url_for('tenant.delete_tenant', identifier=tenant.get_url_identifier()))

    # Safety net: full backup first, restorable from Settings
    manager = BackupManager()
    ok, path, message, _ = manager.create_backup()
    if not ok:
        flash(_l("Sauvegarde prealable impossible, rien n'a ete supprime : %(error)s", error=message), 'error')
        return redirect(url_for('tenant.delete_tenant', identifier=tenant.get_url_identifier()))
    backup_name = os.path.basename(manager.keep_locally(path, prefix='backup_avant_suppression_'))

    name = tenant.name
    plan = remove_tenant(tenant, delete_accounts=request.form.get('delete_accounts') == 'on')
    db.session.commit()
    current_app.logger.warning(f"Tenant {name} deleted by {current_user.username} (backup {backup_name})")

    flash(_l('Etablissement "%(name)s" supprime (sauvegarde prealable : %(backup)s)',
             name=name, backup=backup_name), 'success')
    return redirect(url_for('tenant.list_tenants'))


# ==================== Organization admins ====================

@tenant_bp.route('/<identifier>/admins')
@login_required
@tenant_admin_required
def manage_admins(identifier):
    """Former admins page, now a tab of the organization page."""
    tenant, error = _tenant_or_redirect(identifier)
    return error or _tenant_page(tenant, 'admins')


@tenant_bp.route('/<identifier>/admins/candidates')
@login_required
@superadmin_required
def admin_candidates(identifier):
    """People matching ?q= who could become admin of this organization (for the add box)."""
    tenant = Tenant.get_by_identifier(identifier)
    q = request.args.get('q', '').strip()
    if not tenant or len(q) < 2:
        return jsonify([])
    current_admins = db.session.query(tenant_admins.c.user_id).filter(tenant_admins.c.tenant_id == tenant.id)
    pattern = f'%{q}%'
    users = User.query.filter(
        ~User.id.in_(current_admins),
        User.is_admin == False,  # noqa: E712  (superadmins already see everything)
        db.or_(User.username.ilike(pattern), User.email.ilike(pattern),
               User.first_name.ilike(pattern), User.last_name.ilike(pattern))
    ).order_by(User.last_name, User.username).limit(15).all()
    return jsonify([{'id': u.get_url_identifier(), 'name': u.full_name, 'username': u.username, 'email': u.email}
                    for u in users])


@tenant_bp.route('/<identifier>/admins/add', methods=['POST'])
@login_required
@superadmin_required
def add_admin(identifier):
    """Make someone admin of the organization."""
    tenant, error = _tenant_or_redirect(identifier)
    if error:
        return error
    user = User.get_by_identifier(request.form.get('user', ''))
    if not user:
        flash(_l('Utilisateur introuvable'), 'error')
    elif user.is_superadmin:
        flash(_l('Un super-administrateur a deja acces a tous les etablissements'), 'info')
    else:
        tenant.add_admin(user)
        db.session.commit()
        flash(_l("%(username)s est maintenant admin de l'etablissement", username=user.full_name), 'success')
    return _tenant_page(tenant, 'admins')


@tenant_bp.route('/<identifier>/admins/<user_identifier>/remove', methods=['POST'])
@login_required
@superadmin_required
def remove_admin(identifier, user_identifier):
    """Remove someone from the organization admins (the account stays)."""
    tenant, error = _tenant_or_redirect(identifier)
    if error:
        return error
    user = User.get_by_identifier(user_identifier)
    if not user:
        flash(_l('Utilisateur introuvable'), 'error')
    else:
        tenant.remove_admin(user)
        db.session.commit()
        flash(_l('%(username)s n\'est plus admin de l\'etablissement', username=user.full_name), 'info')
    return _tenant_page(tenant, 'admins')


# ==================== Former sub-pages ====================

@tenant_bp.route('/<identifier>/groups')
@login_required
@tenant_admin_required
def tenant_groups(identifier):
    """Former groups page, now a tab of the organization page."""
    tenant, error = _tenant_or_redirect(identifier)
    return error or _tenant_page(tenant, 'groups')


@tenant_bp.route('/<identifier>/groups/create')
@login_required
@tenant_admin_required
def create_group_in_tenant(identifier):
    """Former creation form: the group form, with this organization selected."""
    tenant, error = _tenant_or_redirect(identifier)
    return error or redirect(url_for('admin.create_group', tenant=tenant.get_url_identifier()))


@tenant_bp.route('/<identifier>/quizzes')
@login_required
@tenant_admin_required
def tenant_quizzes(identifier):
    """Former quiz page, now a tab of the organization page."""
    tenant, error = _tenant_or_redirect(identifier)
    return error or _tenant_page(tenant, 'content')
