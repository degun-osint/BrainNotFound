"""Admin scope: which tenants, groups, users and content the current admin sees.

Every admin list, dropdown and assignment goes through these helpers so that
the role rules and the navbar tenant context are applied the same way
everywhere.

Rules (without navbar context):
- superadmin: everything
- tenant admin: groups of their tenants (+ groups they admin directly)
- group admin: the groups they admin
Content (quizzes, interviews) is visible when it belongs to one of the
admin's tenants, is assigned to one of the scoped groups, or was created by
the admin. With a navbar context, everything is narrowed to that tenant.
"""
from flask import session
from flask_login import current_user

from app import db
from app.models import Group, Interview, Quiz, Tenant, User, tenant_admins, user_groups

TENANT_CONTEXT_KEY = 'admin_tenant_context'


# ==================== Tenants ====================

def get_tenant_context():
    """Tenant selected in the navbar, or None. Stale or unauthorized values are cleared."""
    tenant_id = session.get(TENANT_CONTEXT_KEY)
    if not tenant_id:
        return None
    tenant = db.session.get(Tenant, tenant_id)
    if not tenant or not current_user.is_admin_of_tenant(tenant.id):
        session.pop(TENANT_CONTEXT_KEY, None)
        return None
    return tenant


def set_tenant_context(tenant):
    if tenant is None:
        session.pop(TENANT_CONTEXT_KEY, None)
    else:
        session[TENANT_CONTEXT_KEY] = tenant.id


def get_accessible_tenants():
    """Active tenants the current user administers (all of them for a superadmin)."""
    if current_user.is_superadmin:
        query = Tenant.query.filter_by(is_active=True)
    else:
        query = current_user.admin_tenants.filter_by(is_active=True)
    return query.order_by(Tenant.name).all()


def _scoped_tenant_ids(ctx):
    """Tenant IDs content is attached to, or None for a superadmin without context."""
    if ctx:
        return [ctx.id]
    if current_user.is_superadmin:
        return None
    return sorted(current_user.admin_tenant_ids())


# ==================== Groups ====================

def _group_condition():
    """SQL condition on Group for the current scope, or None when unrestricted."""
    ctx = get_tenant_context()
    if ctx:
        return Group.tenant_id == ctx.id
    if current_user.is_superadmin:
        return None
    admin_group_ids = db.session.query(user_groups.c.group_id).filter(
        user_groups.c.user_id == current_user.id,
        user_groups.c.role == 'admin',
    )
    conditions = [Group.id.in_(admin_group_ids)]
    tenant_ids = _scoped_tenant_ids(None)
    if tenant_ids:
        conditions.append(Group.tenant_id.in_(tenant_ids))
    return db.or_(*conditions)


def scoped_groups(active_only=True):
    """Query of the groups in scope, ordered by name."""
    query = Group.query
    condition = _group_condition()
    if condition is not None:
        query = query.filter(condition)
    if active_only:
        query = query.filter(Group.is_active == True)  # noqa: E712
    return query.order_by(Group.name)


def scoped_group_ids():
    """Subquery of the IDs of all groups in scope (active or not)."""
    query = db.session.query(Group.id)
    condition = _group_condition()
    if condition is not None:
        query = query.filter(condition)
    return query


def validate_group_ids(raw_ids, active_only=True):
    """Keep only the groups from a submitted form that are in scope. Returns Group objects."""
    ids = {int(x) for x in raw_ids if str(x).strip().isdigit()}
    if not ids:
        return []
    return scoped_groups(active_only=active_only).filter(Group.id.in_(ids)).all()


def assign_groups(relationship, raw_ids):
    """Set an item's groups to the submitted ones, within scope.

    Groups outside the admin's scope (e.g. another tenant's group on a shared
    quiz) are left untouched instead of being silently removed.
    """
    in_scope = {g.id: g for g in scoped_groups(active_only=False)}
    selected = {g.id for g in validate_group_ids(raw_ids, active_only=False)}
    current = {g.id: g for g in relationship.all()}
    for gid, group in current.items():
        if gid in in_scope and gid not in selected:
            relationship.remove(group)
    for gid in selected - current.keys():
        relationship.append(in_scope[gid])


# ==================== Content (quizzes, interviews) ====================

def _content_condition(model):
    ctx = get_tenant_context()
    if ctx is None and current_user.is_superadmin:
        return None
    conditions = [model.groups.any(Group.id.in_(scoped_group_ids()))]
    tenant_ids = _scoped_tenant_ids(ctx)
    if tenant_ids:
        conditions.append(model.tenant_id.in_(tenant_ids))
    if ctx is None:
        conditions.append(model.created_by_id == current_user.id)
    return db.or_(*conditions)


def _scoped_content(model):
    query = model.query
    condition = _content_condition(model)
    if condition is not None:
        query = query.filter(condition)
    return query


def scoped_quizzes():
    return _scoped_content(Quiz)


def scoped_interviews():
    return _scoped_content(Interview)


def default_tenant_id(groups=()):
    """Tenant to attach new content to: navbar context, else the first group's tenant."""
    ctx = get_tenant_context()
    if ctx:
        return ctx.id
    for group in groups:
        if group.tenant_id:
            return group.tenant_id
    return None


# ==================== Users ====================

def scoped_user_ids():
    """Subquery of the IDs of members (any role) of the groups in scope."""
    return db.session.query(user_groups.c.user_id).filter(
        user_groups.c.group_id.in_(scoped_group_ids())
    )


def scoped_users():
    """Users in scope: members of scoped groups and admins of scoped tenants.

    Superadmin accounts are only listed to superadmins.
    """
    ctx = get_tenant_context()
    if ctx is None and current_user.is_superadmin:
        return User.query
    conditions = [User.id.in_(scoped_user_ids())]
    tenant_ids = _scoped_tenant_ids(ctx)
    if tenant_ids:
        conditions.append(User.id.in_(
            db.session.query(tenant_admins.c.user_id).filter(tenant_admins.c.tenant_id.in_(tenant_ids))
        ))
    if current_user.is_superadmin:
        conditions.append(User.is_admin == True)  # noqa: E712
    return User.query.filter(db.or_(*conditions))


def quota_tenant():
    """Tenant charged for an AI action not tied to existing content (e.g. quiz generation).

    Navbar context first; a superadmin without context is not charged.
    """
    ctx = get_tenant_context()
    if ctx or current_user.is_superadmin:
        return ctx
    tenant = current_user.admin_tenants.order_by(Tenant.name).first()
    if tenant:
        return tenant
    group = scoped_groups().filter(Group.tenant_id.isnot(None)).first()
    return group.tenant if group else None


CONTENT_STATUSES = ('active', 'inactive', 'no_group')


def filter_content_status(query, model, status):
    """Narrow a quiz or interview query to ?status= (active, inactive, no group)."""
    if status == 'active':
        return query.filter(model.is_active == True)  # noqa: E712
    if status == 'inactive':
        return query.filter(model.is_active == False)  # noqa: E712
    if status == 'no_group':
        return query.filter(~model.groups.any())
    return query


# ==================== Breadcrumb ====================

def breadcrumb(tenant=None, group=None, *extra):
    """[(label, url)] trail for admin detail pages: Organizations > Organization > Group > extra.

    Only links the viewer may open are kept as links; the last item is the current page.
    """
    from flask import url_for
    from flask_babel import gettext as _
    items = []
    if current_user.is_superadmin or len(current_user.admin_tenant_ids()) > 1:
        items.append((_('Etablissements'), url_for('tenant.list_tenants')))
    if tenant:
        can_open = current_user.is_superadmin or current_user.is_admin_of_tenant(tenant.id)
        items.append((tenant.name, url_for('tenant.view_tenant', identifier=tenant.get_url_identifier())
                      if can_open else None))
    elif group is not None or extra:
        items.append((_('Groupes'), url_for('admin.groups')))
    if group is not None:
        items.append((group.name, url_for('admin.group_detail', identifier=group.get_url_identifier())))
    items.extend(extra)
    return items


# ==================== Graders ====================

def grader_candidates():
    """Instructors and organization admins the current admin may name as quiz graders."""
    instructors = db.session.query(user_groups.c.user_id).filter(
        user_groups.c.role == 'admin', user_groups.c.group_id.in_(scoped_group_ids()))
    conditions = [User.id.in_(instructors)]
    tenant_ids = _scoped_tenant_ids(get_tenant_context())
    tenant_admin_ids = db.session.query(tenant_admins.c.user_id)
    if tenant_ids is None:
        conditions.append(User.id.in_(tenant_admin_ids))
    elif tenant_ids:
        conditions.append(User.id.in_(tenant_admin_ids.filter(tenant_admins.c.tenant_id.in_(tenant_ids))))
    return User.query.filter(db.or_(*conditions), User.is_admin == False).order_by(  # noqa: E712
        User.last_name, User.first_name, User.username).all()


def assign_graders(quiz, raw_ids):
    """Set the quiz graders to the submitted ones among our candidates.

    Graders we can't see (named by an admin of another scope) are kept.
    """
    candidates = {u.id: u for u in grader_candidates()}
    wanted = {int(x) for x in raw_ids if str(x).strip().isdigit()} & candidates.keys()
    for user in quiz.graders.all():
        if user.id in candidates and user.id not in wanted:
            quiz.graders.remove(user)
    current = {u.id for u in quiz.graders}
    for uid in wanted - current:
        quiz.graders.append(candidates[uid])
