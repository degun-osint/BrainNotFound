"""Emails to learners: grade validated by a grader, contest handled.

Sent only when the quiz allows it (Quiz.notify_learners), never for test papers
or accounts without a real address, in the learner's language. Called during
the grader's request (links are absolute), sent in the background.
"""
from flask import url_for
from flask_babel import force_locale, gettext as _
from flask_mail import Message
from markupsafe import escape

from app.models import SiteSettings


def _recipient(response):
    user = response.user
    if (not response.quiz.notify_learners or response.is_test or not user.email
            or user.email.endswith('@imported.local')):
        return None
    return user


def _send(user, subject, paragraphs, link):
    """Plain text + simple HTML email, queued for the worker."""
    from app.utils.email_sender import send_email_async
    site = SiteSettings.get_settings().site_title or 'BrainNotFound'
    greeting = _('Bonjour %(name)s,', name=user.first_name or user.username)
    button = _('Voir ma copie')
    text = '\n\n'.join([greeting, *paragraphs, _('Voir ma copie : %(link)s', link=link), site]) + '\n'
    html = (
        '<html><body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">'
        '<div style="max-width: 600px; margin: 0 auto; padding: 20px;">'
        f'<p>{escape(greeting)}</p>'
        + ''.join(f'<p style="white-space: pre-line;">{escape(p)}</p>' for p in paragraphs)
        + f'<p style="margin: 24px 0;"><a href="{escape(link)}" style="background: #0a0a0a; color: #fff; '
          f'padding: 10px 18px; text-decoration: none; border-radius: 4px;">{escape(button)}</a></p>'
        f'<p style="color: #888; font-size: 12px;">{escape(site)}</p></div></body></html>'
    )
    send_email_async(Message(subject=f'[{site}] {subject}', recipients=[user.email], body=text, html=html))


def notify_grade_published(response):
    """A grader validated the paper: the grade is final."""
    user = _recipient(response)
    if not user:
        return
    link = url_for('quiz.result', identifier=response.get_url_identifier(), _external=True)
    with force_locale(user.language_preference or 'fr'):
        paragraphs = [_('Votre copie du quiz « %(quiz)s » a ete validee par un correcteur : votre note est definitive.',
                        quiz=response.quiz.title),
                      _('Note : %(score)s / %(max)s', score=f'{response.total_score:g}', max=f'{response.max_score:g}')]
        deadline = response.contest_deadline()
        if deadline:
            paragraphs.append(_("Si une note vous semble injuste, vous pouvez la contester question par question "
                                "jusqu'au %(date)s.", date=_local(deadline)))
        _send(user, _('Note definitive : %(quiz)s', quiz=response.quiz.title), paragraphs, link)


def notify_contest_resolved(contest):
    """A grader accepted or rejected a contest."""
    answer = contest.answer
    response = answer.quiz_response
    user = _recipient(response)
    if not user:
        return
    link = url_for('quiz.result', identifier=response.get_url_identifier(),
                   _anchor=f'answer-{answer.id}', _external=True)
    with force_locale(user.language_preference or 'fr'):
        question = answer.question.question_text
        question = question if len(question) <= 120 else question[:117] + '...'
        if contest.status == contest.STATUS_ACCEPTED:
            decision = _('Votre contestation a ete acceptee : la note de cette question passe de %(before)s a '
                         '%(after)s. Nouvelle note du quiz : %(total)s / %(max)s.',
                         before=f'{contest.score_before:g}', after=f'{contest.score_after:g}',
                         total=f'{response.total_score:g}', max=f'{response.max_score:g}')
        else:
            decision = _('Votre contestation a ete examinee : la note de cette question est maintenue.')
        paragraphs = [_('Quiz « %(quiz)s », question : %(question)s', quiz=response.quiz.title, question=question),
                      decision]
        if contest.reply:
            paragraphs.append(_('Reponse du correcteur : %(reply)s', reply=contest.reply))
        _send(user, _('Contestation traitee : %(quiz)s', quiz=response.quiz.title), paragraphs, link)


def _local(dt):
    from app.utils import format_datetime
    return format_datetime(dt, '%d/%m/%Y %H:%M')
