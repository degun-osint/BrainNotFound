#!/bin/bash
set -e

export FLASK_APP=wsgi:app

# Initialize migrations if not already done
if [ ! -d "migrations" ]; then
    echo "Initializing Flask-Migrate..."
    flask db init
fi

# Generate migration if there are changes (ignore errors if no changes)
echo "Checking for database schema changes..."
flask db migrate -m "Auto migration" 2>/dev/null || echo "No new migrations needed"

# Apply migrations (with fallback to reset if revision mismatch)
echo "Applying database migrations..."
if ! flask db upgrade 2>&1; then
    echo "Migration failed, attempting to fix revision mismatch..."
    # Reset alembic_version and stamp to head
    python -c "
from wsgi import app
from app import db
with app.app_context():
    try:
        db.session.execute(db.text('DROP TABLE IF EXISTS alembic_version'))
        db.session.commit()
        print('Dropped alembic_version table')
    except Exception as e:
        print(f'Could not drop alembic_version: {e}')
"
    # Re-init and stamp
    rm -rf migrations
    flask db init
    flask db migrate -m "Initial migration"
    flask db upgrade
fi

# Initialize seed data (admin user, default group, default pages)
echo "Initializing seed data..."
python -c "
import os
from wsgi import app
from app import db
from app.models.user import User, user_groups
from app.models.group import Group
from app.models.page import Page

with app.app_context():
    # Create default group if not exists
    default_group = Group.query.filter_by(name='Groupe par défaut').first()
    if not default_group:
        default_group = Group(
            name='Groupe par défaut',
            description='Groupe de démonstration créé automatiquement',
            join_code='DEMO2024',
            is_active=True
        )
        db.session.add(default_group)
        db.session.commit()
        print(f'Default group created: {default_group.name} with code {default_group.join_code}')

    # Create default admin if not exists
    admin = User.query.filter_by(username='admin').first()
    if not admin:
        default_password = os.environ.get('ADMIN_DEFAULT_PASSWORD', 'admin123')
        admin = User(username='admin', email='admin@quiz.com', is_admin=True)
        admin.set_password(default_password)
        db.session.add(admin)
        db.session.commit()
        print(f'Default admin created: admin/{default_password}')

    # Create default pages if not exists (load from private/ or private.example/)
    from app.utils.prompt_loader import read_seed_data, is_using_fallback

    # Default pages configuration: (slug, title, filename, location, order)
    default_pages = [
        ('a-propos', 'A propos', 'a-propos.md', 'footer', 1),
        ('mentions-legales', 'Mentions legales & Confidentialite', 'mentions-legales.md', 'footer', 2),
    ]

    for slug, title, filename, location, order in default_pages:
        existing = Page.query.filter_by(slug=slug).first()
        if not existing:
            content = read_seed_data(filename)
            if content:
                page = Page(
                    title=title,
                    slug=slug,
                    content=content,
                    location=location,
                    display_order=order,
                    is_published=True
                )
                db.session.add(page)
                print(f'Default page created: {title}')
            else:
                print(f'Warning: seed file not found: {filename}')

    if is_using_fallback('seed_data'):
        print('WARNING: Using default seed data from private.example/. Copy to private/ to customize.')

    db.session.commit()

    # Migrate users from old group_id to new user_groups table
    users_with_legacy_group = User.query.filter(User.group_id.isnot(None)).all()
    migrated_count = 0
    for user in users_with_legacy_group:
        # Check if user already has this group in user_groups
        existing = db.session.execute(
            user_groups.select().where(
                user_groups.c.user_id == user.id,
                user_groups.c.group_id == user.group_id
            )
        ).first()
        if not existing:
            # Add to user_groups with member role
            db.session.execute(
                user_groups.insert().values(
                    user_id=user.id,
                    group_id=user.group_id,
                    role='member'
                )
            )
            migrated_count += 1
    if migrated_count > 0:
        db.session.commit()
        print(f'Migrated {migrated_count} users from legacy group_id to user_groups')

    # Set default author for quizzes without one (use admin user id=1)
    from app.models.quiz import Quiz
    quizzes_without_author = Quiz.query.filter(Quiz.created_by_id.is_(None)).all()
    if quizzes_without_author:
        for quiz in quizzes_without_author:
            quiz.created_by_id = 1  # Admin user
        db.session.commit()
        print(f'Set default author for {len(quizzes_without_author)} quizzes')

    print('Seed data initialized successfully')
"

# Compile translations if translations directory exists
if [ -d "translations" ]; then
    echo "Compiling translations..."
    pybabel compile -d translations 2>/dev/null || echo "Translation compilation skipped (no .po files or error)"
fi

# Start the application with WebSocket support
echo "Starting application with WebSocket support..."
exec gunicorn --bind 0.0.0.0:5000 --workers 1 --worker-class geventwebsocket.gunicorn.workers.GeventWebSocketWorker wsgi:app
