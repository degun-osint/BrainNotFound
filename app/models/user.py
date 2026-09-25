from app import db
from flask import has_request_context, request
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
from sqlalchemy import event
import secrets
from app.models.mixins import UIDMixin, init_uid_on_create

# Association table for User-Group many-to-many with role
user_groups = db.Table('user_groups',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('groups.id'), primary_key=True),
    db.Column('role', db.String(20), default='member'),  # 'member' or 'admin'
    db.Column('joined_at', db.DateTime, default=datetime.utcnow)
)


class User(UIDMixin, UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(100), unique=True, nullable=True, index=True)  # Coolname-based identifier
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)  # Superadmin flag
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Email verification fields
    email_verified = db.Column(db.Boolean, default=True)  # True par defaut pour utilisateurs existants
    verification_token = db.Column(db.String(100), unique=True, nullable=True)
    verification_token_expires = db.Column(db.DateTime, nullable=True)

    # Password reset fields
    reset_token = db.Column(db.String(100), unique=True, nullable=True)
    reset_token_expires = db.Column(db.DateTime, nullable=True)

    # Login tracking
    last_login = db.Column(db.DateTime, nullable=True)
    last_login_ip = db.Column(db.String(45), nullable=True)  # IPv6 can be up to 45 chars

    # Language preference for i18n
    language_preference = db.Column(db.String(5), nullable=True, default=None)

    # Relationships
    responses = db.relationship('QuizResponse', back_populates='user', lazy='dynamic',
                               cascade='all, delete-orphan', foreign_keys='QuizResponse.user_id')

    # New many-to-many relationship with groups
    groups = db.relationship('Group', secondary=user_groups,
                            backref=db.backref('members', lazy='dynamic'),
                            lazy='dynamic')

    @property
    def full_name(self):
        """Return full name or username if names not set."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}"
        elif self.first_name:
            return self.first_name
        elif self.last_name:
            return self.last_name
        return self.username

    @property
    def is_superadmin(self):
        """Check if user is a superadmin (full access)."""
        return self.is_admin

    # ==================== Per-request role cache ====================
    # Roles are checked dozens of times per admin page (decorators, context
    # processors, templates); memoize them for the duration of the request.

    def _cached(self, name, compute):
        if not has_request_context():
            return compute()
        cache = getattr(request, '_role_cache', None)
        if cache is None:
            cache = request._role_cache = {}
        key = (self.id, name)
        if key not in cache:
            cache[key] = compute()
        return cache[key]

    @staticmethod
    def clear_role_cache():
        """Call after changing group roles or tenant admins within a request."""
        if has_request_context():
            request._role_cache = {}

    def admin_tenant_ids(self):
        """IDs of the tenants this user administers."""
        from app.models.tenant import tenant_admins
        return self._cached('tenant_ids', lambda: {
            row[0] for row in db.session.query(tenant_admins.c.tenant_id).filter(tenant_admins.c.user_id == self.id)
        })

    def admin_group_ids(self):
        """IDs of the groups where this user has the admin role."""
        return self._cached('group_ids', lambda: {
            row[0] for row in db.session.query(user_groups.c.group_id).filter(
                user_groups.c.user_id == self.id, user_groups.c.role == 'admin')
        })

    @property
    def is_group_admin(self):
        """Check if user is admin of at least one group."""
        return bool(self.admin_group_ids())

    @property
    def is_tenant_admin(self):
        """Check if user is admin of at least one tenant."""
        return bool(self.admin_tenant_ids())

    @property
    def is_any_admin(self):
        """Check if user has any admin role (super, tenant, or group)."""
        return self.is_superadmin or self.is_tenant_admin or self.is_group_admin

    def get_admin_groups(self):
        """Get groups where user is admin."""
        from app.models.group import Group
        return Group.query.join(user_groups).filter(
            user_groups.c.user_id == self.id,
            user_groups.c.role == 'admin'
        )

    def get_accessible_groups(self):
        """Get all groups this admin can manage (for tenant admins includes tenant groups)."""
        from app.models.group import Group
        if self.is_superadmin:
            return Group.query.filter_by(is_active=True)
        if self.is_tenant_admin:
            # Tenant admins can access all groups in their tenants
            tenant_ids = list(self.admin_tenant_ids())
            return Group.query.filter(
                Group.is_active == True,
                Group.tenant_id.in_(tenant_ids)
            )
        # Group admins can only access their direct admin groups
        return self.get_admin_groups().filter(Group.is_active == True)

    def is_admin_of_tenant(self, tenant_id):
        """Check if user is admin of a specific tenant."""
        if self.is_superadmin:
            return True
        return tenant_id in self.admin_tenant_ids()

    def get_accessible_tenants(self):
        """Get tenants this user can access as admin."""
        from app.models.tenant import Tenant
        if self.is_superadmin:
            return Tenant.query.filter_by(is_active=True)
        return self.admin_tenants.filter_by(is_active=True)

    def get_member_groups(self):
        """Get groups where user is a member (for taking quizzes)."""
        from app.models.group import Group
        return Group.query.join(user_groups).filter(
            user_groups.c.user_id == self.id,
            user_groups.c.role == 'member'
        )

    def get_all_groups(self):
        """Get all groups user belongs to (any role)."""
        return self.groups

    def is_admin_of_group(self, group_id):
        """Check if user is admin of a specific group (includes tenant admins)."""
        from app.models.group import Group
        if self.is_superadmin:
            return True
        # Tenant admin can access groups in their tenants
        if self.is_tenant_admin:
            group = Group.query.get(group_id)
            if group and group.tenant_id:
                return self.is_admin_of_tenant(group.tenant_id)
        # Direct group admin
        return group_id in self.admin_group_ids()

    def is_member_of_group(self, group_id):
        """Check if user is member of a specific group."""
        return self.groups.filter_by(id=group_id).first() is not None

    def is_in_group(self, group):
        """Check if user is member of a group (accepts group object)."""
        return self.is_member_of_group(group.id)

    def can_access_user(self, target_user):
        """Check if this admin can access/manage a target user."""
        if self.is_superadmin:
            return True
        # Tenant admin can access users in their tenants
        if self.is_tenant_admin:
            admin_tenant_ids = self.admin_tenant_ids()
            # Get tenants of target user's groups
            target_tenant_ids = set(g.tenant_id for g in target_user.groups if g.tenant_id)
            if admin_tenant_ids & target_tenant_ids:
                return True
        # Group admin can access users in their admin groups
        target_group_ids = {g.id for g in target_user.groups}
        return bool(self.admin_group_ids() & target_group_ids)

    @property
    def role_rank(self):
        """Numeric rank of the user's highest role (3=super, 2=tenant, 1=group, 0=user)."""
        if self.is_superadmin:
            return 3
        if self.is_tenant_admin:
            return 2
        if self.is_group_admin:
            return 1
        return 0

    def get_managed_group_ids(self):
        """IDs of all groups (active or not) this admin controls. None = all groups."""
        from app.models.group import Group
        if self.is_superadmin:
            return None
        def compute():
            ids = set(self.admin_group_ids())
            if self.is_tenant_admin:
                ids |= {row[0] for row in db.session.query(Group.id).filter(
                    Group.tenant_id.in_(self.admin_tenant_ids()))}
            return ids
        return self._cached('managed_group_ids', compute)

    def can_manage_user(self, target_user, for_delete=False):
        """Check if this admin can modify (or delete) a target user: write access.

        Stricter than can_access_user (read access). The target must have a
        lower role, and:
        - edit: share at least one group managed by this admin, with all of
          its groups inside this admin's organizations (an instructor edits
          their learner even if a colleague also has them; an account that
          belongs to another organization is left to that organization);
        - delete: every group of the target must be managed by this admin,
          since deleting erases the target's results everywhere.
        """
        return self.can_manage(target_user.id, target_user.role_rank,
                               [(g.id, g.tenant_id) for g in target_user.groups], for_delete)

    def can_manage(self, target_id, target_rank, target_groups, for_delete=False):
        """can_manage_user from precomputed data; target_groups = [(group_id, tenant_id)]."""
        if target_id == self.id:
            return False
        if self.is_superadmin:
            return True
        if target_rank >= self.role_rank:
            return False
        target_groups = list(target_groups)
        group_ids = {gid for gid, _ in target_groups}
        if not group_ids:
            return False
        managed = self.get_managed_group_ids()
        if group_ids <= managed:
            return True
        if for_delete or not group_ids & managed:
            return False
        own_tenants = self.managed_tenant_ids()
        return all(tid is not None and tid in own_tenants for _, tid in target_groups)

    def managed_tenant_ids(self):
        """Organizations of the groups this admin manages (plus the ones they administer)."""
        from app.models.group import Group

        def compute():
            ids = set(self.admin_tenant_ids())
            managed = self.get_managed_group_ids()
            if managed:
                ids |= {row[0] for row in db.session.query(Group.tenant_id).filter(
                    Group.id.in_(managed), Group.tenant_id.isnot(None)).distinct()}
            return ids
        return self._cached('managed_tenant_ids', compute)

    def _can_access_content(self, item):
        """Shared access rule for quizzes and interviews (anything with tenant_id, groups, created_by_id)."""
        if self.is_superadmin:
            return True
        if item.created_by_id == self.id:
            return True
        item_groups = item.groups.all()
        # Tenant admin: content of their tenants OR assigned to one of their tenants' groups
        if self.is_tenant_admin:
            admin_tenant_ids = self.admin_tenant_ids()
            if item.tenant_id and item.tenant_id in admin_tenant_ids:
                return True
            if admin_tenant_ids & set(g.tenant_id for g in item_groups if g.tenant_id):
                return True
        # Group admin: only content explicitly assigned to their groups
        return bool(self.admin_group_ids() & {g.id for g in item_groups})

    def can_access_quiz(self, quiz):
        """Check if this admin can access/manage a quiz."""
        return self._can_access_content(quiz)

    def is_grader_of(self, quiz):
        """Author or designated grader of the quiz: sees and grades all its papers."""
        return self.id in quiz.grader_ids()

    def can_grade_quiz(self, quiz):
        """Results, score edits, validation, contests of a quiz."""
        return self.is_grader_of(quiz) or self.can_access_quiz(quiz)

    def can_access_interview(self, interview):
        """Check if this admin can access/manage an interview and its sessions."""
        return self._can_access_content(interview)

    def can_access_group(self, group):
        """Check if this admin can access/manage a group."""
        if self.is_superadmin:
            return True
        # Tenant admin can access groups in their tenants
        if self.is_tenant_admin and group.tenant_id:
            if self.is_admin_of_tenant(group.tenant_id):
                return True
        # Group admin can access their own groups
        return self.is_admin_of_group(group.id)

    def add_to_group(self, group, role='member'):
        """Add user to a group with specified role."""
        if not self.is_member_of_group(group.id):
            stmt = user_groups.insert().values(
                user_id=self.id,
                group_id=group.id,
                role=role
            )
            db.session.execute(stmt)
            User.clear_role_cache()

    def remove_from_group(self, group):
        """Remove user from a group."""
        stmt = user_groups.delete().where(
            user_groups.c.user_id == self.id,
            user_groups.c.group_id == group.id
        )
        db.session.execute(stmt)
        User.clear_role_cache()

    def get_role_in_group(self, group_id):
        """Get user's role in a specific group."""
        result = db.session.execute(
            user_groups.select().where(
                user_groups.c.user_id == self.id,
                user_groups.c.group_id == group_id
            )
        ).first()
        return result.role if result else None

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_verification_token(self):
        """Generate email verification token valid for 24 hours."""
        self.verification_token = secrets.token_urlsafe(32)
        self.verification_token_expires = datetime.utcnow() + timedelta(hours=24)
        return self.verification_token

    def generate_reset_token(self, hours=1):
        """Generate password reset token (1 hour by default, longer when sent by an admin)."""
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=hours)
        return self.reset_token

    def clear_verification_token(self):
        """Clear verification token after successful verification."""
        self.verification_token = None
        self.verification_token_expires = None

    def clear_reset_token(self):
        """Clear reset token after successful password reset."""
        self.reset_token = None
        self.reset_token_expires = None

    @staticmethod
    def verify_email_token(token):
        """Find user by verification token and check if valid."""
        user = User.query.filter_by(verification_token=token).first()
        if user and user.verification_token_expires and user.verification_token_expires > datetime.utcnow():
            return user
        return None

    @staticmethod
    def verify_reset_token(token):
        """Find user by reset token and check if valid."""
        user = User.query.filter_by(reset_token=token).first()
        if user and user.reset_token_expires and user.reset_token_expires > datetime.utcnow():
            return user
        return None

    def record_login(self, ip_address):
        """Record login timestamp and IP address."""
        self.last_login = datetime.utcnow()
        self.last_login_ip = ip_address

    def get_id(self):
        """Session identifier: id bound to the random uid.

        A backup restore rewinds MySQL auto-increments, so a numeric id alone
        could later point to a different person; the uid can't be reused.
        """
        return f'{self.id}:{self.uid}' if self.uid else str(self.id)

    @staticmethod
    def load_from_session_id(session_id):
        """Inverse of get_id(): the user, or None if the id no longer matches."""
        user_id, _, uid = str(session_id).partition(':')
        if not user_id.isdigit():
            return None
        user = db.session.get(User, int(user_id))
        if user is None or (user.uid or '') != uid:
            return None
        return user

    def get_url_identifier(self):
        """Get the URL identifier (uid or username as fallback)."""
        return self.uid if self.uid else self.username

    def __repr__(self):
        return f'<User {self.username}>'


# Register event listener for auto-generating UIDs
event.listen(User, 'before_insert', init_uid_on_create)
