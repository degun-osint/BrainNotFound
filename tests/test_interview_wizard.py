"""The interview wizard form: what it renders back, and what it refuses to submit."""
from app import db
from app.models.interview import Interview


def edit_page(login, user, interview):
    url = f'/interview/admin/interviews/{interview.get_url_identifier()}/edit'
    return login(user).get(url).get_data(as_text=True)


def test_empty_columns_do_not_come_back_as_the_word_None(world, content, login):
    """Jinja renders None as "None": it landed in the slug (breaking its pattern,
    so the form refused to submit in silence) and in every text area, where the
    next save wrote the literal word into the database."""
    interview = content['itw_a']
    assert interview.slug is None and interview.description is None
    html = edit_page(login, world['dir_a'], interview)

    assert 'value="None"' not in html
    assert '>None<' not in html


def test_the_saved_values_still_come_back(world, content, login):
    interview = content['itw_a']
    interview.slug = 'entretien-test'
    interview.description = 'Une description'
    interview.persona_name = 'Claire Dubois'
    db.session.commit()

    html = edit_page(login, world['dir_a'], interview)
    assert 'value="entretien-test"' in html
    assert 'Une description' in html
    assert 'value="Claire Dubois"' in html


def test_a_null_slug_leaves_the_field_empty_so_the_pattern_passes(world, content, login):
    """pattern="[a-z0-9\\-]+" rejects "None" but accepts an empty field."""
    html = edit_page(login, world['dir_a'], content['itw_a'])
    assert 'name="slug"' in html
    slug_field = html[html.index('name="slug"'):][:400]
    assert 'value=""' in slug_field


def test_the_form_checks_itself_before_submitting(world, content, login):
    """A required field on an earlier step is hidden, and a browser will not
    submit what it cannot show a message on: the wizard takes the check over."""
    html = edit_page(login, world['dir_a'], content['itw_a'])
    assert 'checkBeforeSubmit(event)' in html
    assert 'function checkBeforeSubmit' in html


def test_the_speed_field_cannot_block_the_form_while_hidden(world, content, login):
    """step="0.1" can read as a mismatch in floating point, and the field is
    hidden when the voice is off: an invalid hidden control kills the submit."""
    interview = content['itw_a']
    interview.tts_mode = Interview.TTS_OFF
    db.session.commit()

    html = edit_page(login, world['dir_a'], interview)
    assert 'name="tts_rate"' in html
    rate_field = html[html.index('name="tts_rate"'):][:300]
    assert 'step="any"' in rate_field
