"""
Routes pour la gestion des tenants (organisations).
"""
from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from functools import wraps
import re
from app import db
from app.models.tenant import Tenant, tenant_admins
from app.models.user import User
from app.models.group import Group
from app.models.quiz import Quiz

tenant_bp = Blueprint('tenant', __name__)


def superadmin_required(f):
    """Require superadmin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_superadmin:
            flash('Accès réservé aux super-administrateurs', 'error')
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
            flash('Accès non autorisé', 'error')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def validate_slug(slug):
    """Valide le format du slug."""
    if not slug:
        return False, "Le slug est requis"
    if len(slug) < 3 or len(slug) > 50:
        return False, "Le slug doit faire entre 3 et 50 caractères"
    if not re.match(r'^[a-z][a-z0-9-]*[a-z0-9]$', slug) and len(slug) > 2:
        return False, "Le slug doit commencer par une lettre et ne contenir que des lettres minuscules, chiffres et tirets"
    if '--' in slug:
        return False, "Le slug ne peut pas contenir deux tirets consécutifs"
    return True, None


# ==================== Routes Superadmin ====================

@tenant_bp.route('/list')
@login_required
@superadmin_required
def list_tenants():
    """Liste tous les tenants (superadmin only)."""
    tenants = Tenant.query.order_by(Tenant.name).all()
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
            errors.append("Le nom est requis")

        if not slug:
            slug = Tenant.generate_slug(name)
        else:
            valid, error = validate_slug(slug)
            if not valid:
                errors.append(error)
            elif Tenant.query.filter_by(slug=slug).first():
                errors.append("Ce slug est déjà utilisé")

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
                errors.append("Format de date invalide")

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

        flash(f'Tenant "{name}" créé avec succès', 'success')
        return redirect(url_for('tenant.view_tenant', tenant_id=tenant.id))

    return render_template('admin/tenants/create.html')


@tenant_bp.route('/<int:tenant_id>')
@login_required
@tenant_admin_required
def view_tenant(tenant_id):
    """Voir les détails d'un tenant."""
    tenant = Tenant.query.get_or_404(tenant_id)

    # Vérifier accès
    if not current_user.is_superadmin and not current_user.is_admin_of_tenant(tenant_id):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin.dashboard'))

    # Stats
    stats = tenant.get_usage_stats()
    ai_stats = tenant.get_ai_usage_stats()

    # Admins du tenant
    admins = tenant.admins.all()

    # Groupes du tenant
    groups = tenant.groups.order_by(Group.name).all()

    return render_template(
        'admin/tenants/view.html',
        tenant=tenant,
        stats=stats,
        ai_stats=ai_stats,
        admins=admins,
        groups=groups
    )


@tenant_bp.route('/<int:tenant_id>/edit', methods=['GET', 'POST'])
@login_required
@superadmin_required
def edit_tenant(tenant_id):
    """Modifier un tenant (superadmin only)."""
    tenant = Tenant.query.get_or_404(tenant_id)

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
                flash("Format de date d'expiration invalide", 'error')
                return render_template('admin/tenants/edit.html', tenant=tenant)
        else:
            tenant.subscription_expires_at = None

        db.session.commit()
        flash('Tenant mis à jour', 'success')
        return redirect(url_for('tenant.view_tenant', tenant_id=tenant.id))

    return render_template('admin/tenants/edit.html', tenant=tenant)


@tenant_bp.route('/<int:tenant_id>/delete', methods=['POST'])
@login_required
@superadmin_required
def delete_tenant(tenant_id):
    """Supprimer un tenant (superadmin only)."""
    tenant = Tenant.query.get_or_404(tenant_id)

    # Vérifier qu'il n'y a pas de groupes
    if tenant.groups.count() > 0:
        flash('Impossible de supprimer un tenant qui contient des groupes', 'error')
        return redirect(url_for('tenant.view_tenant', tenant_id=tenant.id))

    name = tenant.name
    db.session.delete(tenant)
    db.session.commit()

    flash(f'Tenant "{name}" supprimé', 'info')
    return redirect(url_for('tenant.list_tenants'))


# ==================== Gestion des admins de tenant ====================

@tenant_bp.route('/<int:tenant_id>/admins')
@login_required
@superadmin_required
def manage_admins(tenant_id):
    """Gérer les admins d'un tenant."""
    tenant = Tenant.query.get_or_404(tenant_id)
    admins = tenant.admins.all()

    # Utilisateurs disponibles (non admin de ce tenant, email vérifié)
    admin_ids = [a.id for a in admins]
    query = User.query.filter(User.email_verified == True)
    if admin_ids:
        query = query.filter(User.id.notin_(admin_ids))
    available_users = query.order_by(User.username).limit(50).all()

    return render_template(
        'admin/tenants/admins.html',
        tenant=tenant,
        admins=admins,
        available_users=available_users
    )


@tenant_bp.route('/<int:tenant_id>/admins/add', methods=['POST'])
@login_required
@superadmin_required
def add_admin(tenant_id):
    """Ajouter un admin au tenant."""
    tenant = Tenant.query.get_or_404(tenant_id)
    user_id = request.form.get('user_id', type=int)

    if not user_id:
        flash('Utilisateur non spécifié', 'error')
        return redirect(url_for('tenant.manage_admins', tenant_id=tenant_id))

    user = User.query.get_or_404(user_id)
    tenant.add_admin(user)
    db.session.commit()

    flash(f'{user.username} est maintenant admin du tenant', 'success')
    return redirect(url_for('tenant.manage_admins', tenant_id=tenant_id))


@tenant_bp.route('/<int:tenant_id>/admins/<int:user_id>/remove', methods=['POST'])
@login_required
@superadmin_required
def remove_admin(tenant_id, user_id):
    """Retirer un admin du tenant."""
    tenant = Tenant.query.get_or_404(tenant_id)
    user = User.query.get_or_404(user_id)

    tenant.remove_admin(user)
    db.session.commit()

    flash(f'{user.username} n\'est plus admin du tenant', 'info')
    return redirect(url_for('tenant.manage_admins', tenant_id=tenant_id))


# ==================== Routes Tenant Admin ====================

@tenant_bp.route('/<int:tenant_id>/groups')
@login_required
@tenant_admin_required
def tenant_groups(tenant_id):
    """Liste des groupes d'un tenant."""
    tenant = Tenant.query.get_or_404(tenant_id)

    if not current_user.is_superadmin and not current_user.is_admin_of_tenant(tenant_id):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin.dashboard'))

    groups = tenant.groups.order_by(Group.name).all()
    return render_template('admin/tenants/groups.html', tenant=tenant, groups=groups)


@tenant_bp.route('/<int:tenant_id>/groups/create', methods=['GET', 'POST'])
@login_required
@tenant_admin_required
def create_group_in_tenant(tenant_id):
    """Créer un groupe dans un tenant."""
    tenant = Tenant.query.get_or_404(tenant_id)

    if not current_user.is_superadmin and not current_user.is_admin_of_tenant(tenant_id):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin.dashboard'))

    # Vérifier limite
    if not tenant.can_add_group():
        flash(f'Limite de groupes atteinte ({tenant.max_groups})', 'error')
        return redirect(url_for('tenant.tenant_groups', tenant_id=tenant_id))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        description = request.form.get('description', '').strip()
        max_members = request.form.get('max_members', 0, type=int)

        if not name:
            flash('Le nom est requis', 'error')
            return render_template('admin/tenants/create_group.html', tenant=tenant)

        group = Group(
            name=name,
            description=description,
            max_members=max_members,
            join_code=Group.generate_join_code(),
            tenant_id=tenant.id
        )
        db.session.add(group)
        db.session.commit()

        flash(f'Groupe "{name}" créé avec succès', 'success')
        return redirect(url_for('tenant.tenant_groups', tenant_id=tenant_id))

    return render_template('admin/tenants/create_group.html', tenant=tenant)


@tenant_bp.route('/<int:tenant_id>/quizzes')
@login_required
@tenant_admin_required
def tenant_quizzes(tenant_id):
    """Liste des quiz d'un tenant."""
    tenant = Tenant.query.get_or_404(tenant_id)

    if not current_user.is_superadmin and not current_user.is_admin_of_tenant(tenant_id):
        flash('Accès non autorisé', 'error')
        return redirect(url_for('admin.dashboard'))

    quizzes = tenant.quizzes.order_by(Quiz.created_at.desc()).all()
    return render_template('admin/tenants/quizzes.html', tenant=tenant, quizzes=quizzes)


# ==================== API ====================

@tenant_bp.route('/api/search-users')
@login_required
@superadmin_required
def search_users():
    """API pour rechercher des utilisateurs (pour ajouter comme admin)."""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])

    users = User.query.filter(
        db.or_(
            User.username.ilike(f'%{query}%'),
            User.email.ilike(f'%{query}%'),
            User.first_name.ilike(f'%{query}%'),
            User.last_name.ilike(f'%{query}%')
        ),
        User.email_verified == True
    ).limit(10).all()

    return jsonify([
        {
            'id': u.id,
            'username': u.username,
            'email': u.email,
            'full_name': u.full_name
        }
        for u in users
    ])
