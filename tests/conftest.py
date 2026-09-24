import pytest

from app import create_app, db, limiter
from app.models import Group, Tenant, User
from config import Config


class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite://'
    WTF_CSRF_ENABLED = False
    RATELIMIT_ENABLED = False
    MAIL_SUPPRESS_SEND = True


@pytest.fixture
def app():
    app = create_app(TestConfig)
    limiter.enabled = False
    with app.app_context():
        db.create_all()
        from app.models import SiteSettings
        SiteSettings.get_settings()  # exists in any real install
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def login(client):
    """Log a user in by writing the Flask-Login session directly."""
    def _login(user):
        with client.session_transaction() as sess:
            sess['_user_id'] = str(user.id)
            sess['_fresh'] = True
        return client
    return _login


def make_user(username, groups=(), role='member', superadmin=False, tenants=()):
    user = User(username=username, email=f'{username}@test.local', is_admin=superadmin)
    user.set_password('password')
    db.session.add(user)
    db.session.flush()
    for group in groups:
        user.add_to_group(group, role)
    for tenant in tenants:
        tenant.add_admin(user)
    db.session.commit()
    return user


@pytest.fixture
def world(app):
    """Two tenants (schools), each with two groups (classes), and the usual cast.

    - lycee_a: 3a, 3b     - lycee_b: 2c
    - prof_3a: group admin of 3a      - prof_3b: group admin of 3b
    - dir_a: tenant admin of lycee_a  - dir_b: tenant admin of lycee_b
    - eleve_3a: member of 3a          - eleve_3a_3b: member of 3a and 3b
    - eleve_ab: member of 3a (lycee_a) and 2c (lycee_b)
    """
    lycee_a = Tenant(slug='lycee-a', name='Lycee A')
    lycee_b = Tenant(slug='lycee-b', name='Lycee B')
    db.session.add_all([lycee_a, lycee_b])
    db.session.flush()

    g3a = Group(name='3A', join_code='CODE3A', tenant_id=lycee_a.id)
    g3b = Group(name='3B', join_code='CODE3B', tenant_id=lycee_a.id)
    g2c = Group(name='2C', join_code='CODE2C', tenant_id=lycee_b.id)
    db.session.add_all([g3a, g3b, g2c])
    db.session.commit()

    w = dict(lycee_a=lycee_a, lycee_b=lycee_b, g3a=g3a, g3b=g3b, g2c=g2c)
    w['root'] = make_user('root', superadmin=True)
    w['dir_a'] = make_user('dir_a', tenants=[lycee_a])
    w['dir_b'] = make_user('dir_b', tenants=[lycee_b])
    w['prof_3a'] = make_user('prof_3a', groups=[g3a], role='admin')
    w['prof_3b'] = make_user('prof_3b', groups=[g3b], role='admin')
    w['eleve_3a'] = make_user('eleve_3a', groups=[g3a])
    w['eleve_3a_3b'] = make_user('eleve_3a_3b', groups=[g3a, g3b])
    w['eleve_ab'] = make_user('eleve_ab', groups=[g3a, g2c])
    return w


@pytest.fixture
def content(world):
    """Quizzes and interviews spread across both tenants.

    - quiz_a: lycee_a, group 3A           - quiz_b: lycee_b, group 2C
    - quiz_shared: lycee_a, groups 3A + 2C - quiz_draft: no group, created by prof_3a
    - itw_a: lycee_a, group 3A            - itw_b: lycee_b, group 2C
    """
    from app.models import Interview, Quiz

    def quiz(title, tenant, groups, author=None):
        q = Quiz(title=title, markdown_content=f'# {title}', tenant_id=tenant.id if tenant else None,
                 created_by_id=author.id if author else None)
        db.session.add(q)
        db.session.flush()
        for g in groups:
            q.groups.append(g)
        return q

    def interview(title, tenant, groups):
        i = Interview(title=title, system_prompt='prompt', tenant_id=tenant.id)
        db.session.add(i)
        db.session.flush()
        for g in groups:
            i.groups.append(g)
        return i

    w = world
    c = {
        'quiz_a': quiz('Quiz Alpha', w['lycee_a'], [w['g3a']]),
        'quiz_b': quiz('Quiz Bravo', w['lycee_b'], [w['g2c']]),
        'quiz_shared': quiz('Quiz Shared', w['lycee_a'], [w['g3a'], w['g2c']]),
        'quiz_draft': quiz('Quiz Draft', None, [], author=w['prof_3a']),
        'itw_a': interview('Interview Alpha', w['lycee_a'], [w['g3a']]),
        'itw_b': interview('Interview Bravo', w['lycee_b'], [w['g2c']]),
    }
    db.session.commit()
    return c
