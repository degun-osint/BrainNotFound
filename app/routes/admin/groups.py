"""Groups: list, creation, group page (members, roles, join code), exports, emails."""
from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_required, current_user
from flask_babel import lazy_gettext as _l
from app import db
from app.models.user import User, user_groups
from app.models.group import Group
from app.models.quiz import Quiz, QuizResponse, quiz_groups
from app.models.tenant import Tenant
from app.models.interview import Interview
from app.utils.scope import scoped_groups, scoped_users, breadcrumb
from datetime import datetime
from app.routes.admin import admin_bp
from app.routes.admin.common import admin_required, sanitize_filename


# Group management routes - Superadmin and Tenant Admin
@admin_bp.route('/groups')
@login_required
@admin_required
def groups():
    search = request.args.get('search', '', type=str).strip()
    status = request.args.get('status', '')
    query = scoped_groups(active_only=False)
    if search:
        query = query.filter(db.or_(Group.name.ilike(f'%{search}%'), Group.join_code.ilike(f'%{search}%')))
    if status == 'active':
        query = query.filter(Group.is_active == True)  # noqa: E712
    elif status == 'inactive':
        query = query.filter(Group.is_active == False)  # noqa: E712
    else:
        status = ''
    all_groups = query.all()
    learner_counts, instructor_counts = Group.role_counts(all_groups)
    return render_template('admin/groups.html', groups=all_groups, search=search, status=status,
                           learner_counts=learner_counts, instructor_counts=instructor_counts)


@admin_bp.route('/group/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_group():
    # Get available tenants for the current user
    if current_user.is_superadmin:
        tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.name).all()
    elif current_user.is_tenant_admin:
        tenants = list(current_user.admin_tenants.filter_by(is_active=True))
    else:
        # Group admins cannot create groups
        flash(_l('Vous n\'avez pas la permission de creer des groupes'), 'error')
        return redirect(url_for('admin.groups'))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description', '')
        max_members = request.form.get('max_members', 0, type=int)
        tenant_id = request.form.get('tenant_id', type=int)

        if not name:
            flash(_l('Le nom du groupe est requis'), 'error')
            return render_template('admin/create_group.html', tenants=tenants)

        # Every group belongs to one of the organizations we administer
        tenant = next((t for t in tenants if t.id == tenant_id), None)
        if not tenant:
            flash(_l('Choisissez un etablissement pour ce groupe'), 'error')
            return render_template('admin/create_group.html', tenants=tenants)
        if not tenant.can_add_group():
            flash(_l('Limite de groupes atteinte (%(max)s)', max=tenant.max_groups), 'error')
            return render_template('admin/create_group.html', tenants=tenants)

        # Generate unique join code
        join_code = Group.generate_join_code()

        group = Group(
            name=name,
            description=description,
            join_code=join_code,
            is_active=True,
            max_members=max(0, max_members),
            tenant_id=tenant_id
        )

        db.session.add(group)
        db.session.commit()

        flash(_l('Groupe "%(name)s" cree avec le code : %(code)s', name=name, code=join_code), 'success')
        return redirect(url_for('admin.group_detail', identifier=group.get_url_identifier()))

    # ?tenant=<uid>: coming from an organization page
    wanted = Tenant.get_by_identifier(request.args.get('tenant', '')) if request.args.get('tenant') else None
    selected_tenant_id = wanted.id if wanted and wanted in tenants else None
    return render_template('admin/create_group.html', tenants=tenants, selected_tenant_id=selected_tenant_id)


@admin_bp.route('/group/<identifier>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_group(identifier):
    group = Group.get_by_identifier(identifier)
    if not group:
        flash(_l('Groupe introuvable'), 'error')
        return redirect(url_for('admin.groups'))

    # Check permission
    if not current_user.can_access_group(group):
        flash(_l('Vous n\'avez pas acces a ce groupe'), 'error')
        return redirect(url_for('admin.groups'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != group.get_url_identifier():
        return redirect(url_for('admin.edit_group', identifier=group.get_url_identifier()), code=301)

    # Get available tenants for the current user
    if current_user.is_superadmin:
        tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.name).all()
    else:
        tenants = list(current_user.admin_tenants.filter_by(is_active=True))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        tenant_id = request.form.get('tenant_id', type=int)

        if not name:
            flash(_l('Le nom du groupe est requis'), 'error')
            return render_template('admin/edit_group.html', group=group, tenants=tenants,
                                   breadcrumb=breadcrumb(group.tenant, group, (_l('Modifier'), None)))

        # Moving a group is limited to the tenants we administer
        if tenant_id and tenant_id != group.tenant_id and tenant_id not in {t.id for t in tenants}:
            flash(_l('Acces non autorise a cet etablissement'), 'error')
            return render_template('admin/edit_group.html', group=group, tenants=tenants,
                                   breadcrumb=breadcrumb(group.tenant, group, (_l('Modifier'), None)))
        if tenant_id and tenant_id != group.tenant_id and not db.session.get(Tenant, tenant_id).can_add_group():
            flash(_l('Limite de groupes atteinte (%(max)s)', max=db.session.get(Tenant, tenant_id).max_groups), 'error')
            return render_template('admin/edit_group.html', group=group, tenants=tenants,
                                   breadcrumb=breadcrumb(group.tenant, group, (_l('Modifier'), None)))

        group.name = name
        group.description = request.form.get('description', '')
        max_members = request.form.get('max_members', 0, type=int)
        group.max_members = max(0, max_members)
        if tenant_id:
            group.tenant_id = tenant_id
        db.session.commit()

        flash(_l('Groupe mis a jour avec succes'), 'success')
        return redirect(url_for('admin.groups'))

    return render_template('admin/edit_group.html', group=group, tenants=tenants,
                                   breadcrumb=breadcrumb(group.tenant, group, (_l('Modifier'), None)))


@admin_bp.route('/group/<identifier>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_group(identifier):
    group = Group.get_by_identifier(identifier)
    if not group:
        flash(_l('Groupe introuvable'), 'error')
        return redirect(url_for('admin.groups'))

    # Check permission
    if not current_user.can_access_group(group):
        flash(_l('Vous n\'avez pas acces a ce groupe'), 'error')
        return redirect(url_for('admin.groups'))

    group.is_active = not group.is_active
    db.session.commit()

    status = 'activé' if group.is_active else 'désactivé'
    flash(_l('Groupe %(status)s', status=status), 'success')
    return redirect(url_for('admin.groups'))


@admin_bp.route('/group/<identifier>/delete', methods=['POST'])
@login_required
@admin_required
def delete_group(identifier):
    group = Group.get_by_identifier(identifier)
    if not group:
        flash(_l('Groupe introuvable'), 'error')
        return redirect(url_for('admin.groups'))

    # Check permission
    if not current_user.can_access_group(group):
        flash(_l('Vous n\'avez pas acces a ce groupe'), 'error')
        return redirect(url_for('admin.groups'))

    # Check if group has users (via new relationship)
    if group.members.count() > 0:
        flash(_l('Impossible de supprimer un groupe qui contient des utilisateurs'), 'error')
        return redirect(url_for('admin.groups'))

    db.session.delete(group)
    db.session.commit()

    flash(_l('Groupe supprime avec succes'), 'success')
    return redirect(url_for('admin.groups'))


def _group_or_redirect(identifier):
    """(group, None) if the current admin can manage it, else (None, redirect response)."""
    group = Group.get_by_identifier(identifier)
    if not group:
        flash(_l('Groupe introuvable'), 'error')
        return None, redirect(url_for('admin.groups'))
    if not current_user.can_access_group(group):
        flash(_l('Vous n\'avez pas acces a ce groupe'), 'error')
        return None, redirect(url_for('admin.groups'))
    return group, None


def _can_change_membership(target):
    """Instructors add/remove learners; organization admins also manage instructors."""
    return target.id != current_user.id and (
        current_user.is_superadmin or target.role_rank < current_user.role_rank)


@admin_bp.route('/group/<identifier>')
@login_required
@admin_required
def group_detail(identifier):
    """Everything about one group: learners, instructors, content, join code."""
    group, error = _group_or_redirect(identifier)
    if error:
        return error
    if identifier != group.get_url_identifier():
        return redirect(url_for('admin.group_detail', identifier=group.get_url_identifier()), code=301)

    rows = db.session.query(User, user_groups.c.role, user_groups.c.joined_at).join(
        user_groups, user_groups.c.user_id == User.id
    ).filter(user_groups.c.group_id == group.id).order_by(User.last_name, User.first_name, User.username).all()
    member_ids = [u.id for u, _, _ in rows]
    learners = [(u, joined) for u, role, joined in rows if role != 'admin']
    instructors = [(u, joined) for u, role, joined in rows if role == 'admin']

    response_counts = dict(db.session.query(QuizResponse.user_id, db.func.count(QuizResponse.id)).filter(
        QuizResponse.user_id.in_(member_ids)
    ).group_by(QuizResponse.user_id).all()) if member_ids else {}

    quizzes = group.quizzes.order_by(Quiz.created_at.desc()).all()
    interviews = group.interviews.order_by(Interview.created_at.desc()).all()
    learner_ids = [u.id for u, _ in learners]
    # How many learners of this group answered each quiz
    quiz_done = dict(db.session.query(QuizResponse.quiz_id, db.func.count(db.distinct(QuizResponse.user_id))).filter(
        QuizResponse.quiz_id.in_([q.id for q in quizzes]), QuizResponse.user_id.in_(learner_ids)
    ).group_by(QuizResponse.quiz_id).all()) if quizzes and learner_ids else {}

    manageable = {u.id: current_user.can_manage_user(u) for u, _, _ in rows}
    return render_template('admin/group_detail.html', breadcrumb=breadcrumb(group.tenant, group), group=group, learners=learners, instructors=instructors,
                           response_counts=response_counts, quizzes=quizzes, interviews=interviews,
                           quiz_done=quiz_done, manageable=manageable,
                           can_manage_roles=current_user.role_rank >= 2,
                           invite_url=url_for('auth.register', code=group.join_code, _external=True))


@admin_bp.route('/group/<identifier>/users')
@login_required
@admin_required
def group_users(identifier):
    """Former members page, now part of the group page."""
    return redirect(url_for('admin.group_detail', identifier=identifier), code=301)


@admin_bp.route('/group/<identifier>/candidates')
@login_required
@admin_required
def group_candidates(identifier):
    """Users in the admin's scope matching ?q=, not yet in the group (for the add box)."""
    group, error = _group_or_redirect(identifier)
    if error:
        return jsonify([]), 403
    q = request.args.get('q', '').strip()
    if len(q) < 2:
        return jsonify([])
    in_group = db.session.query(user_groups.c.user_id).filter(user_groups.c.group_id == group.id)
    pattern = f'%{q}%'
    users = scoped_users().filter(
        ~User.id.in_(in_group),
        User.is_admin == False,  # noqa: E712
        db.or_(User.username.ilike(pattern), User.email.ilike(pattern),
               User.first_name.ilike(pattern), User.last_name.ilike(pattern))
    ).order_by(User.last_name, User.username).limit(15).all()
    return jsonify([{'id': u.get_url_identifier(), 'name': u.full_name, 'username': u.username, 'email': u.email}
                    for u in users if u.role_rank < 2])


@admin_bp.route('/group/<identifier>/members/add', methods=['POST'])
@login_required
@admin_required
def group_add_member(identifier):
    group, error = _group_or_redirect(identifier)
    if error:
        return error
    user = User.get_by_identifier(request.form.get('user', ''))
    if (not user or not current_user.can_access_user(user) or user.role_rank >= 2
            or not _can_change_membership(user)):
        flash(_l('Vous n\'avez pas acces a cet utilisateur'), 'error')
    elif user.is_member_of_group(group.id):
        flash(_l('%(name)s fait deja partie du groupe', name=user.full_name), 'info')
    elif group.join_error(user):
        flash(group.join_error(user), 'error')
    else:
        user.add_to_group(group, 'member')
        db.session.commit()
        flash(_l('%(name)s ajoute au groupe', name=user.full_name), 'success')
    return redirect(url_for('admin.group_detail', identifier=group.get_url_identifier()))


@admin_bp.route('/group/<identifier>/members/<user_identifier>/remove', methods=['POST'])
@login_required
@admin_required
def group_remove_member(identifier, user_identifier):
    group, error = _group_or_redirect(identifier)
    if error:
        return error
    user = User.get_by_identifier(user_identifier)
    if not user or not user.is_member_of_group(group.id) or not _can_change_membership(user):
        flash(_l('Vous n\'avez pas acces a cet utilisateur'), 'error')
    else:
        user.remove_from_group(group)
        db.session.commit()
        flash(_l('%(name)s retire du groupe', name=user.full_name), 'success')
    return redirect(url_for('admin.group_detail', identifier=group.get_url_identifier()))


@admin_bp.route('/group/<identifier>/members/<user_identifier>/role', methods=['POST'])
@login_required
@admin_required
def group_set_role(identifier, user_identifier):
    """Make a member instructor of this group, or back to learner (organization admins only)."""
    group, error = _group_or_redirect(identifier)
    if error:
        return error
    user = User.get_by_identifier(user_identifier)
    role = request.form.get('role')
    if (role not in ('admin', 'member') or current_user.role_rank < 2 or not user
            or not user.is_member_of_group(group.id) or not _can_change_membership(user)):
        flash(_l('Vous n\'avez pas acces a cet utilisateur'), 'error')
    else:
        db.session.execute(user_groups.update().where(
            user_groups.c.user_id == user.id, user_groups.c.group_id == group.id
        ).values(role=role))
        db.session.commit()
        User.clear_role_cache()
        flash(_l('Role mis a jour pour %(name)s', name=user.full_name), 'success')
    return redirect(url_for('admin.group_detail', identifier=group.get_url_identifier()))


@admin_bp.route('/group/<identifier>/regenerate-code', methods=['POST'])
@login_required
@admin_required
def group_regenerate_code(identifier):
    """New join code: the old code and invitation link stop working."""
    group, error = _group_or_redirect(identifier)
    if error:
        return error
    code = group.regenerate_join_code()
    db.session.commit()
    flash(_l('Nouveau code d\'acces : %(code)s. L\'ancien code et l\'ancien lien ne fonctionnent plus.', code=code),
          'success')
    return redirect(url_for('admin.group_detail', identifier=group.get_url_identifier()))


@admin_bp.route('/group/<identifier>/export-results')
@login_required
@admin_required
def export_group_results(identifier):
    """Export quiz results for all users in a group as CSV."""
    import csv
    from io import StringIO
    from flask import Response

    group = Group.get_by_identifier(identifier)
    if not group:
        flash(_l('Groupe introuvable'), 'error')
        return redirect(url_for('admin.groups'))

    group_id = group.id  # Keep for queries

    # Check permission
    if not current_user.is_superadmin and not current_user.is_admin_of_group(group_id):
        flash(_l('Vous n\'avez pas acces a ce groupe'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Get all users in the group
    users = User.query.join(user_groups).filter(
        user_groups.c.group_id == group_id
    ).order_by(User.username).all()

    # Get quizzes available to this group
    group_quizzes = group.quizzes.order_by(Quiz.created_at).all()

    # If no specific quizzes assigned, get all quizzes with no group restriction
    if not group_quizzes:
        group_quizzes = Quiz.query.outerjoin(quiz_groups).filter(
            quiz_groups.c.quiz_id == None
        ).order_by(Quiz.created_at).all()

    # Build CSV
    output = StringIO()
    writer = csv.writer(output, delimiter=';')

    # Header row
    header = ['Utilisateur', 'Email']
    for quiz in group_quizzes:
        header.append(f'{quiz.title} (%)')
    header.append('Moyenne (%)')
    writer.writerow(header)

    # Data rows
    for user in users:
        row = [user.username, user.email or '']
        scores = []
        max_scores = []

        for quiz in group_quizzes:
            # Get user's response for this quiz (exclude test responses)
            # Handle both is_test=False and is_test=NULL (old responses)
            response = QuizResponse.query.filter(
                QuizResponse.user_id == user.id,
                QuizResponse.quiz_id == quiz.id,
                db.or_(QuizResponse.is_test == False, QuizResponse.is_test == None)
            ).first()

            if response and response.grading_status == 'completed':
                score = response.total_score
                max_score = response.max_score
                if max_score > 0:
                    percentage = (score / max_score) * 100
                    row.append(f'{percentage:.1f}')
                    scores.append(score)
                    max_scores.append(max_score)
                else:
                    row.append('-')
            elif response:
                row.append('En cours')
            else:
                row.append('Non fait')

        # Calculate average
        if scores and sum(max_scores) > 0:
            avg_percentage = (sum(scores) / sum(max_scores)) * 100
            row.append(f'{avg_percentage:.1f}%')
        else:
            row.append('-')

        writer.writerow(row)

    # Create response with UTF-8 BOM for Excel compatibility
    output.seek(0)
    filename = f'resultats_{sanitize_filename(group.name[:30])}_{datetime.utcnow().strftime("%Y%m%d")}.csv'

    # Add UTF-8 BOM for Excel to recognize encoding
    csv_content = '\ufeff' + output.getvalue()

    return Response(
        csv_content.encode('utf-8'),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@admin_bp.route('/group/<identifier>/email', methods=['GET', 'POST'])
@login_required
@admin_required
def email_group(identifier):
    """Send bulk email to all members of a group."""
    from app.utils.email_sender import send_bulk_email

    group = Group.get_by_identifier(identifier)
    if not group:
        flash(_l('Groupe introuvable'), 'error')
        return redirect(url_for('admin.groups'))

    group_id = group.id  # Keep for queries

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != group.get_url_identifier():
        return redirect(url_for('admin.email_group', identifier=group.get_url_identifier()), code=301)

    # Check permission
    if not current_user.is_superadmin and not current_user.is_admin_of_group(group_id):
        flash(_l('Vous n\'avez pas acces a ce groupe'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Get all users in the group with email
    users = User.query.join(user_groups).filter(
        user_groups.c.group_id == group_id,
        User.email.isnot(None),
        User.email != ''
    ).all()

    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()

        if not subject or not message:
            flash(_l('Le sujet et le message sont requis'), 'error')
            return render_template('admin/email_group.html', group=group, users=users)

        if not users:
            flash(_l('Aucun utilisateur avec email dans ce groupe'), 'error')
            return render_template('admin/email_group.html', group=group, users=users)

        success, fail = send_bulk_email(users, subject, message)

        if success > 0:
            flash(_l('%(count)s email(s) envoye(s) avec succes', count=success), 'success')
        if fail > 0:
            flash(_l('%(count)s email(s) echoue(s)', count=fail), 'warning')

        return redirect(url_for('admin.group_detail', identifier=group.get_url_identifier()))

    return render_template('admin/email_group.html', group=group, users=users)
