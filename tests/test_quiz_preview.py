"""Live preview of the quiz editor."""
from app import db


def preview(client, markdown, quiz=None):
    return client.post('/admin/quiz/preview-markdown', json={'markdown': markdown, 'quiz': quiz}).get_json()


def test_preview_cards_and_totals(world, login):
    data = preview(login(world['prof_3a']), "# Quiz\n\n## QCM - Capitale ? [2 points]\n- [ ] Lyon\n- [x] Paris\n\n"
                                            "## OUVERTE - Expliquez [3 points]\n### Reponse attendue\nParce que.\n")
    assert data['count'] == 2 and data['points'] == 5 and data['errors'] == []
    assert 'Capitale ?' in data['html'] and 'Parce que.' in data['html'] and 'check-circle' in data['html']


def test_preview_points_out_mistakes(world, login):
    data = preview(login(world['prof_3a']), "# Quiz\n\n## QCM - Sans bonne reponse [1 point]\n- [ ] a\n- [ ] b\n\n"
                                            "## QUESTION - Mot-cle inconnu\ntexte\n\n## OUVERTE - Sans reponse [2 points]\n")
    assert any('illisible' in e for e in data['errors'])          # "## QUESTION -" is not a question type
    assert any('aucune reponse correcte' in e for e in data['errors'])
    assert any('pas de reponse attendue' in w for w in data['warnings'])
    assert 'Aucune bonne reponse' in data['html']


def test_preview_shows_images_only_for_an_accessible_quiz(world, content, login):
    quiz = content['quiz_a']
    md = '# Q\n\n## QCM - Schema ![s](schema.png) [1 point]\n- [x] a\n- [ ] b\n'
    assert '<img' in preview(login(world['prof_3a']), md, quiz.get_url_identifier())['html']
    assert '<img' not in preview(login(world['prof_3b']), md, quiz.get_url_identifier())['html']  # no access


def test_editor_pages_have_the_preview(world, content, login):
    client = login(world['dir_a'])
    for url in ('/admin/quiz/create', f"/admin/quiz/{content['quiz_a'].get_url_identifier()}/edit"):
        html = client.get(url).get_data(as_text=True)
        assert 'id="md-preview"' in html and '/admin/quiz/preview-markdown' in html, url
