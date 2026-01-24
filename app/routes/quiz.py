from flask import Blueprint, render_template, redirect, url_for, flash, request, session, current_app, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timedelta
import random
import json
from app import db, socketio
from app.models.quiz import Quiz, Question, QuizResponse, Answer, quiz_groups
from app.models.group import Group
from app.models.tenant import Tenant
from app.models.interview import InterviewSession

quiz_bp = Blueprint('quiz', __name__)

@quiz_bp.route('/dashboard')
@login_required
def dashboard():
    """Student dashboard with stats, history, progress chart and to-do."""
    if current_user.is_any_admin:
        return redirect(url_for('admin.dashboard'))

    now = datetime.now()

    # Get all user responses ordered by date
    responses = QuizResponse.query.filter_by(user_id=current_user.id)\
        .order_by(QuizResponse.submitted_at.desc()).all()

    # Get user interview sessions
    interview_sessions = InterviewSession.query.filter_by(
        user_id=current_user.id,
        is_test=False
    ).order_by(InterviewSession.started_at.desc()).all()

    completed_interviews = [s for s in interview_sessions if s.status == 'completed']

    # Calculate statistics
    stats = {
        'quiz_count': len(responses),
        'interview_count': len(completed_interviews),
        'total_points': sum(r.total_score for r in responses),
        'max_possible_points': sum(r.max_score for r in responses),
        'average_percentage': 0.0,
        'total_evaluations': len(responses) + len(completed_interviews)
    }

    if stats['max_possible_points'] > 0:
        stats['average_percentage'] = (stats['total_points'] / stats['max_possible_points']) * 100

    # Calculate interview average
    interview_total = sum(s.total_score for s in completed_interviews)
    interview_max = sum(s.max_score for s in completed_interviews if s.max_score)
    stats['interview_average'] = (interview_total / interview_max * 100) if interview_max > 0 else 0

    # Combined average (quiz + interviews)
    combined_total = stats['total_points'] + interview_total
    combined_max = stats['max_possible_points'] + interview_max
    stats['combined_average'] = (combined_total / combined_max * 100) if combined_max > 0 else 0

    # Recent activity (last 5 items combined, sorted by date)
    recent_activity = []

    for r in responses[:10]:
        pct = (r.total_score / r.max_score * 100) if r.max_score > 0 else 0
        recent_activity.append({
            'type': 'quiz',
            'title': r.quiz.title,
            'score': r.total_score,
            'max_score': r.max_score,
            'percentage': pct,
            'date': r.submitted_at,
            'url': url_for('quiz.result', identifier=r.get_url_identifier())
        })

    for s in completed_interviews[:10]:
        recent_activity.append({
            'type': 'interview',
            'title': s.interview.title,
            'score': s.total_score,
            'max_score': s.max_score,
            'percentage': s.get_score_percentage(),
            'date': s.ended_at or s.started_at,
            'url': url_for('interview.result', identifier=s.get_url_identifier())
        })

    # Sort by date and take last 5
    recent_activity.sort(key=lambda x: x['date'], reverse=True)
    recent_activity = recent_activity[:5]

    # Progress data for chart (last 10 evaluations, oldest first)
    progress_data = []
    all_completed = []

    for r in responses:
        pct = (r.total_score / r.max_score * 100) if r.max_score > 0 else 0
        all_completed.append({
            'date': r.submitted_at,
            'percentage': pct,
            'label': r.quiz.title[:15]
        })

    for s in completed_interviews:
        all_completed.append({
            'date': s.ended_at or s.started_at,
            'percentage': s.get_score_percentage(),
            'label': s.interview.title[:15]
        })

    all_completed.sort(key=lambda x: x['date'])
    progress_data = all_completed[-10:]  # Last 10

    # To-do: Available quizzes not yet taken
    user_groups = list(current_user.groups)
    user_group_ids = [g.id for g in user_groups]
    completed_quiz_ids = [r.quiz_id for r in responses]

    available_quizzes = []
    if user_group_ids:
        quizzes_with_groups = db.session.query(quiz_groups.c.quiz_id).distinct()
        quiz_query = Quiz.query.filter(
            Quiz.is_active == True,
            db.or_(Quiz.available_from == None, Quiz.available_from <= now),
            db.or_(Quiz.available_until == None, Quiz.available_until >= now),
            ~Quiz.id.in_(completed_quiz_ids),
            db.or_(
                Quiz.groups.any(Group.id.in_(user_group_ids)),
                ~Quiz.id.in_(quizzes_with_groups)
            )
        ).order_by(
            db.case((Quiz.available_until.is_(None), 1), else_=0),
            Quiz.available_until.asc(),
            Quiz.created_at.desc()
        ).limit(5)
        available_quizzes = quiz_query.all()

    # To-do: Available interviews not yet taken
    from app.models.interview import Interview, interview_groups
    completed_interview_ids = [s.interview_id for s in interview_sessions]

    available_interviews = []
    if user_group_ids:
        interviews_with_groups = db.session.query(interview_groups.c.interview_id).distinct()
        interview_query = Interview.query.filter(
            Interview.is_active == True,
            db.or_(Interview.available_from == None, Interview.available_from <= now),
            db.or_(Interview.available_until == None, Interview.available_until >= now),
            ~Interview.id.in_(completed_interview_ids),
            db.or_(
                Interview.groups.any(Group.id.in_(user_group_ids)),
                ~Interview.id.in_(interviews_with_groups)
            )
        ).order_by(
            db.case((Interview.available_until.is_(None), 1), else_=0),
            Interview.available_until.asc(),
            Interview.created_at.desc()
        ).limit(5)
        available_interviews = interview_query.all()

    return render_template(
        'quiz/dashboard.html',
        responses=responses,
        stats=stats,
        interview_sessions=interview_sessions,
        recent_activity=recent_activity,
        progress_data=progress_data,
        available_quizzes=available_quizzes,
        available_interviews=available_interviews
    )

@quiz_bp.route('/list')
@login_required
def quiz_list():
    if current_user.is_any_admin:
        return redirect(url_for('admin.dashboard'))

    now = datetime.now()
    from app.models.quiz import quiz_groups

    # Get filter parameters
    filter_group_id = request.args.get('group', 0, type=int)
    filter_tenant_id = request.args.get('tenant', 0, type=int)

    # Get user's groups and tenants for filter dropdowns
    user_groups = list(current_user.groups)
    user_group_ids = [g.id for g in user_groups]

    # Get unique tenants from user's groups
    user_tenant_ids = set(g.tenant_id for g in user_groups if g.tenant_id)
    user_tenants = Tenant.query.filter(Tenant.id.in_(user_tenant_ids)).order_by(Tenant.name).all() if user_tenant_ids else []

    # Get active quizzes that are available (time window check)
    base_query = Quiz.query.filter(
        Quiz.is_active == True,
        db.or_(Quiz.available_from == None, Quiz.available_from <= now),
        db.or_(Quiz.available_until == None, Quiz.available_until >= now)
    )

    # Filter by user's groups - show quizzes assigned to any of user's groups OR quizzes with no group assignment
    if user_group_ids:
        # Subquery to get quiz IDs that have ANY group assigned
        quizzes_with_groups = db.session.query(quiz_groups.c.quiz_id).distinct()

        # Quizzes assigned to any of user's groups OR quizzes with no groups (available to all)
        base_query = base_query.filter(
            db.or_(
                Quiz.groups.any(Group.id.in_(user_group_ids)),
                ~Quiz.id.in_(quizzes_with_groups)
            )
        )
    else:
        # User without groups - show only quizzes with no group restriction
        quizzes_with_groups = db.session.query(quiz_groups.c.quiz_id).distinct()
        base_query = base_query.filter(
            ~Quiz.id.in_(quizzes_with_groups)
        )

    # Apply group filter if selected
    if filter_group_id > 0 and filter_group_id in user_group_ids:
        base_query = base_query.filter(Quiz.groups.any(Group.id == filter_group_id))

    # Apply tenant filter if selected
    if filter_tenant_id > 0 and filter_tenant_id in user_tenant_ids:
        # Get groups from this tenant that the user belongs to
        tenant_group_ids = [g.id for g in user_groups if g.tenant_id == filter_tenant_id]
        if tenant_group_ids:
            base_query = base_query.filter(
                db.or_(
                    Quiz.tenant_id == filter_tenant_id,
                    Quiz.groups.any(Group.id.in_(tenant_group_ids))
                )
            )

    quizzes = base_query.order_by(Quiz.created_at.desc()).all()

    # Get user's responses
    user_responses = {}
    for quiz in quizzes:
        response = QuizResponse.query.filter_by(
            user_id=current_user.id,
            quiz_id=quiz.id
        ).first()
        if response:
            user_responses[quiz.id] = response

    return render_template(
        'quiz/list.html',
        quizzes=quizzes,
        user_responses=user_responses,
        user_groups=user_groups,
        user_tenants=user_tenants,
        filter_group_id=filter_group_id,
        filter_tenant_id=filter_tenant_id
    )

@quiz_bp.route('/<identifier>')
@login_required
def quiz_by_slug(identifier):
    """Access a quiz by its uid, slug, or ID - redirects to take."""
    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        flash('Quiz introuvable', 'error')
        return redirect(url_for('quiz.quiz_list'))
    return redirect(url_for('quiz.take', identifier=quiz.get_url_identifier()))


@quiz_bp.route('/<identifier>/take', methods=['GET', 'POST'])
@login_required
def take(identifier):
    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        flash('Quiz introuvable', 'error')
        return redirect(url_for('quiz.quiz_list'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != quiz.get_url_identifier():
        return redirect(url_for('quiz.take', identifier=quiz.get_url_identifier()), code=301)

    quiz_id = quiz.id  # Keep for session keys compatibility
    now = datetime.now()

    if not quiz.is_active:
        flash('Ce quiz n\'est plus disponible', 'error')
        return redirect(url_for('quiz.quiz_list'))

    # Check availability window
    if quiz.available_from and quiz.available_from > now:
        flash('Ce quiz n\'est pas encore disponible', 'error')
        return redirect(url_for('quiz.quiz_list'))

    if quiz.available_until and quiz.available_until < now:
        flash('Ce quiz est fermé', 'error')
        return redirect(url_for('quiz.quiz_list'))

    # Check group permission - quiz must be available for at least one of user's groups
    if not quiz.is_available_for_user(current_user):
        flash('Ce quiz n\'est pas disponible pour vos groupes', 'error')
        return redirect(url_for('quiz.quiz_list'))

    # Check if user already submitted
    existing_response = QuizResponse.query.filter_by(
        user_id=current_user.id,
        quiz_id=quiz.id
    ).first()

    if existing_response:
        flash('Vous avez déjà répondu à ce quiz', 'info')
        return redirect(url_for('quiz.result', identifier=existing_response.get_url_identifier()))

    questions = Question.query.filter_by(quiz_id=quiz.id).order_by(Question.order).all()

    # Randomize questions if enabled - use session to maintain consistent order for user
    question_order_key = f'quiz_{quiz_id}_question_order'
    if quiz.randomize_questions:
        if question_order_key in session:
            # Restore saved order
            order_map = session[question_order_key]
            questions = sorted(questions, key=lambda q: order_map.get(str(q.id), 0))
        else:
            # Create new random order and save it
            question_ids = [q.id for q in questions]
            random.shuffle(question_ids)
            order_map = {str(qid): i for i, qid in enumerate(question_ids)}
            session[question_order_key] = order_map
            questions = sorted(questions, key=lambda q: order_map.get(str(q.id), 0))

    # Randomize MCQ options if enabled - store mapping in session
    options_order_key = f'quiz_{quiz_id}_options_order'
    options_order = {}
    if quiz.randomize_options:
        if options_order_key in session:
            options_order = session[options_order_key]
        else:
            for question in questions:
                if question.question_type == 'mcq' and question.options:
                    indices = [i for i in range(len(question.options))]
                    random.shuffle(indices)
                    options_order[str(question.id)] = indices
            session[options_order_key] = options_order
    else:
        # Default order (no shuffle)
        for question in questions:
            if question.question_type == 'mcq' and question.options:
                options_order[str(question.id)] = [i for i in range(len(question.options))]

    # Time tracking with session
    session_key = f'quiz_{quiz_id}_started_at'

    if request.method == 'POST':
        # Get start time from session
        started_at_str = session.get(session_key)
        started_at = datetime.fromisoformat(started_at_str) if started_at_str else datetime.utcnow()
        now = datetime.utcnow()

        # Check if submission is late
        is_late = False
        if quiz.time_limit_minutes:
            deadline = started_at + timedelta(minutes=quiz.time_limit_minutes)
            is_late = now > deadline

        # Get timing and focus data from form (sent by exam-mode.js)
        timing_data = {}
        focus_data = {}
        focus_events = []
        total_focus_lost = 0

        try:
            timing_data_str = request.form.get('timing_data', '{}')
            timing_data = json.loads(timing_data_str) if timing_data_str else {}
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            focus_data_str = request.form.get('focus_data', '{}')
            focus_data = json.loads(focus_data_str) if focus_data_str else {}
            total_focus_lost = sum(focus_data.values()) if focus_data else 0
        except (json.JSONDecodeError, TypeError):
            pass

        try:
            focus_events_str = request.form.get('focus_events', '[]')
            focus_events = json.loads(focus_events_str) if focus_events_str else []
        except (json.JSONDecodeError, TypeError):
            pass

        # Server-side suspicious activity detection
        suspicious_flags = []

        # 1. Check for suspiciously fast completion
        total_duration = (now - started_at).total_seconds()
        min_expected_time = len(questions) * 10  # At least 10 seconds per question
        if total_duration < min_expected_time:
            suspicious_flags.append({
                'type': 'fast_completion',
                'detail': f'Completed in {int(total_duration)}s, expected at least {min_expected_time}s'
            })

        # 2. Check for security events in focus_events
        security_events = [e for e in focus_events if e.get('event_type', '').endswith('_blocked') or
                          e.get('event_type') in ['devtools_detected', 'paste_detected']]
        if len(security_events) > 5:
            suspicious_flags.append({
                'type': 'many_security_events',
                'detail': f'{len(security_events)} security events detected',
                'events': security_events[:10]  # Keep first 10
            })

        # 3. Check for suspiciously fast individual answers
        fast_answers = []
        for q in questions:
            q_time = timing_data.get(str(q.id), 0)
            # MCQ should take at least 3 seconds, open questions at least 10
            min_time = 3 if q.question_type == 'mcq' else 10
            if q_time > 0 and q_time < min_time:
                fast_answers.append({
                    'question_id': q.id,
                    'time': q_time,
                    'min_expected': min_time
                })
        if fast_answers:
            suspicious_flags.append({
                'type': 'fast_answers',
                'detail': f'{len(fast_answers)} questions answered suspiciously fast',
                'questions': fast_answers
            })

        # Store suspicious flags in focus_events for analysis
        if suspicious_flags:
            focus_events.append({
                'event_type': 'server_suspicious_flags',
                'timestamp': now.isoformat(),
                'flags': suspicious_flags
            })

        # Count open questions that need AI grading
        open_questions = [q for q in questions if q.question_type == 'open']
        has_open_questions = len(open_questions) > 0

        # Create quiz response with time tracking
        quiz_response = QuizResponse(
            user_id=current_user.id,
            quiz_id=quiz.id,
            started_at=started_at,
            is_late=is_late,
            grading_status=QuizResponse.STATUS_PENDING if has_open_questions else QuizResponse.STATUS_COMPLETED,
            grading_total=len(open_questions),
            focus_events=focus_events if focus_events else None,
            total_focus_lost=total_focus_lost
        )
        db.session.add(quiz_response)
        db.session.flush()

        total_score = 0.0
        max_score = 0.0
        answers_to_grade = []

        # Process answers - MCQs are graded immediately, open questions saved for async grading
        for question in questions:
            max_score += question.points

            # Get timing and focus data for this question
            q_time = timing_data.get(str(question.id), 0)
            q_focus_lost = focus_data.get(str(question.id), 0)

            if question.question_type == 'mcq':
                # Get selected options
                selected = request.form.getlist(f'question_{question.id}')
                selected_indices = [int(i) for i in selected]

                # Grade MCQ immediately
                correct_set = set(question.correct_answers)
                selected_set = set(selected_indices)

                if correct_set == selected_set:
                    score = question.points
                else:
                    score = 0.0

                answer = Answer(
                    quiz_response_id=quiz_response.id,
                    question_id=question.id,
                    selected_options=selected_indices,
                    score=score,
                    max_score=question.points,
                    time_spent_seconds=q_time if q_time else None,
                    focus_lost_count=q_focus_lost
                )
                db.session.add(answer)
                total_score += score

            else:  # open question - save for async grading
                answer_text = request.form.get(f'question_{question.id}', '').strip()

                answer = Answer(
                    quiz_response_id=quiz_response.id,
                    question_id=question.id,
                    answer_text=answer_text,
                    score=0.0,  # Will be updated by async grading
                    max_score=question.points,
                    ai_feedback=None,  # Will be updated by async grading
                    time_spent_seconds=q_time if q_time else None,
                    focus_lost_count=q_focus_lost
                )
                db.session.add(answer)
                db.session.flush()

                # Add to list for async grading
                answers_to_grade.append({
                    'answer_id': answer.id,
                    'question_id': question.id
                })

        # Update quiz response totals (MCQ score only for now)
        quiz_response.total_score = total_score
        quiz_response.max_score = max_score

        db.session.commit()

        # Clean up session
        session.pop(session_key, None)
        session.pop(question_order_key, None)
        session.pop(options_order_key, None)

        # Start async grading if there are open questions
        if has_open_questions:
            from app.utils.grading_tasks import grade_quiz_async
            socketio.start_background_task(
                grade_quiz_async,
                current_app._get_current_object(),
                quiz_response.id,
                answers_to_grade
            )
            return redirect(url_for('quiz.grading', identifier=quiz_response.get_url_identifier()))
        else:
            flash('Quiz soumis avec succes !', 'success')
            return redirect(url_for('quiz.result', identifier=quiz_response.get_url_identifier()))

    # GET request - start or continue quiz
    exam_already_started = session_key in session
    if not exam_already_started:
        session[session_key] = datetime.utcnow().isoformat()

    # Calculate remaining time for template
    remaining_seconds = None
    if quiz.time_limit_minutes:
        started_at = datetime.fromisoformat(session[session_key])
        elapsed = (datetime.utcnow() - started_at).total_seconds()
        remaining_seconds = max(0, int((quiz.time_limit_minutes * 60) - elapsed))

    # Choose template based on exam mode
    template_name = 'quiz/take_exam.html' if quiz.one_question_per_page else 'quiz/take.html'

    return render_template(template_name,
                         quiz=quiz,
                         questions=questions,
                         remaining_seconds=remaining_seconds,
                         time_limit_minutes=quiz.time_limit_minutes,
                         options_order=options_order,
                         exam_mode=quiz.one_question_per_page,
                         exam_already_started=exam_already_started)

@quiz_bp.route('/<identifier>/start-exam', methods=['POST'])
@login_required
def start_exam(identifier):
    """Start the exam - sets session flag and redirects to exam page."""
    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        flash('Quiz introuvable', 'error')
        return redirect(url_for('quiz.quiz_list'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != quiz.get_url_identifier():
        return redirect(url_for('quiz.start_exam', identifier=quiz.get_url_identifier()), code=301)

    if not quiz.is_active:
        flash('Ce quiz n\'est plus disponible', 'error')
        return redirect(url_for('quiz.quiz_list'))

    if not quiz.is_available_for_user(current_user):
        flash('Ce quiz n\'est pas disponible pour vos groupes', 'error')
        return redirect(url_for('quiz.quiz_list'))

    # Check if user already submitted
    existing_response = QuizResponse.query.filter_by(
        user_id=current_user.id,
        quiz_id=quiz.id
    ).first()
    if existing_response:
        flash('Vous avez déjà répondu à ce quiz', 'info')
        return redirect(url_for('quiz.result', identifier=existing_response.get_url_identifier()))

    # Set the session flag to mark exam as started
    session_key = f'quiz_{quiz.id}_started_at'
    if session_key not in session:
        session[session_key] = datetime.utcnow().isoformat()

    return redirect(url_for('quiz.take', identifier=quiz.get_url_identifier()))


@quiz_bp.route('/<identifier>/save-progress', methods=['POST'])
@login_required
def save_progress(identifier):
    """Auto-save answer progress during exam mode (AJAX endpoint)."""
    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        return jsonify({'error': 'Quiz not found'}), 404

    quiz_id = quiz.id  # Keep for session keys compatibility

    # Verify user can access this quiz (student in group OR admin with access)
    is_student_access = quiz.is_available_for_user(current_user)
    is_admin_test = current_user.is_any_admin and current_user.can_access_quiz(quiz)
    if not is_student_access and not is_admin_test:
        return jsonify({'error': 'Unauthorized'}), 403

    # Check if user already submitted (ignore test responses for admins)
    existing_response = QuizResponse.query.filter_by(
        user_id=current_user.id,
        quiz_id=quiz.id,
        is_test=False
    ).first()
    if existing_response and not is_admin_test:
        return jsonify({'error': 'Already submitted'}), 400

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data'}), 400

    # Store progress in session
    progress_key = f'quiz_{quiz_id}_progress'
    progress = session.get(progress_key, {})

    question_id = str(data.get('question_id'))
    if question_id:
        progress[question_id] = {
            'answer': data.get('answer'),
            'time_spent': data.get('time_spent', 0),
            'focus_lost': data.get('focus_lost', 0)
        }
        session[progress_key] = progress

    return jsonify({'status': 'saved', 'question_id': question_id})


@quiz_bp.route('/result/<identifier>')
@login_required
def result(identifier):
    quiz_response = QuizResponse.get_by_identifier(identifier)
    if not quiz_response:
        flash('Resultat introuvable', 'error')
        return redirect(url_for('quiz.quiz_list'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != quiz_response.get_url_identifier():
        return redirect(url_for('quiz.result', identifier=quiz_response.get_url_identifier()), code=301)

    # Check ownership or admin access
    is_owner = quiz_response.user_id == current_user.id
    is_admin_with_access = current_user.is_any_admin and current_user.can_access_quiz(quiz_response.quiz)
    if not is_owner and not is_admin_with_access:
        flash('Accès non autorisé', 'error')
        return redirect(url_for('quiz.quiz_list'))

    answers = Answer.query.filter_by(quiz_response_id=quiz_response.id).all()

    # Organize answers by question
    answers_by_question = {}
    for answer in answers:
        answers_by_question[answer.question_id] = answer

    questions = Question.query.filter_by(quiz_id=quiz_response.quiz_id).order_by(Question.order).all()

    return render_template('quiz/result.html',
                         quiz_response=quiz_response,
                         questions=questions,
                         answers_by_question=answers_by_question)


@quiz_bp.route('/grading/<identifier>')
@login_required
def grading(identifier):
    """Show grading progress page with WebSocket updates."""
    quiz_response = QuizResponse.get_by_identifier(identifier)
    if not quiz_response:
        flash('Resultat introuvable', 'error')
        return redirect(url_for('quiz.quiz_list'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != quiz_response.get_url_identifier():
        return redirect(url_for('quiz.grading', identifier=quiz_response.get_url_identifier()), code=301)

    # Check ownership or admin access
    is_owner = quiz_response.user_id == current_user.id
    is_admin_with_access = current_user.is_any_admin and current_user.can_access_quiz(quiz_response.quiz)
    if not is_owner and not is_admin_with_access:
        flash('Acces non autorise', 'error')
        return redirect(url_for('quiz.quiz_list'))

    # If grading is already completed, redirect to results
    if quiz_response.grading_status == QuizResponse.STATUS_COMPLETED:
        return redirect(url_for('quiz.result', identifier=quiz_response.get_url_identifier()))

    return render_template('quiz/grading.html', quiz_response=quiz_response)


@quiz_bp.route('/grading-status/<identifier>')
@login_required
def grading_status(identifier):
    """API endpoint to check grading status (fallback for WebSocket)."""
    quiz_response = QuizResponse.get_by_identifier(identifier)
    if not quiz_response:
        return jsonify({'error': 'Not found'}), 404

    # Check ownership or admin access
    is_owner = quiz_response.user_id == current_user.id
    is_admin_with_access = current_user.is_any_admin and current_user.can_access_quiz(quiz_response.quiz)
    if not is_owner and not is_admin_with_access:
        return jsonify({'error': 'Unauthorized'}), 403

    return jsonify({
        'status': quiz_response.grading_status,
        'progress': quiz_response.grading_progress,
        'total': quiz_response.grading_total,
        'total_score': quiz_response.total_score,
        'max_score': quiz_response.max_score
    })
