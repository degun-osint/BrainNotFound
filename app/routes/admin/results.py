"""Quiz results: submissions, regrading, CSV export, score edits, AI analyses."""
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from flask_babel import lazy_gettext as _l
from app import db
from app.models.user import user_groups
from app.models.group import Group
from app.models.quiz import Quiz, Question, QuizResponse, Answer, AnswerContest
from app.utils.scope import scoped_groups, scoped_group_ids, scoped_user_ids
from datetime import datetime
from app.routes.admin import admin_bp
from app.routes.admin.common import admin_required, sanitize_filename


RESULT_FILTERS = ('review', 'contests')


def scoped_quiz_responses(quiz, group_id=None, status=None):
    """Responses to a quiz the current admin can see, optionally for one group or one status.

    Graders of the quiz (author, designated graders) see every paper; other
    admins only those of the learners they manage.
    status: 'review' (waiting for a grader) or 'contests' (with an open contest).
    """
    query = QuizResponse.query.filter(QuizResponse.quiz_id == quiz.id)
    grader = current_user.is_grader_of(quiz)
    if group_id:
        allowed_groups = scoped_group_ids()
        if grader:
            allowed_groups = [g.id for g in quiz.groups] + [row[0] for row in allowed_groups]
        members = db.session.query(user_groups.c.user_id).filter(
            user_groups.c.group_id == group_id,
            user_groups.c.group_id.in_(allowed_groups)
        )
        query = query.filter(QuizResponse.user_id.in_(members))
    elif not current_user.is_superadmin and not grader:
        query = query.filter(QuizResponse.user_id.in_(scoped_user_ids()))
    if status == 'review':
        query = query.filter(QuizResponse.grading_status == QuizResponse.STATUS_REVIEW)
    elif status == 'contests':
        open_contests = db.session.query(Answer.quiz_response_id).join(AnswerContest).filter(
            AnswerContest.status == AnswerContest.STATUS_OPEN)
        query = query.filter(QuizResponse.id.in_(open_contests))
    return query.order_by(QuizResponse.submitted_at.desc())


def grading_todo():
    """[(quiz, papers waiting, open contests)] the current user can handle, most urgent first.

    Quizzes in the admin's scope, plus those they wrote or grade.
    """
    from app.models.quiz import quiz_graders
    from app.utils.scope import scoped_quizzes
    mine = db.or_(
        Quiz.id.in_(scoped_quizzes().with_entities(Quiz.id)),
        Quiz.created_by_id == current_user.id,
        Quiz.id.in_(db.session.query(quiz_graders.c.quiz_id).filter(quiz_graders.c.user_id == current_user.id)),
    )
    waiting = dict(db.session.query(QuizResponse.quiz_id, db.func.count()).join(Quiz).filter(
        mine, QuizResponse.is_test == False,  # noqa: E712
        QuizResponse.grading_status == QuizResponse.STATUS_REVIEW).group_by(QuizResponse.quiz_id).all())
    contests = dict(db.session.query(QuizResponse.quiz_id, db.func.count()).join(Quiz).join(
        Answer, Answer.quiz_response_id == QuizResponse.id).join(AnswerContest).filter(
        mine, AnswerContest.status == AnswerContest.STATUS_OPEN).group_by(QuizResponse.quiz_id).all())
    ids = set(waiting) | set(contests)
    quizzes = Quiz.query.filter(Quiz.id.in_(ids)).all() if ids else []
    todo = [(q, waiting.get(q.id, 0), contests.get(q.id, 0)) for q in quizzes]
    return sorted(todo, key=lambda t: (-t[2], -t[1], t[0].title))


def pending_counts(quiz_ids):
    """{quiz_id: (papers waiting for a grader, open contests)} for the given quizzes."""
    if not quiz_ids:
        return {}
    counts = {qid: [0, 0] for qid in quiz_ids}
    for qid, n in db.session.query(QuizResponse.quiz_id, db.func.count()).filter(
            QuizResponse.quiz_id.in_(quiz_ids), QuizResponse.is_test == False,  # noqa: E712
            QuizResponse.grading_status == QuizResponse.STATUS_REVIEW).group_by(QuizResponse.quiz_id):
        counts[qid][0] = n
    for qid, n in db.session.query(QuizResponse.quiz_id, db.func.count()).join(
            Answer, Answer.quiz_response_id == QuizResponse.id).join(AnswerContest).filter(
            QuizResponse.quiz_id.in_(quiz_ids),
            AnswerContest.status == AnswerContest.STATUS_OPEN).group_by(QuizResponse.quiz_id):
        counts[qid][1] = n
    return {qid: tuple(c) for qid, c in counts.items()}


def _quiz_for_grading(identifier):
    """(quiz, None) if the current user may grade it, else (None, redirect)."""
    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        flash(_l('Quiz introuvable'), 'error')
        return None, redirect(url_for('admin.dashboard'))
    if not current_user.can_grade_quiz(quiz):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return None, redirect(url_for('admin.dashboard'))
    return quiz, None


@admin_bp.route('/quiz/<identifier>/results')
@login_required
@admin_required
def quiz_results(identifier):
    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        flash(_l('Quiz introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != quiz.get_url_identifier():
        return redirect(url_for('admin.quiz_results', identifier=quiz.get_url_identifier()), code=301)

    # Check permission
    if not current_user.can_grade_quiz(quiz):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return redirect(url_for('admin.dashboard'))

    group_filter = request.args.get('group', None, type=int)
    status = request.args.get('status', '')
    status = status if status in RESULT_FILTERS else ''
    groups = scoped_groups(active_only=False).all()
    if current_user.is_grader_of(quiz):
        groups = sorted({g.id: g for g in groups + quiz.groups.all()}.values(), key=lambda g: g.name)
    responses = scoped_quiz_responses(quiz, group_filter, status).all()
    user_group_names = Group.names_by_user({r.user_id for r in responses})
    open_contests = {row[0] for row in db.session.query(Answer.quiz_response_id).join(AnswerContest).filter(
        Answer.quiz_response_id.in_([r.id for r in responses]),
        AnswerContest.status == AnswerContest.STATUS_OPEN)} if responses else set()
    to_review, contests = pending_counts([quiz.id]).get(quiz.id, (0, 0))

    return render_template('admin/quiz_results.html', quiz=quiz, responses=responses, groups=groups,
                           selected_group=group_filter, user_group_names=user_group_names, status=status,
                           open_contests=open_contests, to_review=to_review, contest_count=contests,
                           can_validate_all=bool(scoped_quiz_responses(quiz, status='review').filter(
                               QuizResponse.review_reason == QuizResponse.REVIEW_MODE).count()))


@admin_bp.route('/quiz/<identifier>/regrade', methods=['POST'])
@login_required
@admin_required
def regrade_quiz(identifier):
    """Re-grade all open questions for a quiz."""
    from app.tasks import grade_quiz, run_task

    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        flash(_l('Quiz introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    quiz_id = quiz.id  # Keep for queries

    # Check permission
    if not current_user.can_grade_quiz(quiz):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Get all completed responses for this quiz
    responses = QuizResponse.query.filter_by(quiz_id=quiz_id).all()

    regrade_count = 0
    for response in responses:
        # Get all open question answers
        answers_to_grade = []
        for answer in response.answers:
            if answer.question.question_type == 'open':
                answers_to_grade.append({
                    'answer_id': answer.id,
                    'question_id': answer.question_id
                })

        if answers_to_grade:
            # Reset scores for open questions
            mcq_score = 0.0
            for answer in response.answers:
                if answer.question.question_type == 'mcq':
                    mcq_score += answer.score or 0.0
                else:
                    answer.score = 0.0
                    answer.ai_feedback = None

            response.total_score = mcq_score
            response.grading_status = 'pending'
            response.grading_total = len(answers_to_grade)
            response.grading_progress = 0
            db.session.commit()

            # Start async grading
            run_task(grade_quiz, response.id, answers_to_grade)
            regrade_count += 1

    if regrade_count > 0:
        flash(_l('Re-correction lancee pour %(count)s copie(s). Les notes seront mises a jour progressivement.', count=regrade_count), 'success')
    else:
        flash(_l('Aucune question ouverte a re-corriger.'), 'info')

    return redirect(url_for('admin.quiz_results', identifier=quiz.get_url_identifier()))


@admin_bp.route('/quiz/<identifier>/export-csv')
@login_required
@admin_required
def export_quiz_csv(identifier):
    """Export quiz results as CSV."""
    import csv
    from io import StringIO
    from flask import Response

    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        flash(_l('Quiz introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Check permission
    if not current_user.can_grade_quiz(quiz):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return redirect(url_for('admin.dashboard'))

    group_filter = request.args.get('group', None, type=int)
    responses = scoped_quiz_responses(quiz, group_filter).all()

    # Create CSV in memory
    output = StringIO()
    writer = csv.writer(output, delimiter=';')

    # Header row
    writer.writerow([
        'Nom', 'Prenom', 'Username', 'Email', 'Groupes',
        'Score', 'Score Max', 'Pourcentage', 'Date soumission', 'En retard'
    ])

    # Data rows
    for resp in responses:
        user = resp.user
        percentage = (resp.total_score / resp.max_score * 100) if resp.max_score > 0 else 0
        # Get all user groups as comma-separated list
        user_group_names = ', '.join([g.name for g in user.groups])
        writer.writerow([
            user.last_name or '',
            user.first_name or '',
            user.username,
            user.email,
            user_group_names,
            f"{resp.total_score:.2f}",
            f"{resp.max_score:.2f}",
            f"{percentage:.1f}%",
            resp.submitted_at.strftime('%Y-%m-%d %H:%M') if resp.submitted_at else '',
            'Oui' if resp.is_late else 'Non'
        ])

    # Generate response
    output.seek(0)
    filename = f"resultats_{sanitize_filename(quiz.title[:30])}_{datetime.now().strftime('%Y%m%d')}.csv"

    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


# Quiz response management
def _response_for_grading(identifier):
    """(response, None) if the current user may grade this paper, else (None, redirect)."""
    response = QuizResponse.get_by_identifier(identifier)
    if not response:
        flash(_l('Reponse introuvable'), 'error')
        return None, redirect(url_for('admin.dashboard'))
    quiz = response.quiz
    # Graders of the quiz grade every paper; otherwise the learner must be in our scope
    if not (current_user.is_grader_of(quiz)
            or (current_user.can_access_quiz(quiz) and current_user.can_access_user(response.user))):
        flash(_l('Vous n\'avez pas acces a cette copie'), 'error')
        return None, redirect(url_for('admin.dashboard'))
    return response, None


def _results_url(quiz):
    """Back to the results, keeping the list filters the grader came from."""
    return url_for('admin.quiz_results', identifier=quiz.get_url_identifier(),
                   status=request.args.get('status') or None, group=request.args.get('group') or None)


@admin_bp.route('/response/<identifier>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_response(identifier):
    """Grade a paper: scores, feedback, comment, validation, contests."""
    response, error = _response_for_grading(identifier)
    if error:
        return error
    if identifier != response.get_url_identifier():
        return redirect(url_for('admin.edit_response', identifier=response.get_url_identifier()), code=301)

    quiz = response.quiz
    user = response.user
    answers = Answer.query.join(Question).filter(
        Answer.quiz_response_id == response.id
    ).order_by(Question.order).all()

    if request.method == 'POST':
        now = datetime.utcnow()
        for answer in answers:
            previous = answer.score or 0.0
            new_score = request.form.get(f'score_{answer.id}', type=float)
            if new_score is not None:
                answer.score = max(0, min(answer.max_score, new_score))
            new_feedback = request.form.get(f'feedback_{answer.id}', '').strip()
            if new_feedback and answer.question.question_type == 'open':
                answer.ai_feedback = new_feedback

            # Contest of this answer: accepted (grade changed) or rejected (grade kept), with a reply
            contest = answer.contest
            decision = request.form.get(f'contest_{answer.id}')
            if contest and contest.is_open and decision in ('accept', 'reject'):
                if decision == 'reject':
                    answer.score = previous
                contest.status = AnswerContest.STATUS_ACCEPTED if decision == 'accept' else AnswerContest.STATUS_REJECTED
                contest.reply = request.form.get(f'contest_reply_{answer.id}', '').strip() or None
                contest.score_before = previous
                contest.score_after = answer.score
                contest.resolved_by_id = current_user.id
                contest.resolved_at = now

        response.recompute_total()
        response.admin_comment = request.form.get('admin_comment', '').strip() or None
        if request.form.get('action') == 'validate' and response.grading_status == QuizResponse.STATUS_REVIEW:
            response.publish(reviewer=current_user)
            flash(_l('Copie de %(name)s validee : la note est publiee.', name=user.full_name), 'success')
        else:
            flash(_l('Scores mis a jour pour %(name)s', name=user.full_name), 'success')
        db.session.commit()
        return redirect(_results_url(quiz))

    return render_template('admin/edit_response.html', response=response, quiz=quiz, user=user,
                           answers=answers, status=request.args.get('status', ''),
                           group=request.args.get('group', ''))


@admin_bp.route('/response/<identifier>/validate', methods=['POST'])
@login_required
@admin_required
def validate_response(identifier):
    """Publish a paper the AI graded, as is."""
    response, error = _response_for_grading(identifier)
    if error:
        return error
    if response.grading_status == QuizResponse.STATUS_REVIEW:
        response.publish(reviewer=current_user)
        db.session.commit()
        flash(_l('Copie de %(name)s validee : la note est publiee.', name=response.user.full_name), 'success')
    return redirect(_results_url(response.quiz))


@admin_bp.route('/quiz/<identifier>/validate-all', methods=['POST'])
@login_required
@admin_required
def validate_all_responses(identifier):
    """Publish every paper the AI fully graded and that waits for validation.

    Papers the AI could not grade (quota, error) are left alone: their missing
    answers would be published with 0.
    """
    quiz, error = _quiz_for_grading(identifier)
    if error:
        return error
    papers = scoped_quiz_responses(quiz, status='review').filter(
        QuizResponse.review_reason == QuizResponse.REVIEW_MODE).all()
    for response in papers:
        response.publish(reviewer=current_user)
    db.session.commit()
    flash(_l('%(count)s copie(s) validee(s).', count=len(papers)), 'success')
    return redirect(_results_url(quiz))


@admin_bp.route('/response/<identifier>/delete', methods=['POST'])
@login_required
@admin_required
def delete_response(identifier):
    """Delete a quiz response (allows user to retake the quiz)."""
    response = QuizResponse.get_by_identifier(identifier)
    if not response:
        flash(_l('Reponse introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    response_id = response.id  # Keep for queries
    quiz = response.quiz
    user = response.user

    # Permission check - must have access to both the quiz and the user
    if not current_user.can_access_quiz(quiz):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return redirect(url_for('admin.dashboard'))

    if not current_user.can_access_user(user):
        flash(_l('Vous n\'avez pas acces a cet utilisateur'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Delete all answers first (cascade should handle this but being explicit)
    Answer.query.filter_by(quiz_response_id=response_id).delete()
    db.session.delete(response)
    db.session.commit()

    flash(_l('Reponse de %(name)s supprimee. L\'utilisateur peut maintenant repasser le quiz.', name=user.full_name), 'success')

    # Redirect back to the referring page
    referer = request.referrer
    if referer and f'/admin/user/{user.get_url_identifier()}' in referer:
        return redirect(url_for('admin.user_detail', identifier=user.get_url_identifier(), _anchor='results'))
    return redirect(url_for('admin.quiz_results', identifier=quiz.get_url_identifier()))


@admin_bp.route('/response/<identifier>/analysis')
@login_required
@admin_required
def response_analysis(identifier):
    """Show detailed analysis page for a quiz response."""
    from app.utils.anomaly_detector import get_response_stats

    response = QuizResponse.get_by_identifier(identifier)
    if not response:
        flash(_l('Reponse introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Redirect if accessed by old numeric ID
    if identifier != response.get_url_identifier():
        return redirect(url_for('admin.response_analysis', identifier=response.get_url_identifier()), code=301)

    # Check permission
    if not current_user.can_access_quiz(response.quiz) or not current_user.can_access_user(response.user):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return redirect(url_for('admin.dashboard'))

    stats = get_response_stats(response.id)
    if not stats:
        flash(_l('Reponse introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    class_averages = stats.get('class_averages', {})

    return render_template('admin/response_analysis.html',
                          stats=stats,
                          class_averages=class_averages,
                          quiz=response.quiz,
                          response=response)


@admin_bp.route('/response/<identifier>/analyze', methods=['POST'])
@login_required
@admin_required
def analyze_response(identifier):
    """Run AI analysis on a quiz response."""
    from app.utils.anomaly_detector import analyze_quiz_response

    response = QuizResponse.get_by_identifier(identifier)
    if not response:
        return jsonify({'error': 'Response not found'}), 404

    # Check permission
    if not current_user.can_access_quiz(response.quiz) or not current_user.can_access_user(response.user):
        return jsonify({'error': 'Unauthorized'}), 403

    tenant = response.quiz.tenant
    if tenant and not tenant.can_analyze_class():
        return jsonify({'error': str(_l('Quota mensuel d\'analyses IA atteint pour cet etablissement'))}), 429

    # Update status
    response.ai_analysis_status = 'pending'
    db.session.commit()

    try:
        # Run analysis
        result = analyze_quiz_response(response.id)

        # Save result
        response.ai_analysis_result = result
        response.ai_analysis_status = 'completed'
        db.session.commit()
        if tenant:
            tenant.increment_class_analyses()

        return jsonify({'success': True, 'result': result})

    except Exception as e:
        current_app.logger.error(f"AI analysis error for response {response.id}: {str(e)}")
        response.ai_analysis_status = 'error'
        db.session.commit()
        return jsonify({'error': 'Erreur lors de l\'analyse. Veuillez reessayer.'}), 500


@admin_bp.route('/quiz/<identifier>/class-analysis')
@login_required
@admin_required
def class_analysis(identifier):
    """Show class-wide analysis page for a quiz."""
    from app.utils.anomaly_detector import get_class_stats

    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        flash(_l('Quiz introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Redirect if accessed by old numeric ID
    if identifier != quiz.get_url_identifier():
        return redirect(url_for('admin.class_analysis', identifier=quiz.get_url_identifier()), code=301)

    # Check permission
    if not current_user.can_access_quiz(quiz):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return redirect(url_for('admin.dashboard'))

    stats = get_class_stats(quiz.id)
    if not stats:
        flash(_l('Quiz introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    if 'error' in stats:
        flash(stats['error'], 'warning')
        return redirect(url_for('admin.quiz_results', identifier=quiz.get_url_identifier()))

    # Check if analysis exists in quiz
    analysis_result = quiz.class_analysis_result if hasattr(quiz, 'class_analysis_result') else None

    return render_template('admin/class_analysis.html',
                          quiz=quiz,
                          stats=stats,
                          analysis=analysis_result)


@admin_bp.route('/quiz/<identifier>/analyze-class', methods=['POST'])
@login_required
@admin_required
def analyze_class_route(identifier):
    """Run AI analysis on all responses for a quiz."""
    from app.utils.anomaly_detector import analyze_class

    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        return jsonify({'error': 'Quiz not found'}), 404

    # Check permission
    if not current_user.can_access_quiz(quiz):
        return jsonify({'error': 'Unauthorized'}), 403

    if quiz.tenant and not quiz.tenant.can_analyze_class():
        return jsonify({'error': str(_l('Quota mensuel d\'analyses IA atteint pour cet etablissement'))}), 429

    try:
        result = analyze_class(quiz.id)

        if 'error' in result and result.get('class_risk_level') == 'unknown':
            return jsonify({'error': result['error']}), 500

        # Store result in quiz
        quiz.class_analysis_result = result
        db.session.commit()
        if quiz.tenant:
            quiz.tenant.increment_class_analyses()

        return jsonify({'success': True, 'result': result})

    except Exception as e:
        current_app.logger.error(f"Class analysis error for quiz {quiz.id}: {str(e)}")
        return jsonify({'error': 'Erreur lors de l\'analyse. Veuillez reessayer.'}), 500
