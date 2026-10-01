"""AI quiz generator: review question by question, regenerate only the chosen ones."""
from datetime import datetime, timedelta
from html import unescape
from io import BytesIO

import pytest

from app import db
from app.models import GeneratorDraft, Tenant
from app.utils import quiz_generator
from app.utils.quiz_generator import describe_block, join_blocks, regenerate_questions, split_blocks

QUIZ = """# Le cycle de l'eau

Quiz genere.

## QCM - Qu'est-ce que l'evaporation ? [2 points]
- [ ] La pluie
- [x] Le passage de l'eau liquide a la vapeur
- [ ] La neige
- [ ] Le ruissellement

## QCM - Question ratee sur une date [2 points]
- [x] 1789
- [ ] 1815
- [ ] 1914
- [ ] 1945

## OUVERTE - Expliquez la condensation [4 points]
### Reponse attendue
La vapeur se refroidit et redevient liquide.
"""

NEW_MCQ = """## QCM - Comment se forment les nuages ? [3 points]
- [ ] Par evaporation des oceans uniquement
- [x] Par condensation de la vapeur d'eau
- [ ] Par le vent
- [ ] Par la pression
"""

COURSE = "Le cycle de l'eau decrit les mouvements de l'eau entre oceans, atmosphere et sols. " * 5


def test_blocks_round_trip():
    preamble, blocks = split_blocks(QUIZ)
    assert preamble.startswith("# Le cycle de l'eau") and len(blocks) == 3
    assert [describe_block(b)['question_type'] for b in blocks] == ['mcq', 'mcq', 'open']
    assert split_blocks(join_blocks(preamble, blocks)) == (preamble, blocks)


@pytest.fixture
def ai(monkeypatch):
    """Fake AI: records the prompt, answers with the queued text."""
    state = {'prompts': [], 'answer': NEW_MCQ}

    def fake(messages, **kw):
        state['prompts'].append(messages[0]['content'])
        return state['answer']
    monkeypatch.setattr(quiz_generator, 'complete', fake)
    return state


def test_regenerate_sends_kept_and_rejected_and_keeps_the_points(app, ai):
    _, blocks = split_blocks(QUIZ)
    result = regenerate_questions(COURSE, 'Cycle', kept=[blocks[0], blocks[2]], rejected=[blocks[1]],
                                  specs=[('mcq', 2.0)], guidance='sur les nuages')
    assert result['success']
    prompt = ai['prompts'][0]
    assert "Qu'est-ce que l'evaporation" in prompt and 'Question ratee sur une date' in prompt
    assert 'sur les nuages' in prompt and 'QCM (2 points)' in prompt
    assert describe_block(result['blocks'][0])['points'] == 2.0  # AI said 3: original scale kept


@pytest.mark.parametrize('answer', [NEW_MCQ + '\n' + NEW_MCQ, 'Desole, je ne peux pas.',
                                    '## OUVERTE - Autre [2 points]\n### Reponse attendue\nx\n'])
def test_regenerate_rejects_wrong_count_or_type(app, ai, answer):
    ai['answer'] = answer
    _, blocks = split_blocks(QUIZ)
    assert not regenerate_questions(COURSE, 'Cycle', kept=[], rejected=[blocks[1]], specs=[('mcq', 2.0)])['success']


# ==================== routes ====================

def generate(client, monkeypatch):
    monkeypatch.setattr('app.routes.admin.quizzes.generate_quiz_from_content',
                        lambda **kw: {'success': True, 'markdown': QUIZ})
    return client.post('/admin/quiz/generate', data={
        'title': 'Cycle', 'num_mcq': '2', 'num_open': '1', 'difficulty': 'modere',
        'course_file': (BytesIO(COURSE.encode()), 'cours.txt')}, content_type='multipart/form-data')


def test_generation_keeps_a_draft_and_shows_questions(world, login, monkeypatch):
    html = generate(login(world['dir_a']), monkeypatch).get_data(as_text=True)
    draft = GeneratorDraft.query.one()
    assert draft.user_id == world['dir_a'].id and draft.content.startswith("Le cycle de l'eau")
    assert f'/admin/quiz/generate/{draft.token}/regenerate' in html
    assert html.count('name="regen"') == 3 and 'Question ratee sur une date' in html


def test_regenerating_replaces_only_the_checked_question(world, login, monkeypatch, ai):
    client = login(world['dir_a'])
    generate(client, monkeypatch)
    draft = GeneratorDraft.query.one()
    tenant = db.session.get(Tenant, world['lycee_a'].id)
    used = tenant.used_quiz_generations or 0

    html = unescape(client.post(f'/admin/quiz/generate/{draft.token}/regenerate',
                                data={'markdown_content': QUIZ, 'regen': ['1']}).get_data(as_text=True))
    assert 'Comment se forment les nuages' in html and 'Question ratee sur une date' not in html
    assert "Qu'est-ce que l'evaporation" in html and 'Expliquez la condensation' in html
    _, blocks = split_blocks(html.split('name="markdown_content"', 1)[1].split('>', 1)[1].split('</textarea>')[0])
    assert len(blocks) == 3 and 'nuages' in blocks[1]
    assert (db.session.get(Tenant, tenant.id).used_quiz_generations or 0) == used + 1


def test_failed_regeneration_changes_nothing(world, login, monkeypatch, ai):
    client = login(world['dir_a'])
    generate(client, monkeypatch)
    draft = GeneratorDraft.query.one()
    ai['answer'] = 'Je refuse.'
    html = client.post(f'/admin/quiz/generate/{draft.token}/regenerate',
                       data={'markdown_content': QUIZ, 'regen': ['1']}).get_data(as_text=True)
    assert 'Question ratee sur une date' in html and 'Regeneration impossible' in html


def test_draft_of_someone_else_or_expired(world, login, monkeypatch, ai):
    generate(login(world['dir_a']), monkeypatch)
    draft = GeneratorDraft.query.one()
    resp = login(world['dir_b']).post(f'/admin/quiz/generate/{draft.token}/regenerate',
                                      data={'markdown_content': QUIZ, 'regen': ['1']})
    assert resp.status_code == 302 and ai['prompts'] == []

    draft.created_at = datetime.utcnow() - timedelta(hours=25)
    db.session.commit()
    assert GeneratorDraft.purge_expired() == 1 and GeneratorDraft.query.count() == 0


def test_quiz_options_survive_the_preview_and_regeneration(world, login, monkeypatch, ai):
    client = login(world['dir_a'])
    html = generate(client, monkeypatch).get_data(as_text=True)
    assert 'name="notify_learners" checked' in html  # default on, though the upload was a POST
    draft = GeneratorDraft.query.one()
    html = client.post(f'/admin/quiz/generate/{draft.token}/regenerate', data={
        'markdown_content': QUIZ, 'regen': ['1'], 'grading_options_shown': '1',
        'grading_mode': 'review', 'contest_days': '3'}).get_data(as_text=True)  # notify unchecked by the user
    assert 'name="notify_learners" checked' not in html
    assert 'value="review" checked' in html and 'value="3"' in html
