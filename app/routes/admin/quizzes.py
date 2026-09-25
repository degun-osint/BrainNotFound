"""Quizzes: list, creation, edition, test, duplication, images, AI generator."""
import os
import shutil
import uuid
import re
from flask import (
    render_template,
    redirect,
    url_for,
    flash,
    request,
    jsonify,
    current_app,
    send_from_directory,
    abort,
)
from flask_login import login_required, current_user
from flask_babel import lazy_gettext as _l
from werkzeug.utils import secure_filename
from app import db
from app.models.user import User, user_groups
from app.models.group import Group
from app.models.quiz import Quiz, Question, QuizResponse, Answer
from app.models.tenant import Tenant
from app.utils.markdown_parser import parse_quiz_markdown, validate_quiz_data
from app.utils.quiz_generator import ContentExtractor, generate_quiz_from_content
from app.utils.scope import (
    get_tenant_context,
    scoped_groups,
    scoped_quizzes,
    validate_group_ids,
    assign_groups,
    default_tenant_id,
    quota_tenant,
    filter_content_status,
    CONTENT_STATUSES,
    assign_graders,
)
from datetime import datetime
from io import BytesIO
from app.routes.admin import admin_bp
from app.routes.admin.common import admin_required, allowed_image_file, validate_slug


@admin_bp.route('/quizzes')
@login_required
@admin_required
def quiz_list():
    """Dedicated quiz list page."""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search = request.args.get('search', '', type=str).strip()
    filter_group_id = request.args.get('group', 0, type=int)
    status = request.args.get('status', '')

    query = filter_content_status(scoped_quizzes(), Quiz, status)
    if search:
        query = query.filter(Quiz.title.ilike(f'%{search}%'))
    if filter_group_id > 0:
        query = query.filter(Quiz.groups.any(Group.id == filter_group_id))

    quizzes = query.order_by(Quiz.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    return render_template(
        'admin/quizzes.html',
        quizzes=quizzes,
        search=search,
        all_groups=scoped_groups().all(),
        filter_group_id=filter_group_id,
        status=status if status in CONTENT_STATUSES else '',
    )


def read_grading_mode(form):
    """Grading mode and contest delay from the quiz form."""
    mode = form.get('grading_mode')
    days = form.get('contest_days', type=int)
    return {
        'grading_mode': mode if mode in (Quiz.GRADING_DIRECT, Quiz.GRADING_REVIEW) else Quiz.GRADING_DIRECT,
        'contest_days': max(0, min(365, days)) if days is not None else 7,
        'notify_learners': form.get('notify_learners') == 'on',
    }


@admin_bp.route('/quiz/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_quiz():
    tenant_ctx = get_tenant_context()
    groups = scoped_groups().all()

    if request.method == 'POST':
        markdown_content = request.form.get('markdown_content')
        time_limit = request.form.get('time_limit_minutes')
        available_from_str = request.form.get('available_from')
        available_until_str = request.form.get('available_until')
        grading_severity = request.form.get('grading_severity', 'modere')
        grading_mood = request.form.getlist('grading_mood')
        group_ids = request.form.getlist('group_ids')
        randomize_questions = request.form.get('randomize_questions') == 'on'
        randomize_options = request.form.get('randomize_options') == 'on'
        one_question_per_page = request.form.get('one_question_per_page') == 'on'
        custom_slug = request.form.get('slug', '').strip() or None

        # Keep only groups in scope; non-superadmins (or any admin with a context) must pick one
        selected_groups = validate_group_ids(group_ids)
        if not selected_groups and (not current_user.is_superadmin or tenant_ctx):
            flash(_l('Vous devez assigner le quiz a au moins un groupe accessible'), 'error')
            return render_template('admin/create_quiz.html', groups=groups)
        group_ids = [str(g.id) for g in selected_groups]
        quiz_tenant_id = default_tenant_id(selected_groups)
        quiz_tenant = db.session.get(Tenant, quiz_tenant_id) if quiz_tenant_id else None
        if quiz_tenant and not quiz_tenant.can_add_quiz():
            flash(_l('Limite de quiz atteinte pour cet etablissement (%(max)s)', max=quiz_tenant.max_quizzes), 'error')
            return render_template('admin/create_quiz.html', groups=groups)

        # Parse dates
        available_from = None
        if available_from_str:
            try:
                available_from = datetime.strptime(available_from_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                pass

        available_until = None
        if available_until_str:
            try:
                available_until = datetime.strptime(available_until_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                pass

        if not markdown_content:
            flash(_l('Le contenu Markdown est requis'), 'error')
            return render_template('admin/create_quiz.html', groups=groups)

        try:
            # Parse markdown
            quiz_data = parse_quiz_markdown(markdown_content)

            if not quiz_data['questions']:
                flash(_l('Aucune question trouvee dans le Markdown'), 'error')
                return render_template('admin/create_quiz.html', markdown_content=markdown_content, groups=groups)

            # Validate quiz data
            validation = validate_quiz_data(quiz_data)

            # Show errors (block creation)
            for error in validation['errors']:
                flash(error, 'error')

            if not validation['valid']:
                return render_template('admin/create_quiz.html', markdown_content=markdown_content, groups=groups)

            # Show warnings (allow creation but inform admin)
            for warning in validation['warnings']:
                flash(warning, 'warning')

            # Validate slug format
            if custom_slug:
                slug_valid, slug_error = validate_slug(custom_slug)
                if not slug_valid:
                    flash(slug_error, 'error')
                    return render_template('admin/create_quiz.html', markdown_content=markdown_content, groups=groups)
                # Check slug uniqueness
                if Quiz.query.filter_by(slug=custom_slug).first():
                    flash(_l('Le slug "%(slug)s" est deja utilise', slug=custom_slug), 'error')
                    return render_template('admin/create_quiz.html', markdown_content=markdown_content, groups=groups)

            # Create quiz
            title = quiz_data['title'] or 'Sans titre'
            quiz = Quiz(
                title=title,
                slug=custom_slug,
                description=quiz_data.get('description', ''),
                markdown_content=markdown_content,
                is_active=True,
                randomize_questions=randomize_questions,
                randomize_options=randomize_options,
                one_question_per_page=one_question_per_page,
                time_limit_minutes=int(time_limit) if time_limit else None,
                available_from=available_from,
                available_until=available_until,
                grading_severity=grading_severity,
                grading_mood=grading_mood,
                **read_grading_mode(request.form),
                created_by_id=current_user.id,
                tenant_id=quiz_tenant_id  # Assign to tenant if applicable
            )
            db.session.add(quiz)
            db.session.flush()
            adopt_temp_uploads(quiz)
            assign_graders(quiz, request.form.getlist('grader_ids'))

            # Assign groups
            if group_ids:
                for gid in group_ids:
                    group = Group.query.get(int(gid))
                    if group:
                        quiz.groups.append(group)

            # Create questions
            for q_data in quiz_data['questions']:
                question = Question(
                    quiz_id=quiz.id,
                    question_type=q_data['question_type'],
                    question_text=q_data['question_text'],
                    points=q_data['points'],
                    order=q_data['order']
                )

                if q_data['question_type'] == 'mcq':
                    question.options = q_data['options']
                    question.correct_answers = q_data['correct_answers']
                    question.allow_multiple = q_data.get('allow_multiple', False)
                else:  # open
                    question.expected_answer = q_data.get('expected_answer', '')

                db.session.add(question)

            db.session.commit()
            flash(_l('Quiz "%(title)s" cree avec succes !', title=quiz.title), 'success')
            return redirect(url_for('admin.dashboard'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Quiz creation error: {str(e)}')
            flash(_l('Erreur lors de la creation du quiz. Verifiez le format Markdown.'), 'error')
            return render_template('admin/create_quiz.html', markdown_content=markdown_content, groups=groups)

    return render_template('admin/create_quiz.html', groups=groups)


def adopt_temp_uploads(quiz):
    """Move the images uploaded while creating the quiz into its own folder.

    Unreferenced leftovers older than a day are cleaned up.
    """
    import time
    root = current_app.config['UPLOAD_FOLDER']
    tmp_dir = os.path.join(root, f'quiz-tmp-{current_user.id}')
    if not os.path.isdir(tmp_dir):
        return
    referenced = set(re.findall(r'!\[[^\]]*\]\(([\w\-\.]+)\)', quiz.markdown_content or ''))
    dest_dir = os.path.join(root, f'quiz-{quiz.id}')
    for name in os.listdir(tmp_dir):
        path = os.path.join(tmp_dir, name)
        if name in referenced:
            os.makedirs(dest_dir, exist_ok=True)
            shutil.move(path, os.path.join(dest_dir, name))
        elif time.time() - os.path.getmtime(path) > 86400:
            os.remove(path)


@admin_bp.route('/quiz/<identifier>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_quiz(identifier):
    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        flash(_l('Quiz introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != quiz.get_url_identifier():
        return redirect(url_for('admin.edit_quiz', identifier=quiz.get_url_identifier()), code=301)

    # Check permission
    if not current_user.can_access_quiz(quiz):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return redirect(url_for('admin.dashboard'))

    groups = scoped_groups().all()
    admin_users = []
    if current_user.is_superadmin:
        # All admin users for author selection (superadmins + group admins)
        group_admin_ids = db.session.query(user_groups.c.user_id).filter(
            user_groups.c.role == 'admin'
        ).distinct().subquery()
        admin_users = User.query.filter(
            db.or_(
                User.is_admin == True,
                User.id.in_(group_admin_ids)
            )
        ).order_by(User.last_name, User.first_name, User.username).all()

    if request.method == 'POST':
        markdown_content = request.form.get('markdown_content')
        time_limit = request.form.get('time_limit_minutes')
        available_from_str = request.form.get('available_from')
        available_until_str = request.form.get('available_until')
        grading_severity = request.form.get('grading_severity', 'modere')
        grading_mood = request.form.getlist('grading_mood')
        group_ids = request.form.getlist('group_ids')
        randomize_questions = request.form.get('randomize_questions') == 'on'
        randomize_options = request.form.get('randomize_options') == 'on'
        one_question_per_page = request.form.get('one_question_per_page') == 'on'
        custom_slug = request.form.get('slug', '').strip() or None

        # Non-superadmins must keep at least one of their accessible groups
        if not current_user.is_superadmin and not validate_group_ids(group_ids):
            flash(_l('Le quiz doit rester assigne a au moins un de vos groupes'), 'error')
            return render_template('admin/edit_quiz.html', quiz=quiz, groups=groups, admin_users=admin_users)

        # Parse dates
        available_from = None
        if available_from_str:
            try:
                available_from = datetime.strptime(available_from_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                pass

        available_until = None
        if available_until_str:
            try:
                available_until = datetime.strptime(available_until_str, '%Y-%m-%dT%H:%M')
            except ValueError:
                pass

        try:
            # Parse markdown
            quiz_data = parse_quiz_markdown(markdown_content)

            # Validate quiz data
            validation = validate_quiz_data(quiz_data)

            # Show errors (block update)
            for error in validation['errors']:
                flash(error, 'error')

            if not validation['valid']:
                return render_template('admin/edit_quiz.html', quiz=quiz, groups=groups, admin_users=admin_users)

            # Show warnings (allow update but inform admin)
            for warning in validation['warnings']:
                flash(warning, 'warning')

            # Validate and check slug uniqueness if changed
            if custom_slug and custom_slug != quiz.slug:
                slug_valid, slug_error = validate_slug(custom_slug)
                if not slug_valid:
                    flash(slug_error, 'error')
                    return render_template('admin/edit_quiz.html', quiz=quiz, groups=groups, admin_users=admin_users)
                existing = Quiz.query.filter_by(slug=custom_slug).first()
                if existing and existing.id != quiz.id:
                    flash(_l('Le slug "%(slug)s" est deja utilise', slug=custom_slug), 'error')
                    return render_template('admin/edit_quiz.html', quiz=quiz, groups=groups, admin_users=admin_users)

            # Update quiz
            new_title = quiz_data['title'] or quiz.title
            quiz.title = new_title
            quiz.slug = custom_slug
            quiz.description = quiz_data.get('description', '')
            quiz.markdown_content = markdown_content
            quiz.randomize_questions = randomize_questions
            quiz.randomize_options = randomize_options
            quiz.one_question_per_page = one_question_per_page
            quiz.time_limit_minutes = int(time_limit) if time_limit else None
            quiz.available_from = available_from
            quiz.available_until = available_until
            quiz.grading_severity = grading_severity
            quiz.grading_mood = grading_mood
            for field, value in read_grading_mode(request.form).items():
                setattr(quiz, field, value)
            assign_graders(quiz, request.form.getlist('grader_ids'))
            quiz.updated_at = datetime.utcnow()

            # Allow superadmins to change the author
            if current_user.is_superadmin:
                new_author_id = request.form.get('created_by_id')
                if new_author_id:
                    quiz.created_by_id = int(new_author_id)

            # Update group assignments
            # Groups outside our scope (shared quiz) are kept as they are
            assign_groups(quiz.groups, group_ids)

            # Delete old questions and their answers (bulk delete doesn't cascade)
            old_questions = Question.query.filter_by(quiz_id=quiz.id).all()
            for old_q in old_questions:
                Answer.query.filter_by(question_id=old_q.id).delete()
            Question.query.filter_by(quiz_id=quiz.id).delete()

            # Create new questions
            for q_data in quiz_data['questions']:
                question = Question(
                    quiz_id=quiz.id,
                    question_type=q_data['question_type'],
                    question_text=q_data['question_text'],
                    points=q_data['points'],
                    order=q_data['order']
                )

                if q_data['question_type'] == 'mcq':
                    question.options = q_data['options']
                    question.correct_answers = q_data['correct_answers']
                    question.allow_multiple = q_data.get('allow_multiple', False)
                else:
                    question.expected_answer = q_data.get('expected_answer', '')

                db.session.add(question)

            db.session.commit()
            flash(_l('Quiz mis a jour avec succes !'), 'success')
            return redirect(url_for('admin.dashboard'))

        except Exception as e:
            db.session.rollback()
            current_app.logger.error(f'Quiz update error: {str(e)}')
            flash(_l('Erreur lors de la mise a jour. Verifiez le format Markdown.'), 'error')

    return render_template('admin/edit_quiz.html', quiz=quiz, groups=groups, admin_users=admin_users)


@admin_bp.route('/quiz/<identifier>/preview')
@login_required
@admin_required
def preview_quiz(identifier):
    """Preview a quiz as a student would see it (read-only)."""
    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        flash(_l('Quiz introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != quiz.get_url_identifier():
        return redirect(url_for('admin.preview_quiz', identifier=quiz.get_url_identifier()), code=301)

    # Check permission
    if not current_user.can_access_quiz(quiz):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return redirect(url_for('admin.dashboard'))

    questions = Question.query.filter_by(quiz_id=quiz.id).order_by(Question.order).all()

    # Check if admin already has a test response for this quiz
    existing_test = QuizResponse.query.filter_by(
        user_id=current_user.id,
        quiz_id=quiz.id,
        is_test=True
    ).first()

    return render_template('admin/preview_quiz.html',
                          quiz=quiz,
                          questions=questions,
                          is_preview=True,
                          existing_test=existing_test)


@admin_bp.route('/quiz/<identifier>/test', methods=['GET', 'POST'])
@login_required
@admin_required
def test_quiz(identifier):
    """Take a quiz in test mode (admin only)."""
    import json
    import random
    from flask import session
    from datetime import timedelta
    
    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        flash(_l('Quiz introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    quiz_id = quiz.id  # Keep for session keys compatibility

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != quiz.get_url_identifier():
        return redirect(url_for('admin.test_quiz', identifier=quiz.get_url_identifier()), code=301)

    # Check permission
    if not current_user.can_access_quiz(quiz):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return redirect(url_for('admin.dashboard'))

    questions = list(Question.query.filter_by(quiz_id=quiz.id).order_by(Question.order).all())

    # Delete any existing test response for this quiz
    existing_test = QuizResponse.query.filter_by(
        user_id=current_user.id,
        quiz_id=quiz.id,
        is_test=True
    ).first()
    if existing_test and request.method == 'GET':
        db.session.delete(existing_test)
        db.session.commit()

    # Randomize questions if enabled
    question_order_key = f'test_quiz_{quiz_id}_question_order'
    if quiz.randomize_questions:
        if question_order_key in session:
            order_map = session[question_order_key]
            questions = sorted(questions, key=lambda q: order_map.get(str(q.id), 0))
        else:
            question_ids = [q.id for q in questions]
            random.shuffle(question_ids)
            order_map = {str(qid): i for i, qid in enumerate(question_ids)}
            session[question_order_key] = order_map
            questions = sorted(questions, key=lambda q: order_map.get(str(q.id), 0))

    # Randomize MCQ options if enabled
    options_order_key = f'test_quiz_{quiz_id}_options_order'
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
        for question in questions:
            if question.question_type == 'mcq' and question.options:
                options_order[str(question.id)] = [i for i in range(len(question.options))]

    # Time tracking
    session_key = f'test_quiz_{quiz_id}_started_at'

    if request.method == 'POST':
        started_at_str = session.get(session_key)
        started_at = datetime.fromisoformat(started_at_str) if started_at_str else datetime.utcnow()
        now = datetime.utcnow()

        # Check if late
        is_late = False
        if quiz.time_limit_minutes:
            deadline = started_at + timedelta(minutes=quiz.time_limit_minutes)
            is_late = now > deadline

        # Get timing and focus data
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

        # Find open questions for grading
        open_questions = [q for q in questions if q.question_type == 'open']
        has_open_questions = len(open_questions) > 0

        # Create test quiz response
        quiz_response = QuizResponse(
            user_id=current_user.id,
            quiz_id=quiz.id,
            started_at=started_at,
            is_late=is_late,
            is_test=True,
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

        # Process answers
        for question in questions:
            max_score += question.points
            q_time = timing_data.get(str(question.id), 0)
            q_focus_lost = focus_data.get(str(question.id), 0)

            if question.question_type == 'mcq':
                selected = request.form.getlist(f'question_{question.id}')
                selected_indices = [int(i) for i in selected]

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

            else:  # open question
                answer_text = request.form.get(f'question_{question.id}', '').strip()

                answer = Answer(
                    quiz_response_id=quiz_response.id,
                    question_id=question.id,
                    answer_text=answer_text,
                    score=0.0,
                    max_score=question.points,
                    ai_feedback=None,
                    time_spent_seconds=q_time if q_time else None,
                    focus_lost_count=q_focus_lost
                )
                db.session.add(answer)
                db.session.flush()  # Get answer.id
                answers_to_grade.append({
                    'answer_id': answer.id,
                    'question_id': question.id
                })

        quiz_response.total_score = total_score
        quiz_response.max_score = max_score
        db.session.commit()

        # Clear session data
        for key in [session_key, question_order_key, options_order_key, f'test_quiz_{quiz_id}_progress']:
            session.pop(key, None)

        # Start async grading if needed
        if has_open_questions:
            quiz_response.grading_status = QuizResponse.STATUS_GRADING
            db.session.commit()
            from app.tasks import grade_quiz, run_task
            run_task(grade_quiz, quiz_response.id, answers_to_grade)
            return redirect(url_for('quiz.grading', identifier=quiz_response.get_url_identifier()))

        flash(_l('Test du quiz termine !'), 'success')
        return redirect(url_for('quiz.result', identifier=quiz_response.get_url_identifier()))

    # GET request - show the quiz
    if session_key not in session:
        session[session_key] = datetime.utcnow().isoformat()

    started_at_str = session.get(session_key)
    started_at = datetime.fromisoformat(started_at_str) if started_at_str else datetime.utcnow()

    remaining_seconds = None
    if quiz.time_limit_minutes:
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
                         is_test=True,
                         exam_mode=quiz.one_question_per_page,
                         exam_already_started=True)


@admin_bp.route('/quiz/<identifier>/delete', methods=['POST'])
@login_required
@admin_required
def delete_quiz(identifier):
    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        flash(_l('Quiz introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    quiz_id = quiz.id  # Keep for file operations

    # Check permission
    if not current_user.can_access_quiz(quiz):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Delete associated uploaded images
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], f'quiz-{quiz_id}')
    if os.path.isdir(upload_dir):
        try:
            shutil.rmtree(upload_dir)
            current_app.logger.info(f"Deleted upload directory: {upload_dir}")
        except Exception as e:
            current_app.logger.warning(f"Failed to delete upload directory {upload_dir}: {e}")

    db.session.delete(quiz)
    db.session.commit()
    flash(_l('Quiz supprime avec succes'), 'success')
    return redirect(url_for('admin.dashboard'))


@admin_bp.route('/quiz/<identifier>/duplicate', methods=['POST'])
@login_required
@admin_required
def duplicate_quiz(identifier):
    """Duplicate an existing quiz."""
    original = Quiz.get_by_identifier(identifier)
    if not original:
        flash(_l('Quiz introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Check permission
    if not current_user.can_access_quiz(original):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Copy group assignments (only accessible groups for non-superadmins)
    if current_user.is_superadmin:
        copied_groups = original.groups.all()
    else:
        accessible_group_ids = [g.id for g in current_user.get_accessible_groups()]
        copied_groups = [g for g in original.groups if g.id in accessible_group_ids]
    tenant_id = default_tenant_id(copied_groups) or original.tenant_id
    tenant = db.session.get(Tenant, tenant_id) if tenant_id else None
    if tenant and not tenant.can_add_quiz():
        flash(_l('Limite de quiz atteinte pour cet etablissement (%(max)s)', max=tenant.max_quizzes), 'error')
        return redirect(url_for('admin.quiz_list'))

    # Create new quiz with copied data
    new_title = f"{original.title} (copie)"
    new_quiz = Quiz(
        title=new_title,
        slug=None,  # No slug for copies, admin can add one later
        description=original.description,
        markdown_content=original.markdown_content,
        is_active=False,  # Disable by default to let admin review
        randomize_questions=original.randomize_questions,
        time_limit_minutes=original.time_limit_minutes,
        available_from=None,  # Reset availability dates
        available_until=None,
        grading_severity=original.grading_severity,
        grading_mood=original.grading_mood,
        grading_mode=original.grading_mode,
        contest_days=original.contest_days,
        notify_learners=original.notify_learners,
        created_by_id=current_user.id,  # New copy is created by current user
        tenant_id=tenant_id
    )
    db.session.add(new_quiz)
    db.session.flush()
    for group in copied_groups:
        new_quiz.groups.append(group)
    for grader in original.graders:
        new_quiz.graders.append(grader)

    # Copy questions
    for orig_q in original.questions.order_by(Question.order):
        new_q = Question(
            quiz_id=new_quiz.id,
            question_type=orig_q.question_type,
            question_text=orig_q.question_text,
            points=orig_q.points,
            order=orig_q.order,
            options=orig_q.options,
            correct_answers=orig_q.correct_answers,
            allow_multiple=orig_q.allow_multiple,
            expected_answer=orig_q.expected_answer,
            images=orig_q.images
        )
        db.session.add(new_q)

    db.session.commit()
    flash(_l('Quiz duplique ! Le nouveau quiz "%(title)s" est desactive par defaut.', title=new_quiz.title), 'success')
    return redirect(url_for('admin.edit_quiz', identifier=new_quiz.get_url_identifier()))


@admin_bp.route('/quiz/<identifier>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_quiz(identifier):
    quiz = Quiz.get_by_identifier(identifier)
    if not quiz:
        flash(_l('Quiz introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Check permission
    if not current_user.can_access_quiz(quiz):
        flash(_l('Vous n\'avez pas acces a ce quiz'), 'error')
        return redirect(url_for('admin.dashboard'))

    quiz.is_active = not quiz.is_active
    db.session.commit()
    status = 'activé' if quiz.is_active else 'désactivé'
    flash(_l('Quiz %(status)s', status=status), 'success')
    return redirect(url_for('admin.dashboard'))


# Image upload routes
ALLOWED_MIME_TYPES = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/gif': 'gif',
    'image/webp': 'webp'
}


def validate_image_mime(file_stream):
    """Validate image by checking magic bytes."""
    header = file_stream.read(12)
    file_stream.seek(0)  # Reset stream position

    # Check magic bytes
    if header[:8] == b'\x89PNG\r\n\x1a\n':
        return 'png'
    elif header[:3] == b'\xff\xd8\xff':
        return 'jpg'
    elif header[:6] in (b'GIF87a', b'GIF89a'):
        return 'gif'
    elif header[:4] == b'RIFF' and header[8:12] == b'WEBP':
        return 'webp'
    return None


@admin_bp.route('/quiz/upload-image', methods=['POST'])
@login_required
@admin_required
def upload_image():
    """Upload image for quiz questions."""
    if 'image' not in request.files:
        return jsonify({'error': 'Aucun fichier'}), 400

    file = request.files['image']
    quiz_ref = request.form.get('quiz_id', 'temp')
    if quiz_ref == 'temp':
        # Quiz being created: per-admin folder, moved into the quiz folder on creation
        folder, tenant = f'quiz-tmp-{current_user.id}', quota_tenant()
    else:
        quiz = db.session.get(Quiz, int(quiz_ref)) if quiz_ref.isdigit() else None
        if not quiz or not current_user.can_access_quiz(quiz):
            return jsonify({'error': 'Quiz introuvable'}), 403
        folder, tenant = f'quiz-{quiz.id}', quiz.tenant

    if file.filename == '':
        return jsonify({'error': 'Aucun fichier selectionne'}), 400

    if not allowed_image_file(file.filename):
        return jsonify({'error': 'Type de fichier non autorise (PNG, JPG, GIF, WEBP uniquement)'}), 400

    # Validate MIME type by checking magic bytes
    detected_ext = validate_image_mime(file.stream)
    if not detected_ext:
        return jsonify({'error': 'Fichier invalide: le contenu ne correspond pas a une image'}), 400

    file.stream.seek(0, os.SEEK_END)
    size = file.stream.tell()
    file.stream.seek(0)
    if tenant and not tenant.can_store(size):
        return jsonify({'error': str(_l('Espace de stockage de l\'etablissement plein (%(max)s Mo)',
                                        max=tenant.max_storage_mb))}), 413

    # Create upload directory
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], folder)
    os.makedirs(upload_dir, exist_ok=True)

    # Use detected extension for safety
    unique_filename = f"{uuid.uuid4().hex[:8]}.{detected_ext}"
    filepath = os.path.join(upload_dir, unique_filename)

    file.save(filepath)

    return jsonify({
        'success': True,
        'filename': unique_filename,
        'markdown': f'![image]({unique_filename})'
    })


@admin_bp.route('/uploads/quiz-<int:quiz_id>/<filename>')
@login_required
def serve_quiz_image(quiz_id, filename):
    """Serve uploaded quiz images."""
    # Permission check - verify user has access to this quiz
    quiz = Quiz.query.get(quiz_id)
    if quiz:
        if current_user.is_any_admin:
            # Admins must have explicit access to the quiz
            if not current_user.can_access_quiz(quiz):
                abort(403)
        else:
            # Regular users must have the quiz available to them
            if not quiz.is_available_for_user(current_user):
                abort(403)

    # Sanitize filename to prevent directory traversal
    filename = secure_filename(filename)
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], f'quiz-{quiz_id}')
    return send_from_directory(upload_dir, filename)


# Quiz Generator routes
@admin_bp.route('/quiz/generate', methods=['GET', 'POST'])
@login_required
@admin_required
def generate_quiz():
    """Generate a quiz from uploaded course material using AI."""
    groups = scoped_groups().all()

    if request.method == 'POST':
        # Get form data
        title = request.form.get('title', 'Quiz genere').strip()
        num_mcq = request.form.get('num_mcq', 5, type=int)
        num_open = request.form.get('num_open', 2, type=int)
        difficulty = request.form.get('difficulty', 'modere')
        instructions = request.form.get('instructions', '').strip()

        # Validate numbers
        num_mcq = max(0, min(20, num_mcq))
        num_open = max(0, min(10, num_open))

        if num_mcq + num_open == 0:
            flash(_l('Vous devez generer au moins une question'), 'error')
            return render_template('admin/generate_quiz.html', groups=groups)

        # Handle file upload
        if 'course_file' not in request.files:
            flash(_l('Veuillez selectionner un fichier'), 'error')
            return render_template('admin/generate_quiz.html', groups=groups)

        file = request.files['course_file']

        if file.filename == '':
            flash(_l('Aucun fichier selectionne'), 'error')
            return render_template('admin/generate_quiz.html', groups=groups)

        if not ContentExtractor.allowed_file(file.filename):
            flash(_l('Format de fichier non supporte (PDF, DOCX, MD, TXT uniquement)'), 'error')
            return render_template('admin/generate_quiz.html', groups=groups)

        try:
            # Extract content from file
            file_stream = BytesIO(file.read())
            content = ContentExtractor.extract(file_stream, file.filename)

            if not content or len(content.strip()) < 100:
                flash(_l('Le fichier ne contient pas assez de texte exploitable (minimum 100 caracteres)'), 'error')
                return render_template('admin/generate_quiz.html', groups=groups)

            tenant = quota_tenant()
            if tenant and not tenant.can_generate_quiz():
                flash(_l('Quota mensuel de generations IA atteint pour cet etablissement'), 'error')
                return render_template('admin/generate_quiz.html', groups=groups)

            # Generate quiz using Claude
            result = generate_quiz_from_content(
                content=content,
                title=title,
                num_mcq=num_mcq,
                num_open=num_open,
                difficulty=difficulty,
                instructions=instructions
            )

            if result['success']:
                if tenant:
                    tenant.increment_quiz_generations()
                # Render preview page with generated markdown
                return render_template('admin/generate_quiz_preview.html',
                                     generated_markdown=result['markdown'],
                                     title=title,
                                     groups=groups)
            else:
                flash(_l('Erreur lors de la generation: %(error)s', error=result.get("error", _l("Erreur inconnue"))), 'error')
                return render_template('admin/generate_quiz.html', groups=groups)

        except Exception as e:
            current_app.logger.error(f'Quiz generation error: {str(e)}')
            flash(_l('Erreur lors du traitement du fichier: %(error)s', error=str(e)), 'error')
            return render_template('admin/generate_quiz.html', groups=groups)

    return render_template('admin/generate_quiz.html', groups=groups)
