#!/bin/bash
set -e

export FLASK_APP=wsgi:app

# Apply database migrations (deterministic: no runtime autogenerate, never resets alembic_version)
echo "Applying database migrations..."
python -m scripts.migrate_db

# Initialize seed data (admin user, default group, default pages)
echo "Initializing seed data..."
python -c "
import os
from wsgi import app
from app import db
from app.models.user import User
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
        print('Default admin created: admin (password from ADMIN_DEFAULT_PASSWORD, change it after first login)')

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
