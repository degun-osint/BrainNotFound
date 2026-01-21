from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import secrets

# Association table for User-Group many-to-many with role
user_groups = db.Table('user_groups',
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('groups.id'), primary_key=True),
    db.Column('role', db.String(20), default='member'),  # 'member' or 'admin'
    db.Column('joined_at', db.DateTime, default=datetime.utcnow)
)


class User(UserMixin, db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)  # Superadmin flag
    # Legacy field - kept for backward compatibility during migration
    group_id = db.Column(db.Integer, db.ForeignKey('groups.id'), nullable=True)
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

    # Relationships
    group = db.relationship('Group', back_populates='users', foreign_keys=[group_id])  # Legacy
    responses = db.relationship('QuizResponse', back_populates='user', lazy='dynamic',
                               cascade='all, delete-orphan')

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

    @property
    def is_group_admin(self):
        """Check if user is admin of at least one group."""
        return self.get_admin_groups().count() > 0

    @property
    def is_tenant_admin(self):
        """Check if user is admin of at least one tenant."""
        return self.admin_tenants.count() > 0

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

    def is_admin_of_tenant(self, tenant_id):
        """Check if user is admin of a specific tenant."""
        if self.is_superadmin:
            return True
        return self.admin_tenants.filter_by(id=tenant_id).first() is not None

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
        """Check if user is admin of a specific group."""
        if self.is_superadmin:
            return True
        return self.get_admin_groups().filter_by(id=group_id).first() is not None

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
            admin_tenant_ids = set(t.id for t in self.admin_tenants)
            # Get tenants of target user's groups
            target_tenant_ids = set(g.tenant_id for g in target_user.groups if g.tenant_id)
            if admin_tenant_ids & target_tenant_ids:
                return True
        # Group admin can access users in their admin groups
        admin_group_ids = [g.id for g in self.get_admin_groups()]
        target_group_ids = [g.id for g in target_user.groups]
        return bool(set(admin_group_ids) & set(target_group_ids))

    def can_access_quiz(self, quiz):
        """Check if this admin can access/manage a quiz."""
        if self.is_superadmin:
            return True
        # Tenant admin can access quizzes in their tenants
        if self.is_tenant_admin and quiz.tenant_id:
            if self.is_admin_of_tenant(quiz.tenant_id):
                return True
        # Group admin can ONLY access quizzes explicitly assigned to their groups
        admin_group_ids = set(g.id for g in self.get_admin_groups())
        quiz_group_ids = set(g.id for g in quiz.groups)
        # Can access only if quiz is in one of admin's groups
        return bool(admin_group_ids & quiz_group_ids)

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

    def remove_from_group(self, group):
        """Remove user from a group."""
        stmt = user_groups.delete().where(
            user_groups.c.user_id == self.id,
            user_groups.c.group_id == group.id
        )
        db.session.execute(stmt)

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

    def generate_reset_token(self):
        """Generate password reset token valid for 1 hour."""
        self.reset_token = secrets.token_urlsafe(32)
        self.reset_token_expires = datetime.utcnow() + timedelta(hours=1)
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

    def __repr__(self):
        return f'<User {self.username}>'
