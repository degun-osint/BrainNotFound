"""Rate limits must stop brute force without locking out a class behind one IP."""
import pytest

from app import db, limiter
from tests.conftest import make_user


@pytest.fixture
def app():
    """The usual test app, with rate limits on (off everywhere else)."""
    from app import create_app
    from app.models import SiteSettings
    from tests.conftest import TestConfig

    class LimitedConfig(TestConfig):
        RATELIMIT_ENABLED = True

    app = create_app(LimitedConfig)
    limiter.enabled = True
    limiter.reset()
    with app.app_context():
        db.create_all()
        SiteSettings.get_settings()
        yield app
        db.session.remove()
        db.drop_all()
    limiter.reset()
    limiter.enabled = False


@pytest.fixture
def limits(app):
    return app


def test_a_class_behind_one_ip_can_log_in_together(app, world, limits):
    learners = [make_user(f'learner{i}', groups=[world['g3a']]) for i in range(30)]
    client = app.test_client()
    for u in learners:
        resp = client.post('/login', data={'username': u.username, 'password': 'password'})
        assert resp.status_code == 302 and '/login' not in resp.headers['Location'], u.username  # logged in
        client.get('/logout')


def test_brute_force_on_one_account_is_stopped(app, world, limits):
    client = app.test_client()
    # A wrong password re-displays the form (200); once limited, the POST is bounced back (302)
    statuses = [client.post('/login', data={'username': 'eleve_3a', 'password': f'wrong{i}'}).status_code
                for i in range(12)]
    assert statuses[:10] == [200] * 10 and statuses[10:] == [302, 302]
    # other accounts from the same IP are not affected
    assert client.post('/login', data={'username': 'eleve_ab', 'password': 'wrong'}).status_code == 200
