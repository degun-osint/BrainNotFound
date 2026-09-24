from app import db
from datetime import datetime
from sqlalchemy import event
import secrets
from app.models.mixins import UIDMixin, init_uid_on_create

class Group(UIDMixin, db.Model):
    __tablename__ = 'groups'

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(100), unique=True, nullable=True, index=True)  # Coolname-based identifier
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    join_code = db.Column(db.String(20), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    max_members = db.Column(db.Integer, default=0)  # 0 = unlimited
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Tenant relationship (nullable for backward compatibility)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    @staticmethod
    def generate_join_code():
        """Generate a unique 8-character join code."""
        while True:
            code = secrets.token_urlsafe(6)[:8].upper()
            if not Group.query.filter_by(join_code=code).first():
                return code

    @staticmethod
    def member_counts(groups):
        """{group_id: member count} for several groups in a single query."""
        from app.models.user import user_groups
        ids = [g.id for g in groups]
        if not ids:
            return {}
        rows = db.session.query(user_groups.c.group_id, db.func.count(user_groups.c.user_id)).filter(
            user_groups.c.group_id.in_(ids)
        ).group_by(user_groups.c.group_id).all()
        return dict(rows)

    @staticmethod
    def names_by_user(user_ids):
        """{user_id: 'Group A, Group B'} for several users in a single query."""
        from app.models.user import user_groups
        if not user_ids:
            return {}
        rows = db.session.query(user_groups.c.user_id, Group.name).join(
            Group, Group.id == user_groups.c.group_id
        ).filter(user_groups.c.user_id.in_(list(user_ids))).order_by(Group.name).all()
        names = {}
        for user_id, name in rows:
            names.setdefault(user_id, []).append(name)
        return {uid: ', '.join(n) for uid, n in names.items()}

    def get_member_count(self):
        """Get the current number of members in this group."""
        from app.models.user import user_groups
        return db.session.query(user_groups).filter(
            user_groups.c.group_id == self.id
        ).count()

    def is_full(self):
        """Check if the group has reached its member limit."""
        if not self.max_members or self.max_members <= 0:
            return False  # Unlimited
        return self.get_member_count() >= self.max_members

    def available_spots(self):
        """Get the number of available spots (None if unlimited)."""
        if not self.max_members or self.max_members <= 0:
            return None  # Unlimited
        return max(0, self.max_members - self.get_member_count())

    def join_error(self, user=None):
        """Why a user (None = a new account) can't be added to this group, or None if they can.

        Checks the group itself and its tenant: subscription and user limit
        (someone already in the tenant doesn't count against the limit again).
        """
        from flask_babel import lazy_gettext as _l
        if not self.is_active:
            return _l('Code de groupe invalide ou inactif')
        if self.is_full():
            return _l('Ce groupe a atteint sa limite de membres')
        tenant = self.tenant
        if tenant:
            if not tenant.is_subscription_active():
                return _l("Cet etablissement n'accepte plus de nouvelles inscriptions")
            if (user is None or not tenant.has_member(user)) and not tenant.can_add_user():
                return _l("Cet etablissement n'accepte plus de nouvelles inscriptions")
        return None

    def get_url_identifier(self):
        """Get the URL identifier (uid)."""
        return self.uid if self.uid else str(self.id)

    def __repr__(self):
        return f'<Group {self.name}>'


# Register event listener for auto-generating UIDs
event.listen(Group, 'before_insert', init_uid_on_create)
