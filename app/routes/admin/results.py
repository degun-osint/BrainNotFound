"""Quiz results: submissions, regrading, CSV export, score edits, AI analyses."""
from flask import render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from flask_babel import lazy_gettext as _l
from app import db
from app.models.user import user_groups
from app.models.group import Group
from app.models.quiz import Quiz, Question, QuizResponse, Answer
from app.utils.scope import scoped_groups, scoped_group_ids, scoped_user_ids
from datetime import datetime
from app.routes.admin import admin_bp
from app.routes.admin.common import admin_required, sanitize_filename


def scoped_quiz_responses(quiz, group_id=None):
    """Responses to a quiz from users the current admin can see, optionally for one group."""
    query = QuizResponse.query.filter(QuizResponse.quiz_id == quiz.id)
    if group_id:
        members = db.session.query(user_groups.c.user_id).filter(
            user_groups.c.group_id == group_id,
            user_groups.c.group_id.in_(scoped_group_ids())
        )
        query = query.filter(QuizResponse.user_id.in_(members))
    elif not current_user.is_superadmin:
        query = query.filter(QuizResponse.user_id.in_(scoped_user_ids()))
    return query.order_by(QuizResponse.submitted_at.desc())


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
    if not current_user.can_access_quiz(quiz):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return redirect(url_for('admin.dashboard'))

    group_filter = request.args.get('group', None, type=int)
    groups = scoped_groups(active_only=False).all()
    responses = scoped_quiz_responses(quiz, group_filter).all()
    user_group_names = Group.names_by_user({r.user_id for r in responses})

    return render_template('admin/quiz_results.html', quiz=quiz, responses=responses, groups=groups,
                           selected_group=group_filter, user_group_names=user_group_names)


@admin_bp.route('/quiz/<identifier>/regrade', methods=['POST'])
@login_required
@admin_required
def regrade_quiz(identifier):
    """Re-grade all open questions for a quiz."""
    from app.utils.grading_tasks import grade_quiz_async

    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        flash(_l('Quiz introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    quiz_id = quiz.id  # Keep for queries

    # Check permission
    if not current_user.can_access_quiz(quiz):
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
            from app import socketio
            socketio.start_background_task(
                grade_quiz_async,
                current_app._get_current_object(),
                response.id,
                answers_to_grade
            )
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
    if not current_user.can_access_quiz(quiz):
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
@admin_bp.route('/response/<identifier>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_response(identifier):
    """Edit scores for a quiz response."""
    response = QuizResponse.get_by_identifier(identifier)
    if not response:
        flash(_l('Reponse introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    response_id = response.id  # Keep for queries

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != response.get_url_identifier():
        return redirect(url_for('admin.edit_response', identifier=response.get_url_identifier()), code=301)

    quiz = response.quiz
    user = response.user

    # Permission check
    if not current_user.can_access_quiz(quiz):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return redirect(url_for('admin.dashboard'))

    if not current_user.can_access_user(user):
        flash(_l('Vous n\'avez pas acces a cet utilisateur'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Get answers with their questions, ordered by question order
    answers = Answer.query.join(Question).filter(
        Answer.quiz_response_id == response_id
    ).order_by(Question.order).all()

    if request.method == 'POST':
        total_score = 0.0

        for answer in answers:
            # Get score from form
            score_key = f'score_{answer.id}'
            feedback_key = f'feedback_{answer.id}'

            new_score = request.form.get(score_key, type=float)
            new_feedback = request.form.get(feedback_key, '').strip()

            if new_score is not None:
                # Clamp score between 0 and max_score
                answer.score = max(0, min(answer.max_score, new_score))

            # Update feedback if provided (for open questions)
            if new_feedback and answer.question.question_type == 'open':
                answer.ai_feedback = new_feedback

            total_score += answer.score

        # Update total score and admin comment
        response.total_score = total_score
        response.admin_comment = request.form.get('admin_comment', '').strip() or None
        if response.grading_status == QuizResponse.STATUS_REVIEW:
            response.grading_status = QuizResponse.STATUS_COMPLETED  # the instructor has now graded it
        db.session.commit()

        flash(_l('Scores mis a jour pour %(name)s', name=user.full_name), 'success')
        return redirect(url_for('admin.quiz_results', identifier=quiz.get_url_identifier()))

    return render_template('admin/edit_response.html',
                          response=response,
                          quiz=quiz,
                          user=user,
                          answers=answers)


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
