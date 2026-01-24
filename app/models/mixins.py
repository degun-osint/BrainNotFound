"""Model mixins for common functionality."""
from coolname import generate_slug
from app import db


class UIDMixin:
    """Mixin to add coolname-based UID to models.

    Provides:
    - uid: A unique, URL-friendly identifier (e.g., 'brave-purple-tiger')
    - generate_uid(): Class method to create unique UIDs
    - get_by_identifier(): Class method to find records by uid, slug, or numeric id
    - get_url_identifier(): Instance method returning the preferred URL identifier
    """

    # Note: The uid column is defined here but models using this mixin
    # should declare it explicitly to ensure proper SQLAlchemy mapping:
    # uid = db.Column(db.String(100), unique=True, nullable=False, index=True)

    @classmethod
    def generate_uid(cls):
        """Generate a unique coolname-based UID.

        Tries up to 100 times to generate a unique 3-word coolname.
        Falls back to adding a numeric suffix if collisions persist.

        Returns:
            str: A unique UID like 'brave-purple-tiger'
        """
        for attempt in range(100):
            uid = generate_slug(3)

            # Check if already exists
            if not cls.query.filter_by(uid=uid).first():
                return uid

        # Fallback: add numeric suffix
        import uuid
        base = generate_slug(3)
        return f"{base}-{uuid.uuid4().hex[:6]}"

    @classmethod
    def get_by_identifier(cls, identifier):
        """Get record by UID, slug (if model has it), or numeric ID.

        Search order:
        1. By uid (most common after migration)
        2. By slug (if model has slug field)
        3. By numeric id (backward compatibility)

        Args:
            identifier: A uid string, slug string, or numeric id (as string or int)

        Returns:
            Model instance or None if not found
        """
        if not identifier:
            return None

        identifier_str = str(identifier)

        # Try UID first (most common case after migration)
        record = cls.query.filter_by(uid=identifier_str).first()
        if record:
            return record

        # Try slug if model has it
        if hasattr(cls, 'slug'):
            record = cls.query.filter(cls.slug == identifier_str).first()
            if record:
                return record

        # Try numeric ID (backward compatibility)
        try:
            record_id = int(identifier_str)
            return cls.query.get(record_id)
        except (ValueError, TypeError):
            return None

    def get_url_identifier(self):
        """Get the preferred identifier for URLs.

        For models with optional user-defined slugs, prefer slug over uid.
        Otherwise, return the uid.

        Returns:
            str: The preferred URL identifier
        """
        # If model has a slug and it's set, prefer it
        if hasattr(self, 'slug') and self.slug:
            return self.slug
        return self.uid


def init_uid_on_create(mapper, connection, target):
    """SQLAlchemy event listener to auto-generate UID on insert.

    Usage:
        from sqlalchemy import event
        event.listen(MyModel, 'before_insert', init_uid_on_create)

    Args:
        mapper: SQLAlchemy mapper (unused)
        connection: Database connection (unused)
        target: Model instance being inserted
    """
    if hasattr(target, 'uid') and target.uid is None:
        target.uid = target.__class__.generate_uid()
