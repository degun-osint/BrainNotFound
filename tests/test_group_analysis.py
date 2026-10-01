"""Group analysis: only the chosen group's papers, never papers outside the viewer's scope."""
import json

import pytest

from app import db
from app.models import Quiz, QuizAnalysis, QuizResponse
from tests.conftest import make_user


@pytest.fixture
def ai(monkeypatch):
    """Fake AI: records the learner names it was sent."""
    sent = []

    def fake(messages, **kw):
        sent.append(messages[0]['content'])
        return json.dumps({'pedagogical_summary': 'Analyse factice', 'concepts_to_review': []})
    monkeypatch.setattr('app.utils.anomaly_detector.complete', fake)
    return sent


def paper(user, quiz, test=False):
    r = QuizResponse(user_id=user.id, quiz_id=quiz.id, total_score=5, max_score=10, is_test=test)
    db.session.add(r)
    db.session.commit()
    return r


@pytest.fixture
def two_groups(world):
    """A quiz for 3A and 3B; one learner in 3A only, one in both, one in 3B only, plus a test paper."""
    quiz = Quiz(title='Quiz 3A 3B', markdown_content='# x', tenant_id=world['lycee_a'].id)
    db.session.add(quiz)
    db.session.flush()
    quiz.groups.append(world['g3a'])
    quiz.groups.append(world['g3b'])
    only_3b = make_user('only_3b', groups=[world['g3b']])
    for user in (world['eleve_3a'], world['eleve_3a_3b'], only_3b):
        paper(user, quiz)
    paper(world['prof_3b'], quiz, test=True)
    return quiz


def analyse(client, quiz, group=None):
    url = f'/admin/quiz/{quiz.get_url_identifier()}/analyze-class' + (f'?group={group.id}' if group else '')
    return client.post(url)


def test_analysis_covers_only_the_chosen_group(world, login, two_groups, ai):
    resp = analyse(login(world['dir_a']), two_groups, world['g3b'])
    assert resp.get_json()['success']
    prompt = ai[0]
    assert 'eleve_3a_3b' in prompt and 'only_3b' in prompt
    assert '"eleve_3a"' not in prompt and 'prof_3b' not in prompt  # other group, test paper
    analysis = QuizAnalysis.query.one()
    assert analysis.group_id == world['g3b'].id and len(analysis.response_ids) == 2


def test_each_group_keeps_its_own_analysis(world, login, two_groups, ai):
    client = login(world['dir_a'])
    analyse(client, two_groups, world['g3a'])
    analyse(client, two_groups, world['g3b'])
    page_3a = client.get(f"/admin/quiz/{two_groups.get_url_identifier()}/class-analysis?group={world['g3a'].id}")
    assert 'sur 2 copie(s)' in page_3a.get_data(as_text=True)  # eleve_3a and eleve_3a_3b, not overwritten by 3B


def test_no_analysis_or_names_from_another_organization(world, content, login, ai):
    quiz = content['quiz_shared']  # assigned to 3A (lycee A) and 2C (lycee B)
    learner_b = make_user('learner_b', groups=[world['g2c']])
    paper(world['eleve_3a'], quiz)
    paper(learner_b, quiz)

    analyse(login(world['dir_b']), quiz)
    assert 'learner_b' in ai[0] and '"eleve_3a"' not in ai[0]  # dir_b only analyses lycee B papers

    html = login(world['dir_a']).get(f'/admin/quiz/{quiz.get_url_identifier()}/class-analysis').get_data(as_text=True)
    assert 'learner_b' not in html and 'Analyse factice' not in html  # neither the names nor dir_b's analysis


def test_new_papers_since_the_analysis_are_signalled(world, login, two_groups, ai):
    client = login(world['dir_a'])
    analyse(client, two_groups, world['g3b'])
    paper(make_user('late_3b', groups=[world['g3b']]), two_groups)
    html = client.get(f"/admin/quiz/{two_groups.get_url_identifier()}/class-analysis?group={world['g3b'].id}").get_data(as_text=True)
    assert 'Analyse factice' in html and '1 nouvelle(s) copie(s)' in html


def test_group_outside_scope_is_refused(world, content, login, ai):
    resp = login(world['dir_a']).get(
        f"/admin/quiz/{content['quiz_shared'].get_url_identifier()}/class-analysis?group={world['g2c'].id}")
    assert resp.status_code == 302 and ai == []
