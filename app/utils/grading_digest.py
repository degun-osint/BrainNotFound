"""Grouped email to quiz graders: papers waiting for them and open contests.

A paper put in review or a new contest marks the quiz (Quiz.mark_digest_pending);
a scheduler job sends at most one email per quiz every GRADER_DIGEST_MINUTES,
listing what is waiting, to the author and the designated graders.
"""
import logging
from datetime import datetime, timedelta

from flask import current_app, url_for
from flask_mail import Message
from markupsafe import escape

from app import db, mail
from app.models import Answer, AnswerContest, Quiz, QuizResponse, User

logger = logging.getLogger(__name__)


def _counts(quiz):
    waiting = QuizResponse.query.filter(
        QuizResponse.quiz_id == quiz.id, QuizResponse.is_test == False,  # noqa: E712
        QuizResponse.grading_status == QuizResponse.STATUS_REVIEW).count()
    contests = AnswerContest.query.join(Answer).join(QuizResponse).filter(
        QuizResponse.quiz_id == quiz.id, AnswerContest.status == AnswerContest.STATUS_OPEN).count()
    return waiting, contests


def _results_link(quiz, status):
    """Absolute link to the quiz results, or None when PUBLIC_URL is not configured."""
    base = current_app.config.get('PUBLIC_URL')
    if not base:
        return None
    with current_app.test_request_context(base_url=base):
        return url_for('admin.quiz_results', identifier=quiz.get_url_identifier(), status=status, _external=True)


def _recipients(quiz):
    ids = quiz.grader_ids()
    users = User.query.filter(User.id.in_(ids)).all() if ids else []
    return [u.email for u in users if u.email and not u.email.endswith('@imported.local')]


def build_digest(quiz, waiting, contests):
    """(subject, text, html) of the digest for one quiz."""
    from app.models import SiteSettings
    site = SiteSettings.get_settings().site_title or 'BrainNotFound'
    parts = []
    if waiting:
        parts.append(f"{waiting} copie(s) en attente d'un correcteur")
    if contests:
        parts.append(f"{contests} contestation(s) a traiter")
    summary = ' et '.join(parts)
    link = _results_link(quiz, 'contests' if contests and not waiting else 'review' if waiting else None)

    subject = f"[{site}] {quiz.title} : {summary}"
    text = f"""Bonjour,

Sur le quiz « {quiz.title} » : {summary}.

{('Ouvrir les resultats : ' + link) if link else 'Connectez-vous et ouvrez les resultats du quiz.'}

Vous recevez ce message comme auteur ou correcteur de ce quiz ; au plus un par quiz toutes les {current_app.config['GRADER_DIGEST_MINUTES']} minutes.
"""
    button = (f'<p style="margin: 24px 0;"><a href="{escape(link)}" style="background: #0a0a0a; color: #fff; '
              f'padding: 10px 18px; text-decoration: none; border-radius: 4px;">Ouvrir les resultats</a></p>'
              if link else '<p>Connectez-vous et ouvrez les resultats du quiz.</p>')
    html = f"""<html><body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
<div style="max-width: 600px; margin: 0 auto; padding: 20px;">
<p>Bonjour,</p>
<p>Sur le quiz <strong>{escape(quiz.title)}</strong> : {escape(summary)}.</p>
{button}
<p style="color: #888; font-size: 12px;">Vous recevez ce message comme auteur ou correcteur de ce quiz ;
au plus un par quiz toutes les {current_app.config['GRADER_DIGEST_MINUTES']} minutes.</p>
</div></body></html>"""
    return subject, text, html


def send_due_digests(now=None):
    """Send the digests whose delay has passed. Returns the number of emails sent. Needs an app context."""
    now = now or datetime.utcnow()
    delay = timedelta(minutes=current_app.config['GRADER_DIGEST_MINUTES'])
    due = Quiz.query.filter(
        Quiz.digest_pending_since.isnot(None),
        db.or_(Quiz.digest_sent_at.is_(None), Quiz.digest_sent_at <= now - delay),
    ).all()
    sent = 0
    for quiz in due:
        waiting, contests = _counts(quiz)
        recipients = _recipients(quiz)
        if (waiting or contests) and recipients:
            subject, text, html = build_digest(quiz, waiting, contests)
            try:
                mail.send(Message(subject=subject, recipients=recipients, body=text, html=html))
                sent += 1
            except Exception as e:
                # Keep it pending: retried at the next run
                logger.error(f'Grader digest for quiz {quiz.id} failed: {e}')
                continue
            quiz.digest_sent_at = now
        quiz.digest_pending_since = None
    db.session.commit()
    return sent
