from app import db
from datetime import datetime
import secrets

class Group(db.Model):
    __tablename__ = 'groups'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    join_code = db.Column(db.String(20), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    max_members = db.Column(db.Integer, default=0)  # 0 = unlimited
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Tenant relationship (nullable for backward compatibility)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    # Relationships
    users = db.relationship('User', back_populates='group', lazy='dynamic')

    @staticmethod
    def generate_join_code():
        """Generate a unique 8-character join code."""
        while True:
            code = secrets.token_urlsafe(6)[:8].upper()
            if not Group.query.filter_by(join_code=code).first():
                return code

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

    def __repr__(self):
        return f'<Group {self.name}>'
