"""Users: list, person page, creation, CSV import, edition, deletion, bulk actions."""
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from flask_babel import lazy_gettext as _l
from app import db
from app.models.user import User, user_groups
from app.models.group import Group
from app.models.quiz import QuizResponse
from app.models.tenant import Tenant, tenant_admins
from app.models.interview import InterviewSession
from app.utils.deletion import delete_user_account
from app.utils.email_sender import send_verification_email
from app.utils.scope import (
    get_accessible_tenants,
    scoped_groups,
    scoped_users,
    validate_group_ids,
    breadcrumb,
)
from app.routes.admin import admin_bp
from app.routes.admin.common import admin_required, safe_redirect_referrer


@admin_bp.route('/users')
@login_required
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search = request.args.get('search', '', type=str).strip()
    filter_group_id = request.args.get('group', 0, type=int)
    filter_role = request.args.get('role', '', type=str)
    sort_by = request.args.get('sort', 'created_at')
    sort_dir = request.args.get('dir', 'desc')

    # Validate sort and role parameters
    valid_sorts = ['full_name', 'username', 'email', 'created_at', 'last_login']
    valid_roles = ['', 'superadmin', 'tenant_admin', 'group_admin', 'user']
    if sort_by not in valid_sorts:
        sort_by = 'created_at'
    if sort_dir not in ['asc', 'desc']:
        sort_dir = 'desc'
    if filter_role not in valid_roles:
        filter_role = ''

    all_groups = scoped_groups().all()
    query = scoped_users()

    # Filter by selected group (using subquery to avoid JOIN conflicts)
    if filter_group_id > 0:
        users_in_group = db.session.query(user_groups.c.user_id).filter(
            user_groups.c.group_id == filter_group_id
        )
        query = query.filter(User.id.in_(users_in_group))

    if search:
        query = query.filter(
            db.or_(
                User.username.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                User.first_name.ilike(f'%{search}%'),
                User.last_name.ilike(f'%{search}%')
            )
        )

    # Filter by role (User.is_admin is the superadmin DB column)
    tenant_admin_ids = db.session.query(tenant_admins.c.user_id)
    group_admin_ids = db.session.query(user_groups.c.user_id).filter(user_groups.c.role == 'admin')
    if filter_role == 'superadmin':
        query = query.filter(User.is_admin == True)  # noqa: E712
    elif filter_role == 'tenant_admin':
        query = query.filter(User.is_admin == False, User.id.in_(tenant_admin_ids))  # noqa: E712
    elif filter_role == 'group_admin':
        query = query.filter(User.is_admin == False, User.id.in_(group_admin_ids),  # noqa: E712
                             ~User.id.in_(tenant_admin_ids))
    elif filter_role == 'user':
        query = query.filter(User.is_admin == False, ~User.id.in_(tenant_admin_ids),  # noqa: E712
                             ~User.id.in_(group_admin_ids))

    # Apply sorting (MySQL compatible - no NULLS LAST support)
    sort_column_map = {
        'full_name': User.last_name,
        'username': User.username,
        'email': User.email,
        'created_at': User.created_at,
        'last_login': User.last_login
    }
    sort_column = sort_column_map.get(sort_by, User.created_at)
    if sort_dir == 'asc':
        # For ASC, put NULLs at the end: ORDER BY col IS NULL, col ASC
        query = query.order_by(sort_column.is_(None), sort_column.asc())
    else:
        # For DESC, put NULLs at the end: ORDER BY col IS NULL, col DESC
        query = query.order_by(sort_column.is_(None), sort_column.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    all_users = pagination.items
    return render_template('admin/users.html', users=all_users, pagination=pagination, search=search,
                          all_groups=all_groups, filter_group_id=filter_group_id,
                          filter_role=filter_role, sort_by=sort_by, sort_dir=sort_dir,
                          meta=users_list_meta(all_users))


def users_list_meta(users):
    """Groups, roles and permissions for a page of users, in 2 queries instead of ~5 per row.

    Returns {user_id: {'groups': [(group, role)], 'rank': int, 'can_manage': bool}}.
    """
    ids = [u.id for u in users]
    memberships = {uid: [] for uid in ids}
    tenant_admin_ids = set()
    if ids:
        rows = db.session.query(user_groups.c.user_id, Group, user_groups.c.role).join(
            Group, Group.id == user_groups.c.group_id
        ).filter(user_groups.c.user_id.in_(ids)).order_by(Group.name).all()
        for uid, group, role in rows:
            memberships[uid].append((group, role))
        tenant_admin_ids = {row[0] for row in db.session.query(tenant_admins.c.user_id).filter(
            tenant_admins.c.user_id.in_(ids))}
    meta = {}
    for u in users:
        groups = memberships[u.id]
        if u.is_admin:
            rank = 3
        elif u.id in tenant_admin_ids:
            rank = 2
        elif any(role == 'admin' for _, role in groups):
            rank = 1
        else:
            rank = 0
        meta[u.id] = {
            'groups': groups,
            'rank': rank,
            'can_manage': current_user.can_manage(u.id, rank, [(g.id, g.tenant_id) for g, _ in groups]),
            'can_delete': current_user.can_manage(u.id, rank, [(g.id, g.tenant_id) for g, _ in groups],
                                                  for_delete=True),
        }
    return meta


def _manageable_user_or_none(identifier):
    user = User.get_by_identifier(identifier)
    return user if user and current_user.can_manage_user(user) else None


@admin_bp.route('/user/<identifier>/send-reset', methods=['POST'])
@login_required
@admin_required
def send_user_reset(identifier):
    """Email the user a link to choose a new password (instead of the admin typing one)."""
    from app.utils.email_sender import send_reset_email
    user = _manageable_user_or_none(identifier)
    if not user:
        flash(_l('Vous n\'avez pas acces a cet utilisateur'), 'error')
    elif user.email.endswith('@imported.local'):
        flash(_l('%(name)s n\'a pas d\'adresse email reelle : copiez le lien et transmettez-le.',
                 name=user.full_name), 'warning')
    elif send_reset_email(user, by_admin=True):
        db.session.commit()
        flash(_l('Lien de reinitialisation envoye a %(email)s', email=user.email), 'success')
    else:
        flash(_l('Erreur lors de l\'envoi de l\'email.'), 'error')
    return safe_redirect_referrer(url_for('admin.users'))


@admin_bp.route('/user/<identifier>/reset-link', methods=['POST'])
@login_required
@admin_required
def user_reset_link(identifier):
    """Reset link to hand over directly (learners without a real email address)."""
    from app.utils.email_sender import ADMIN_RESET_LINK_HOURS
    user = _manageable_user_or_none(identifier)
    if not user:
        return jsonify({'error': 'forbidden'}), 403
    token = user.generate_reset_token(hours=ADMIN_RESET_LINK_HOURS)
    db.session.commit()
    return jsonify({'url': url_for('auth.reset_password', token=token, _external=True),
                    'hours': ADMIN_RESET_LINK_HOURS})


def _user_page_context(user):
    """Everything the person page shows: memberships, results, edit form data."""
    memberships = db.session.query(Group, user_groups.c.role).join(
        user_groups, user_groups.c.group_id == Group.id
    ).filter(user_groups.c.user_id == user.id).order_by(Group.name).all()

    # Results: only content the viewer can see
    responses = [r for r in QuizResponse.query.filter_by(user_id=user.id)
                 .order_by(QuizResponse.submitted_at.desc()).all()
                 if current_user.can_access_quiz(r.quiz)]
    sessions = [s for s in InterviewSession.query.filter_by(user_id=user.id, is_test=False)
                .order_by(InterviewSession.started_at.desc()).all()
                if current_user.can_access_interview(s.interview)]
    total = sum(r.total_score for r in responses)
    max_total = sum(r.max_score for r in responses)
    stats = {
        'quiz_count': len(responses),
        'interview_count': len(sessions),
        'average_percentage': (total / max_total * 100) if max_total > 0 else 0.0,
    }

    can_edit = user.id != current_user.id and current_user.can_manage_user(user)
    # One group: Organization > Group > Person; otherwise Users > Person
    if len(memberships) == 1 and current_user.can_access_group(memberships[0][0]):
        group = memberships[0][0]
        trail = breadcrumb(group.tenant, group, (user.full_name, None))
    else:
        trail = [(_l('Utilisateurs'), url_for('admin.users')), (user.full_name, None)]
    ctx = dict(breadcrumb=trail, user=user, memberships=memberships, admin_tenants=user.admin_tenants.order_by(Tenant.name).all(),
               responses=responses, sessions=sessions, stats=stats, can_edit=can_edit,
               can_delete=user.id != current_user.id and current_user.can_manage_user(user, for_delete=True))
    if can_edit:
        user_tenant_ids = sorted(user.admin_tenant_ids())
        ctx.update(
            groups=scoped_groups().all(),
            tenants=get_accessible_tenants() if current_user.is_superadmin else [],
            group_roles={g.id: role for g, role in memberships},
            user_tenant_ids=user_tenant_ids,
            global_role='superadmin' if user.is_superadmin else 'tenant_admin' if user_tenant_ids else 'none',
            can_set_instructor=current_user.role_rank >= 2,
            is_superadmin=current_user.is_superadmin,
        )
    return ctx


@admin_bp.route('/user/<identifier>')
@login_required
@admin_required
def user_detail(identifier):
    """Everything about one person: roles, groups, results, and the edit form."""
    user = User.get_by_identifier(identifier)
    if not user:
        flash(_l('Utilisateur introuvable'), 'error')
        return redirect(url_for('admin.users'))
    if identifier != user.get_url_identifier():
        return redirect(url_for('admin.user_detail', identifier=user.get_url_identifier()), code=301)
    if user.id != current_user.id and not current_user.can_access_user(user):
        flash(_l('Vous n\'avez pas acces a cet utilisateur'), 'error')
        return redirect(url_for('admin.users'))
    return render_template('admin/user_detail.html', **_user_page_context(user))


@admin_bp.route('/user/<identifier>/grades')
@login_required
@admin_required
def user_grades(identifier):
    """Former grades page, now a tab of the person page."""
    return redirect(url_for('admin.user_detail', identifier=identifier, _anchor='results'), code=301)


GLOBAL_ROLES = ('none', 'tenant_admin', 'superadmin')


def read_group_roles(form):
    """{group: 'member' | 'admin' | None} for the groups displayed in the form and in scope.

    Only groups listed in group_role_seen are considered, so a group the form
    didn't show is never touched.
    """
    wanted = {}
    for group in validate_group_ids(form.getlist('group_role_seen'), active_only=False):
        role = form.get(f'group_role_{group.id}')
        wanted[group] = role if role in ('member', 'admin') else None
    return wanted


def apply_group_roles(user, wanted, can_set_instructor):
    """Add, remove or change the user's role group by group. Returns error messages."""
    errors = []
    current = {row.group_id: row.role for row in db.session.execute(
        user_groups.select().where(user_groups.c.user_id == user.id))}
    for group, role in wanted.items():
        cur = current.get(group.id)
        if role == 'admin' and not can_set_instructor:
            role = cur or 'member'  # only organization admins name instructors
        if role == cur:
            continue
        if role is None:
            user.remove_from_group(group)
        elif cur is None:
            error = group.join_error(user)
            if error:
                errors.append(f'{group.name} : {error}')
                continue
            user.add_to_group(group, role)
        else:
            db.session.execute(user_groups.update().where(
                user_groups.c.user_id == user.id, user_groups.c.group_id == group.id
            ).values(role=role))
    User.clear_role_cache()
    return errors


def set_admin_tenants(user, tenant_ids):
    """Superadmin only: organizations this user administers."""
    user.admin_tenants = Tenant.query.filter(Tenant.id.in_(tenant_ids)).all() if tenant_ids else []
    User.clear_role_cache()


def _form_tenant_ids(form):
    return [int(t) for t in form.getlist('tenant_ids') if t.isdigit()]


@admin_bp.route('/user/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    """Create a user: global role (superadmin only) and a role per group."""
    import secrets
    from app.utils.email_sender import send_reset_email

    groups = scoped_groups().all()
    tenants = get_accessible_tenants() if current_user.is_superadmin else []
    can_set_instructor = current_user.role_rank >= 2
    preselected = request.args.get('group', type=int)

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')
        global_role = request.form.get('global_role', 'none') if current_user.is_superadmin else 'none'
        if global_role not in GLOBAL_ROLES:
            global_role = 'none'
        tenant_ids = _form_tenant_ids(request.form) if global_role == 'tenant_admin' else []
        wanted = {g: r for g, r in read_group_roles(request.form).items() if r} if global_role == 'none' else {}
        join_errors = [f'{g.name} : {g.join_error()}' for g in wanted if g.join_error()]

        if not username or not email:
            flash(_l('Nom d\'utilisateur et email sont requis'), 'error')
        elif User.query.filter_by(username=username).first():
            flash(_l('Ce nom d\'utilisateur existe deja'), 'error')
        elif User.query.filter_by(email=email).first():
            flash(_l('Cette adresse email est deja utilisee'), 'error')
        elif global_role == 'none' and not wanted:
            flash(_l('Vous devez assigner au moins un groupe'), 'error')
        elif global_role == 'tenant_admin' and not tenant_ids:
            flash(_l("Choisissez au moins un etablissement pour un admin d'etablissement"), 'error')
        elif join_errors:
            for error in join_errors:
                flash(error, 'error')
        else:
            user = User(username=username, first_name=first_name or None, last_name=last_name or None,
                        email=email, is_admin=(global_role == 'superadmin'))
            # No password typed: random one, the user chooses theirs through the invitation
            user.set_password(password or secrets.token_urlsafe(32))
            db.session.add(user)
            db.session.flush()
            apply_group_roles(user, wanted, can_set_instructor)
            if global_role == 'tenant_admin':
                set_admin_tenants(user, tenant_ids)
            db.session.commit()

            flash(_l('Utilisateur "%(username)s" cree avec succes', username=username), 'success')
            if not password:
                if email.endswith('@imported.local'):
                    flash(_l('Pas d\'email reel : copiez un lien de mot de passe depuis la page du groupe.'), 'warning')
                elif send_reset_email(user, by_admin=True):
                    db.session.commit()
                    flash(_l('Invitation envoyee a %(email)s pour choisir un mot de passe.', email=email), 'info')
                else:
                    flash(_l('Erreur lors de l\'envoi de l\'email.'), 'error')
            if preselected and len(wanted) == 1:
                return redirect(url_for('admin.group_detail', identifier=next(iter(wanted)).get_url_identifier()))
            return redirect(url_for('admin.users'))

    return render_template('admin/create_user.html', groups=groups, tenants=tenants,
                           is_superadmin=current_user.is_superadmin, can_set_instructor=can_set_instructor,
                           group_roles={preselected: 'member'} if preselected else {}, user_tenant_ids=[],
                           global_role='none')


@admin_bp.route('/users/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_users():
    """Import users from CSV file."""
    import csv
    from io import StringIO

    groups = scoped_groups().all()

    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash(_l('Aucun fichier selectionne'), 'error')
            return redirect(request.url)

        file = request.files['csv_file']
        if file.filename == '':
            flash(_l('Aucun fichier selectionne'), 'error')
            return redirect(request.url)

        default_group_id = request.form.get('default_group', type=int)
        default_password = request.form.get('default_password', '').strip()

        if not default_group_id:
            flash(_l('Veuillez selectionner un groupe par defaut'), 'error')
            return redirect(request.url)

        # Group must be in scope
        valid = validate_group_ids([default_group_id])
        default_group = valid[0] if valid else None
        if not default_group:
            flash(_l('Groupe invalide'), 'error')
            return redirect(request.url)

        try:
            # Read CSV content
            content = file.read().decode('utf-8-sig')  # Handle BOM
            reader = csv.DictReader(StringIO(content), delimiter=';')

            created_count = 0
            skipped_count = 0
            errors = []

            for row_num, row in enumerate(reader, start=2):
                # Get fields (flexible column names)
                username = (row.get('username') or row.get('identifiant') or row.get('login') or '').strip()
                email = (row.get('email') or row.get('mail') or row.get('courriel') or '').strip()
                first_name = (row.get('first_name') or row.get('prenom') or row.get('prénom') or '').strip()
                last_name = (row.get('last_name') or row.get('nom') or row.get('nom_famille') or '').strip()
                password = (row.get('password') or row.get('mot_de_passe') or default_password or '').strip()

                # Skip empty rows
                if not username and not email:
                    continue

                # Generate username from email if not provided
                if not username and email:
                    username = email.split('@')[0]

                # Generate email from username if not provided
                if username and not email:
                    email = f"{username}@imported.local"

                # Validation
                if not password:
                    errors.append(f"Ligne {row_num}: Mot de passe manquant pour {username}")
                    skipped_count += 1
                    continue

                if User.query.filter_by(username=username).first():
                    errors.append(f"Ligne {row_num}: Identifiant '{username}' existe deja")
                    skipped_count += 1
                    continue

                if User.query.filter_by(email=email).first():
                    errors.append(f"Ligne {row_num}: Email '{email}' existe deja")
                    skipped_count += 1
                    continue

                join_error = default_group.join_error()
                if join_error:
                    errors.append(f"Ligne {row_num}: {join_error}")
                    skipped_count += 1
                    continue

                # Create user
                user = User(
                    username=username,
                    email=email,
                    first_name=first_name if first_name else None,
                    last_name=last_name if last_name else None
                )
                user.set_password(password)
                db.session.add(user)
                db.session.flush()

                # Add to default group
                user.add_to_group(default_group, 'member')
                created_count += 1

            db.session.commit()

            if created_count > 0:
                flash(_l('%(count)s utilisateur(s) importe(s) avec succes dans le groupe "%(group)s"', count=created_count, group=default_group.name), 'success')
            if skipped_count > 0:
                flash(_l('%(count)s utilisateur(s) ignore(s)', count=skipped_count), 'warning')
            if errors:
                for error in errors[:5]:  # Show first 5 errors
                    flash(error, 'error')
                if len(errors) > 5:
                    flash(_l('... et %(count)s autre(s) erreur(s)', count=len(errors) - 5), 'error')

            return redirect(url_for('admin.users'))

        except Exception as e:
            db.session.rollback()
            flash(_l('Erreur lors de l\'import: %(error)s', error=str(e)), 'error')

    return render_template('admin/import_users.html', groups=groups)


@admin_bp.route('/user/<identifier>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(identifier):
    """Save the edit form of the person page (GET opens that page on the edit tab)."""
    user = User.get_by_identifier(identifier)
    if not user:
        flash(_l('Utilisateur introuvable'), 'error')
        return redirect(url_for('admin.users'))

    if request.method == 'GET':
        return redirect(url_for('admin.user_detail', identifier=user.get_url_identifier(), _anchor='edit'))

    # Prevent editing yourself to remove admin rights
    if user.id == current_user.id:
        flash(_l('Vous ne pouvez pas modifier votre propre compte ici'), 'error')
        return redirect(url_for('admin.users'))

    # Write access: lower role only, and all of the user's groups must be ours
    if not current_user.can_manage_user(user):
        flash(_l('Vous n\'avez pas acces a cet utilisateur'), 'error')
        return redirect(url_for('admin.users'))

    user_tenant_ids = sorted(user.admin_tenant_ids())
    can_set_instructor = current_user.role_rank >= 2
    if user.is_superadmin:
        global_role = 'superadmin'
    elif user_tenant_ids:
        global_role = 'tenant_admin'
    else:
        global_role = 'none'

    if request.method == 'POST':
        action = request.form.get('action')

        # Handle email verification actions
        if action == 'verify_email':
            user.email_verified = True
            user.clear_verification_token()
            db.session.commit()
            flash(_l('Email de %(username)s verifie manuellement.', username=user.username), 'success')
            return redirect(url_for('admin.user_detail', identifier=user.get_url_identifier(), _anchor='edit'))

        elif action == 'resend_verification':
            if send_verification_email(user):
                db.session.commit()
                flash(_l('Email de verification renvoye a %(email)s.', email=user.email), 'success')
            else:
                flash(_l('Erreur lors de l\'envoi de l\'email.'), 'error')
            return redirect(url_for('admin.user_detail', identifier=user.get_url_identifier(), _anchor='edit'))

        username = request.form.get('username', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password')

        if not username or not email:
            flash(_l('Nom d\'utilisateur et email sont requis'), 'error')
        elif User.query.filter(User.username == username, User.id != user.id).first():
            flash(_l('Ce nom d\'utilisateur existe deja'), 'error')
        elif User.query.filter(User.email == email, User.id != user.id).first():
            flash(_l('Cette adresse email est deja utilisee'), 'error')
        else:
            user.username = username
            user.first_name = first_name or None
            user.last_name = last_name or None
            user.email = email

            # Global role: superadmins only
            new_global_role = global_role
            if current_user.is_superadmin:
                new_global_role = request.form.get('global_role', global_role)
                if new_global_role not in GLOBAL_ROLES:
                    new_global_role = global_role
                user.is_admin = new_global_role == 'superadmin'
                set_admin_tenants(user, _form_tenant_ids(request.form) if new_global_role == 'tenant_admin' else [])

            # Roles per group (memberships outside the displayed groups are kept)
            if new_global_role == 'none':
                for error in apply_group_roles(user, read_group_roles(request.form), can_set_instructor):
                    flash(error, 'error')

            if password:
                user.set_password(password)

            db.session.commit()
            User.clear_role_cache()
            flash(_l('Utilisateur "%(username)s" mis a jour avec succes', username=username), 'success')
            return redirect(url_for('admin.user_detail', identifier=user.get_url_identifier()))

    # Validation error: back on the edit tab
    db.session.rollback()
    return render_template('admin/user_detail.html', open_tab='edit', **_user_page_context(user))


@admin_bp.route('/user/<identifier>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(identifier):
    """Delete a user."""
    user = User.get_by_identifier(identifier)
    if not user:
        flash(_l('Utilisateur introuvable'), 'error')
        return redirect(url_for('admin.users'))

    # Prevent self-deletion
    if user.id == current_user.id:
        flash(_l('Vous ne pouvez pas supprimer votre propre compte'), 'error')
        return redirect(url_for('admin.users'))

    # Write access: lower role only, and all of the user's groups must be ours
    if not current_user.can_manage_user(user, for_delete=True):
        flash(_l('Vous n\'avez pas acces a cet utilisateur'), 'error')
        return redirect(url_for('admin.users'))

    username = user.username
    delete_user_account(user)
    db.session.commit()

    flash(_l('Utilisateur "%(username)s" supprime avec succes', username=username), 'success')
    return redirect(url_for('admin.users'))


# Bulk user actions
@admin_bp.route('/users/bulk-delete', methods=['POST'])
@login_required
@admin_required
def bulk_delete_users():
    """Delete multiple users at once."""
    user_ids = request.form.getlist('user_ids', type=int)
    if not user_ids:
        flash(_l('Aucun utilisateur selectionne'), 'warning')
        return redirect(url_for('admin.users'))

    deleted_count = 0
    skipped_count = 0

    for user_id in user_ids:
        user = User.query.get(user_id)
        if not user:
            continue

        # Skip self-deletion
        if user.id == current_user.id:
            skipped_count += 1
            continue

        # Permission check (write access)
        if not current_user.can_manage_user(user, for_delete=True):
            skipped_count += 1
            continue

        delete_user_account(user)
        deleted_count += 1

    db.session.commit()

    if deleted_count > 0:
        flash(_l('%(count)s utilisateur(s) supprime(s)', count=deleted_count), 'success')
    if skipped_count > 0:
        flash(_l('%(count)s utilisateur(s) ignore(s) (pas de permission)', count=skipped_count), 'warning')

    return redirect(url_for('admin.users'))


@admin_bp.route('/users/bulk-change-group', methods=['POST'])
@login_required
@admin_required
def bulk_change_group():
    """Change group for multiple users at once."""
    user_ids = request.form.getlist('user_ids', type=int)
    action = request.form.get('action')  # 'add' or 'remove' or 'replace'
    group_id = request.form.get('group_id', type=int)

    if not user_ids:
        flash(_l('Aucun utilisateur selectionne'), 'warning')
        return redirect(url_for('admin.users'))

    if not group_id or action not in ('add', 'remove', 'replace'):
        flash(_l('Aucun groupe selectionne'), 'warning')
        return redirect(url_for('admin.users'))

    group = Group.query.get(group_id)
    if not group:
        flash(_l('Groupe non trouve'), 'error')
        return redirect(url_for('admin.users'))

    # Check group access
    if not current_user.can_access_group(group):
        flash(_l('Vous n\'avez pas acces a ce groupe'), 'error')
        return redirect(url_for('admin.users'))

    updated_count = 0
    skipped_count = 0
    managed_group_ids = current_user.get_managed_group_ids()  # None = all

    for user_id in user_ids:
        user = User.query.get(user_id)
        if not user:
            continue

        # Skip users we cannot see, ourselves, and peers or superiors
        if (user.id == current_user.id
                or not current_user.can_access_user(user)
                or (not current_user.is_superadmin and user.role_rank >= current_user.role_rank)):
            skipped_count += 1
            continue

        in_group = user.is_member_of_group(group.id)

        # Check group/tenant capacity
        if action in ['add', 'replace'] and not in_group and group.join_error(user):
            skipped_count += 1
            continue

        if action == 'add':
            if not in_group:
                user.add_to_group(group, 'member')
                updated_count += 1
        elif action == 'remove':
            if in_group:
                user.remove_from_group(group)
                updated_count += 1
        elif action == 'replace':
            # Leave only the groups we manage; memberships elsewhere are kept
            for g in user.groups.all():
                if g.id != group.id and (managed_group_ids is None or g.id in managed_group_ids):
                    user.remove_from_group(g)
            if not in_group:
                user.add_to_group(group, 'member')
            updated_count += 1

    db.session.commit()

    action_text = {'add': 'ajoute(s) au', 'remove': 'retire(s) du', 'replace': 'deplace(s) vers le'}.get(action, 'modifie(s) pour le')
    if updated_count > 0:
        flash(_l('%(count)s utilisateur(s) %(action)s groupe "%(group)s"', count=updated_count, action=action_text, group=group.name), 'success')
    if skipped_count > 0:
        flash(_l('%(count)s utilisateur(s) ignore(s)', count=skipped_count), 'warning')

    return redirect(url_for('admin.users'))
