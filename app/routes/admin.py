from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app, send_from_directory, send_file, abort
from flask_login import login_required, current_user
from flask_babel import lazy_gettext as _l
from functools import wraps
from werkzeug.utils import secure_filename
from urllib.parse import urlparse
import os
import shutil
import tempfile
import uuid
from app import db, csrf
from app.models.user import User, user_groups
from app.models.group import Group
from app.models.quiz import Quiz, Question, QuizResponse, Answer, quiz_groups
from app.models.tenant import Tenant, tenant_admins
from app.models.interview import Interview, InterviewSession
from app.utils.markdown_parser import parse_quiz_markdown, validate_quiz_data
from app.utils.quiz_generator import ContentExtractor, generate_quiz_from_content
from app.utils.email_sender import send_verification_email
from app.utils.prompt_loader import get_fallback_warnings, is_using_fallback
from app.utils.scope import (
    get_tenant_context, get_accessible_tenants, set_tenant_context as set_scope_tenant,
    scoped_groups, scoped_group_ids, scoped_quizzes, scoped_interviews, scoped_users,
    scoped_user_ids, validate_group_ids, assign_groups, default_tenant_id, quota_tenant,
)
from datetime import datetime
from io import BytesIO
import unicodedata
import re

ALLOWED_IMAGE_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}


def sanitize_filename(text):
    """Sanitize text for use in HTTP Content-Disposition filename header."""
    text = unicodedata.normalize('NFKD', text)
    text = text.encode('ascii', 'ignore').decode('ascii')
    text = re.sub(r'[^\w\s\-\.]', '', text)
    text = re.sub(r'[\s\-]+', '_', text)
    return text.strip('_')

def allowed_image_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS

import re

def validate_slug(slug):
    """Validate slug format - only allow safe URL characters."""
    if not slug:
        return True, None  # Empty slug is OK (optional)
    # Slug must be 3-100 chars, only lowercase letters, numbers, and hyphens
    # Must start and end with alphanumeric
    if len(slug) < 3:
        return False, 'Le slug doit contenir au moins 3 caracteres'
    if len(slug) > 100:
        return False, 'Le slug ne peut pas depasser 100 caracteres'
    if not re.match(r'^[a-z0-9][a-z0-9\-]*[a-z0-9]$', slug) and len(slug) > 2:
        return False, 'Le slug ne peut contenir que des lettres minuscules, chiffres et tirets'
    if '--' in slug:
        return False, 'Le slug ne peut pas contenir deux tirets consecutifs'
    return True, None


def safe_redirect_referrer(default_url):
    """
    Safely redirect to referrer if it's on the same host, otherwise to default.
    Prevents open redirect attacks.
    """
    referrer = request.referrer
    if referrer:
        ref_url = urlparse(request.host_url)
        test_url = urlparse(referrer)
        # Only allow same host redirects
        if test_url.netloc == ref_url.netloc:
            return redirect(referrer)
    return redirect(default_url)


admin_bp = Blueprint('admin', __name__)

def admin_required(f):
    """Require superadmin OR group admin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_any_admin:
            flash(_l('Acces non autorise'), 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def superadmin_required(f):
    """Require superadmin (full) access only."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or not current_user.is_superadmin:
            flash(_l('Acces reserve aux super-administrateurs'), 'error')
            return redirect(url_for('admin.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


# ==================== Tenant Context Management ====================

@admin_bp.context_processor
def inject_tenant_context():
    """Make tenant context available in all admin templates."""
    if current_user.is_authenticated and current_user.is_any_admin:
        tenant_context = get_tenant_context()
        accessible_tenants = get_accessible_tenants()
        return {
            'tenant_context': tenant_context,
            'accessible_tenants': accessible_tenants,
            'show_tenant_selector': len(accessible_tenants) > 0
        }
    return {
        'tenant_context': None,
        'accessible_tenants': [],
        'show_tenant_selector': False
    }


@admin_bp.route('/set-tenant-context/<identifier>')
@login_required
@admin_required
def set_tenant_context(identifier):
    """Set the tenant context filter."""
    tenant = Tenant.get_by_identifier(identifier)
    if not tenant:
        flash(_l('Tenant introuvable'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Verify access
    if not current_user.is_superadmin and not current_user.is_admin_of_tenant(tenant.id):
        flash(_l('Acces non autorise a ce tenant'), 'error')
        return redirect(url_for('admin.dashboard'))

    set_scope_tenant(tenant)
    flash(_l('Contexte: %(name)s', name=tenant.name), 'info')

    # Redirect back to referrer (validated) or dashboard
    return safe_redirect_referrer(url_for('admin.dashboard'))


@admin_bp.route('/clear-tenant-context')
@login_required
@admin_required
def clear_tenant_context():
    """Clear the tenant context filter (show all)."""
    set_scope_tenant(None)
    flash(_l('Contexte: Tous les tenants'), 'info')
    return safe_redirect_referrer(url_for('admin.dashboard'))


@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    page = request.args.get('page', 1, type=int)
    per_page = 10
    search = request.args.get('search', '', type=str).strip()
    filter_group_id = request.args.get('group', 0, type=int)

    all_groups = scoped_groups().all()

    query = scoped_quizzes()
    if search:
        query = query.filter(Quiz.title.ilike(f'%{search}%'))
    if filter_group_id > 0:
        query = query.filter(Quiz.groups.any(Group.id == filter_group_id))
    pagination = query.order_by(Quiz.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)

    quiz_ids = scoped_quizzes().with_entities(Quiz.id)
    interview_ids = scoped_interviews().with_entities(Interview.id)
    not_test = db.or_(QuizResponse.is_test == False, QuizResponse.is_test == None)  # noqa: E711,E712

    users_query = scoped_users()
    if current_user.is_superadmin and not get_tenant_context():
        users_query = users_query.filter(User.is_admin == False)  # noqa: E712

    stats = {
        'total_users': users_query.count(),
        'total_quizzes': scoped_quizzes().count(),
        'total_responses': QuizResponse.query.filter(QuizResponse.quiz_id.in_(quiz_ids)).count(),
        'total_groups': scoped_groups(active_only=False).count(),
        'total_interviews': scoped_interviews().count(),
    }

    recent_responses = QuizResponse.query.filter(
        QuizResponse.quiz_id.in_(quiz_ids), not_test
    ).order_by(QuizResponse.submitted_at.desc()).limit(5).all()

    pending_grading = QuizResponse.query.filter(
        QuizResponse.quiz_id.in_(quiz_ids),
        QuizResponse.grading_status.in_(['pending', 'grading'])
    ).count()

    recent_interviews = InterviewSession.query.filter(
        InterviewSession.interview_id.in_(interview_ids),
        InterviewSession.is_test == False  # noqa: E712
    ).order_by(InterviewSession.started_at.desc()).limit(5).all()

    # Get fallback warnings for superadmins (using default prompts/pages)
    fallback_warnings = []
    if current_user.is_superadmin and is_using_fallback():
        fallback_warnings = get_fallback_warnings()

    return render_template('admin/dashboard.html', quizzes=pagination.items, stats=stats, pagination=pagination,
                           search=search, all_groups=all_groups, filter_group_id=filter_group_id,
                           recent_responses=recent_responses, pending_grading=pending_grading,
                           fallback_warnings=fallback_warnings, recent_interviews=recent_interviews)


@admin_bp.route('/quizzes')
@login_required
@admin_required
def quiz_list():
    """Dedicated quiz list page."""
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search = request.args.get('search', '', type=str).strip()
    filter_group_id = request.args.get('group', 0, type=int)

    query = scoped_quizzes()
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
        filter_group_id=filter_group_id
    )


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
                created_by_id=current_user.id,
                tenant_id=quiz_tenant_id  # Assign to tenant if applicable
            )
            db.session.add(quiz)
            db.session.flush()

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
    from app.utils.grading_tasks import grade_quiz_async

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
            from app import socketio
            quiz_response.grading_status = QuizResponse.STATUS_GRADING
            db.session.commit()
            socketio.start_background_task(
                grade_quiz_async,
                current_app._get_current_object(),
                quiz_response.id,
                answers_to_grade
            )
            return redirect(url_for('quiz.grading', identifier=quiz_response.get_url_identifier()))

        flash(_l('Test du quiz termine !'), 'success')
        return redirect(url_for('quiz.result', response_id=quiz_response.id))

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
        created_by_id=current_user.id,  # New copy is created by current user
        tenant_id=tenant_id
    )
    db.session.add(new_quiz)
    db.session.flush()
    for group in copied_groups:
        new_quiz.groups.append(group)

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

@admin_bp.route('/users')
@login_required
@admin_required
def users():
    page = request.args.get('page', 1, type=int)
    per_page = 20
    search = request.args.get('search', '', type=str).strip()
    filter_group_id = request.args.get('group', 0, type=int)
    filter_role = request.args.get('role', '', type=str)
    sort_by = request.args.get('sort', 'created_at')
    sort_dir = request.args.get('dir', 'desc')

    # Validate sort and role parameters
    valid_sorts = ['full_name', 'username', 'email', 'created_at', 'last_login']
    valid_roles = ['', 'superadmin', 'tenant_admin', 'group_admin', 'user']
    if sort_by not in valid_sorts:
        sort_by = 'created_at'
    if sort_dir not in ['asc', 'desc']:
        sort_dir = 'desc'
    if filter_role not in valid_roles:
        filter_role = ''

    all_groups = scoped_groups().all()
    query = scoped_users()

    # Filter by selected group (using subquery to avoid JOIN conflicts)
    if filter_group_id > 0:
        users_in_group = db.session.query(user_groups.c.user_id).filter(
            user_groups.c.group_id == filter_group_id
        )
        query = query.filter(User.id.in_(users_in_group))

    if search:
        query = query.filter(
            db.or_(
                User.username.ilike(f'%{search}%'),
                User.email.ilike(f'%{search}%'),
                User.first_name.ilike(f'%{search}%'),
                User.last_name.ilike(f'%{search}%')
            )
        )

    # Filter by role (User.is_admin is the superadmin DB column)
    tenant_admin_ids = db.session.query(tenant_admins.c.user_id)
    group_admin_ids = db.session.query(user_groups.c.user_id).filter(user_groups.c.role == 'admin')
    if filter_role == 'superadmin':
        query = query.filter(User.is_admin == True)  # noqa: E712
    elif filter_role == 'tenant_admin':
        query = query.filter(User.is_admin == False, User.id.in_(tenant_admin_ids))  # noqa: E712
    elif filter_role == 'group_admin':
        query = query.filter(User.is_admin == False, User.id.in_(group_admin_ids),  # noqa: E712
                             ~User.id.in_(tenant_admin_ids))
    elif filter_role == 'user':
        query = query.filter(User.is_admin == False, ~User.id.in_(tenant_admin_ids),  # noqa: E712
                             ~User.id.in_(group_admin_ids))

    # Apply sorting (MySQL compatible - no NULLS LAST support)
    sort_column_map = {
        'full_name': User.last_name,
        'username': User.username,
        'email': User.email,
        'created_at': User.created_at,
        'last_login': User.last_login
    }
    sort_column = sort_column_map.get(sort_by, User.created_at)
    if sort_dir == 'asc':
        # For ASC, put NULLs at the end: ORDER BY col IS NULL, col ASC
        query = query.order_by(sort_column.is_(None), sort_column.asc())
    else:
        # For DESC, put NULLs at the end: ORDER BY col IS NULL, col DESC
        query = query.order_by(sort_column.is_(None), sort_column.desc())

    pagination = query.paginate(page=page, per_page=per_page, error_out=False)
    all_users = pagination.items
    return render_template('admin/users.html', users=all_users, pagination=pagination, search=search,
                          all_groups=all_groups, filter_group_id=filter_group_id,
                          filter_role=filter_role, sort_by=sort_by, sort_dir=sort_dir,
                          meta=users_list_meta(all_users))


def users_list_meta(users):
    """Groups, roles and permissions for a page of users, in 2 queries instead of ~5 per row.

    Returns {user_id: {'groups': [(group, role)], 'rank': int, 'can_manage': bool}}.
    """
    ids = [u.id for u in users]
    memberships = {uid: [] for uid in ids}
    tenant_admin_ids = set()
    if ids:
        rows = db.session.query(user_groups.c.user_id, Group, user_groups.c.role).join(
            Group, Group.id == user_groups.c.group_id
        ).filter(user_groups.c.user_id.in_(ids)).order_by(Group.name).all()
        for uid, group, role in rows:
            memberships[uid].append((group, role))
        tenant_admin_ids = {row[0] for row in db.session.query(tenant_admins.c.user_id).filter(
            tenant_admins.c.user_id.in_(ids))}
    meta = {}
    for u in users:
        groups = memberships[u.id]
        if u.is_admin:
            rank = 3
        elif u.id in tenant_admin_ids:
            rank = 2
        elif any(role == 'admin' for _, role in groups):
            rank = 1
        else:
            rank = 0
        meta[u.id] = {
            'groups': groups,
            'rank': rank,
            'can_manage': current_user.can_manage(u.id, rank, {g.id for g, _ in groups}),
        }
    return meta

# Group management routes - Superadmin and Tenant Admin
@admin_bp.route('/groups')
@login_required
@admin_required
def groups():
    all_groups = scoped_groups(active_only=False).order_by(None).order_by(Group.created_at.desc()).all()
    return render_template('admin/groups.html', groups=all_groups)

@admin_bp.route('/group/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_group():
    # Get available tenants for the current user
    if current_user.is_superadmin:
        tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.name).all()
    elif current_user.is_tenant_admin:
        tenants = list(current_user.admin_tenants.filter_by(is_active=True))
    else:
        # Group admins cannot create groups
        flash(_l('Vous n\'avez pas la permission de creer des groupes'), 'error')
        return redirect(url_for('admin.groups'))

    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description', '')
        max_members = request.form.get('max_members', 0, type=int)
        tenant_id = request.form.get('tenant_id', type=int)

        if not name:
            flash(_l('Le nom du groupe est requis'), 'error')
            return render_template('admin/create_group.html', tenants=tenants)

        # Validate tenant selection for non-superadmins
        if not current_user.is_superadmin:
            valid_tenant_ids = [t.id for t in tenants]
            if tenant_id and tenant_id not in valid_tenant_ids:
                flash(_l('Vous ne pouvez creer des groupes que dans vos tenants'), 'error')
                return render_template('admin/create_group.html', tenants=tenants)

        # Default to first available tenant if not specified
        if not tenant_id and tenants:
            tenant_id = tenants[0].id

        tenant = db.session.get(Tenant, tenant_id) if tenant_id else None
        if tenant and not tenant.can_add_group():
            flash(_l('Limite de groupes atteinte (%(max)s)', max=tenant.max_groups), 'error')
            return render_template('admin/create_group.html', tenants=tenants)

        # Generate unique join code
        join_code = Group.generate_join_code()

        group = Group(
            name=name,
            description=description,
            join_code=join_code,
            is_active=True,
            max_members=max(0, max_members),
            tenant_id=tenant_id
        )

        db.session.add(group)
        db.session.commit()

        flash(_l('Groupe "%(name)s" cree avec le code : %(code)s', name=name, code=join_code), 'success')
        return redirect(url_for('admin.groups'))

    return render_template('admin/create_group.html', tenants=tenants)

@admin_bp.route('/group/<identifier>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_group(identifier):
    group = Group.get_by_identifier(identifier)
    if not group:
        flash(_l('Groupe introuvable'), 'error')
        return redirect(url_for('admin.groups'))

    # Check permission
    if not current_user.can_access_group(group):
        flash(_l('Vous n\'avez pas acces a ce groupe'), 'error')
        return redirect(url_for('admin.groups'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != group.get_url_identifier():
        return redirect(url_for('admin.edit_group', identifier=group.get_url_identifier()), code=301)

    # Get available tenants for the current user
    if current_user.is_superadmin:
        tenants = Tenant.query.filter_by(is_active=True).order_by(Tenant.name).all()
    else:
        tenants = list(current_user.admin_tenants.filter_by(is_active=True))

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        tenant_id = request.form.get('tenant_id', type=int)

        if not name:
            flash(_l('Le nom du groupe est requis'), 'error')
            return render_template('admin/edit_group.html', group=group, tenants=tenants)

        # Moving a group is limited to the tenants we administer
        if tenant_id and tenant_id != group.tenant_id and tenant_id not in {t.id for t in tenants}:
            flash(_l('Acces non autorise a ce tenant'), 'error')
            return render_template('admin/edit_group.html', group=group, tenants=tenants)
        if tenant_id and tenant_id != group.tenant_id and not db.session.get(Tenant, tenant_id).can_add_group():
            flash(_l('Limite de groupes atteinte (%(max)s)', max=db.session.get(Tenant, tenant_id).max_groups), 'error')
            return render_template('admin/edit_group.html', group=group, tenants=tenants)

        group.name = name
        group.description = request.form.get('description', '')
        max_members = request.form.get('max_members', 0, type=int)
        group.max_members = max(0, max_members)
        if tenant_id:
            group.tenant_id = tenant_id
        db.session.commit()

        flash(_l('Groupe mis a jour avec succes'), 'success')
        return redirect(url_for('admin.groups'))

    return render_template('admin/edit_group.html', group=group, tenants=tenants)

@admin_bp.route('/group/<identifier>/toggle', methods=['POST'])
@login_required
@admin_required
def toggle_group(identifier):
    group = Group.get_by_identifier(identifier)
    if not group:
        flash(_l('Groupe introuvable'), 'error')
        return redirect(url_for('admin.groups'))

    # Check permission
    if not current_user.can_access_group(group):
        flash(_l('Vous n\'avez pas acces a ce groupe'), 'error')
        return redirect(url_for('admin.groups'))

    group.is_active = not group.is_active
    db.session.commit()

    status = 'activé' if group.is_active else 'désactivé'
    flash(_l('Groupe %(status)s', status=status), 'success')
    return redirect(url_for('admin.groups'))

@admin_bp.route('/group/<identifier>/delete', methods=['POST'])
@login_required
@admin_required
def delete_group(identifier):
    group = Group.get_by_identifier(identifier)
    if not group:
        flash(_l('Groupe introuvable'), 'error')
        return redirect(url_for('admin.groups'))

    # Check permission
    if not current_user.can_access_group(group):
        flash(_l('Vous n\'avez pas acces a ce groupe'), 'error')
        return redirect(url_for('admin.groups'))

    # Check if group has users (via new relationship)
    if group.members.count() > 0:
        flash(_l('Impossible de supprimer un groupe qui contient des utilisateurs'), 'error')
        return redirect(url_for('admin.groups'))

    db.session.delete(group)
    db.session.commit()

    flash(_l('Groupe supprime avec succes'), 'success')
    return redirect(url_for('admin.groups'))

@admin_bp.route('/group/<identifier>/users')
@login_required
@admin_required
def group_users(identifier):
    group = Group.get_by_identifier(identifier)
    if not group:
        flash(_l('Groupe introuvable'), 'error')
        return redirect(url_for('admin.groups'))

    group_id = group.id  # Keep for queries

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != group.get_url_identifier():
        return redirect(url_for('admin.group_users', identifier=group.get_url_identifier()), code=301)

    # Check permission for group admins
    if not current_user.is_superadmin and not current_user.is_admin_of_group(group_id):
        flash(_l('Vous n\'avez pas acces a ce groupe'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Get users from new many-to-many relationship
    users = User.query.join(user_groups).filter(
        user_groups.c.group_id == group_id
    ).order_by(User.created_at.desc()).all()
    response_counts = dict(db.session.query(QuizResponse.user_id, db.func.count(QuizResponse.id)).filter(
        QuizResponse.user_id.in_([u.id for u in users])
    ).group_by(QuizResponse.user_id).all()) if users else {}
    return render_template('admin/group_users.html', group=group, users=users, response_counts=response_counts)


@admin_bp.route('/group/<identifier>/export-results')
@login_required
@admin_required
def export_group_results(identifier):
    """Export quiz results for all users in a group as CSV."""
    import csv
    from io import StringIO
    from flask import Response

    group = Group.get_by_identifier(identifier)
    if not group:
        flash(_l('Groupe introuvable'), 'error')
        return redirect(url_for('admin.groups'))

    group_id = group.id  # Keep for queries

    # Check permission
    if not current_user.is_superadmin and not current_user.is_admin_of_group(group_id):
        flash(_l('Vous n\'avez pas acces a ce groupe'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Get all users in the group
    users = User.query.join(user_groups).filter(
        user_groups.c.group_id == group_id
    ).order_by(User.username).all()

    # Get quizzes available to this group
    group_quizzes = group.quizzes.order_by(Quiz.created_at).all()

    # If no specific quizzes assigned, get all quizzes with no group restriction
    if not group_quizzes:
        group_quizzes = Quiz.query.outerjoin(quiz_groups).filter(
            quiz_groups.c.quiz_id == None
        ).order_by(Quiz.created_at).all()

    # Build CSV
    output = StringIO()
    writer = csv.writer(output, delimiter=';')

    # Header row
    header = ['Utilisateur', 'Email']
    for quiz in group_quizzes:
        header.append(f'{quiz.title} (%)')
    header.append('Moyenne (%)')
    writer.writerow(header)

    # Data rows
    for user in users:
        row = [user.username, user.email or '']
        scores = []
        max_scores = []

        for quiz in group_quizzes:
            # Get user's response for this quiz (exclude test responses)
            # Handle both is_test=False and is_test=NULL (old responses)
            response = QuizResponse.query.filter(
                QuizResponse.user_id == user.id,
                QuizResponse.quiz_id == quiz.id,
                db.or_(QuizResponse.is_test == False, QuizResponse.is_test == None)
            ).first()

            if response and response.grading_status == 'completed':
                score = response.total_score
                max_score = response.max_score
                if max_score > 0:
                    percentage = (score / max_score) * 100
                    row.append(f'{percentage:.1f}')
                    scores.append(score)
                    max_scores.append(max_score)
                else:
                    row.append('-')
            elif response:
                row.append('En cours')
            else:
                row.append('Non fait')

        # Calculate average
        if scores and sum(max_scores) > 0:
            avg_percentage = (sum(scores) / sum(max_scores)) * 100
            row.append(f'{avg_percentage:.1f}%')
        else:
            row.append('-')

        writer.writerow(row)

    # Create response with UTF-8 BOM for Excel compatibility
    output.seek(0)
    filename = f'resultats_{sanitize_filename(group.name[:30])}_{datetime.utcnow().strftime("%Y%m%d")}.csv'

    # Add UTF-8 BOM for Excel to recognize encoding
    csv_content = '\ufeff' + output.getvalue()

    return Response(
        csv_content.encode('utf-8'),
        mimetype='text/csv; charset=utf-8',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@admin_bp.route('/group/<identifier>/email', methods=['GET', 'POST'])
@login_required
@admin_required
def email_group(identifier):
    """Send bulk email to all members of a group."""
    from app.utils.email_sender import send_bulk_email

    group = Group.get_by_identifier(identifier)
    if not group:
        flash(_l('Groupe introuvable'), 'error')
        return redirect(url_for('admin.groups'))

    group_id = group.id  # Keep for queries

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != group.get_url_identifier():
        return redirect(url_for('admin.email_group', identifier=group.get_url_identifier()), code=301)

    # Check permission
    if not current_user.is_superadmin and not current_user.is_admin_of_group(group_id):
        flash(_l('Vous n\'avez pas acces a ce groupe'), 'error')
        return redirect(url_for('admin.dashboard'))

    # Get all users in the group with email
    users = User.query.join(user_groups).filter(
        user_groups.c.group_id == group_id,
        User.email.isnot(None),
        User.email != ''
    ).all()

    if request.method == 'POST':
        subject = request.form.get('subject', '').strip()
        message = request.form.get('message', '').strip()

        if not subject or not message:
            flash(_l('Le sujet et le message sont requis'), 'error')
            return render_template('admin/email_group.html', group=group, users=users)

        if not users:
            flash(_l('Aucun utilisateur avec email dans ce groupe'), 'error')
            return render_template('admin/email_group.html', group=group, users=users)

        success, fail = send_bulk_email(users, subject, message)

        if success > 0:
            flash(_l('%(count)s email(s) envoye(s) avec succes', count=success), 'success')
        if fail > 0:
            flash(_l('%(count)s email(s) echoue(s)', count=fail), 'warning')

        return redirect(url_for('admin.group_users', identifier=group.get_url_identifier()))

    return render_template('admin/email_group.html', group=group, users=users)


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
    quiz_id = request.form.get('quiz_id', 'temp')

    if file.filename == '':
        return jsonify({'error': 'Aucun fichier selectionne'}), 400

    if not allowed_image_file(file.filename):
        return jsonify({'error': 'Type de fichier non autorise (PNG, JPG, GIF, WEBP uniquement)'}), 400

    # Validate MIME type by checking magic bytes
    detected_ext = validate_image_mime(file.stream)
    if not detected_ext:
        return jsonify({'error': 'Fichier invalide: le contenu ne correspond pas a une image'}), 400

    # Create upload directory
    upload_dir = os.path.join(current_app.config['UPLOAD_FOLDER'], f'quiz-{quiz_id}')
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

@admin_bp.route('/user/<identifier>/grades')
@login_required
@admin_required
def user_grades(identifier):
    """View all grades for a specific user."""
    user = User.get_by_identifier(identifier)
    if not user:
        flash(_l('Utilisateur introuvable'), 'error')
        return redirect(url_for('admin.users'))

    user_id = user.id  # Keep for queries

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != user.get_url_identifier():
        return redirect(url_for('admin.user_grades', identifier=user.get_url_identifier()), code=301)

    # Check permission
    if not current_user.is_superadmin and not current_user.can_access_user(user):
        flash(_l('Vous n\'avez pas acces a cet utilisateur'), 'error')
        return redirect(url_for('admin.users'))

    # Get all responses for this user
    responses = QuizResponse.query.filter_by(user_id=user_id)\
        .order_by(QuizResponse.submitted_at.desc()).all()

    # Filter responses for group admins - only show quizzes they can access
    if not current_user.is_superadmin:
        responses = [r for r in responses if current_user.can_access_quiz(r.quiz)]

    # Calculate statistics
    stats = {
        'quiz_count': len(responses),
        'total_points': sum(r.total_score for r in responses),
        'max_possible_points': sum(r.max_score for r in responses),
        'average_percentage': 0.0
    }

    if stats['max_possible_points'] > 0:
        stats['average_percentage'] = (stats['total_points'] / stats['max_possible_points']) * 100

    return render_template('admin/user_grades.html', user=user, responses=responses, stats=stats)

# User management routes
@admin_bp.route('/user/create', methods=['GET', 'POST'])
@login_required
@admin_required
def create_user():
    """Create a new user (admin or regular)."""
    groups = scoped_groups().all()
    tenants = get_accessible_tenants() if current_user.is_superadmin else []

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password')
        user_role = request.form.get('user_role', 'user')  # user, group_admin, tenant_admin, superadmin
        group_ids = request.form.getlist('group_ids')
        tenant_ids = request.form.getlist('tenant_ids')

        # Determine role flags from radio selection
        is_superadmin = (user_role == 'superadmin')
        is_tenant_admin = (user_role == 'tenant_admin')
        is_group_admin = (user_role == 'group_admin')

        # Only superadmins can create superadmins or tenant admins
        # Tenant admins can create group admins in their tenant
        if not current_user.is_superadmin:
            is_superadmin = False
            is_tenant_admin = False
            tenant_ids = []
            # Tenant admins can create group admins, group admins cannot
            if not current_user.is_tenant_admin:
                is_group_admin = False

        # Keep only groups in scope, and check they can take one more person
        selected_groups = validate_group_ids(group_ids)
        group_ids = [str(g.id) for g in selected_groups]
        join_errors = [f'{g.name} : {g.join_error()}' for g in selected_groups if g.join_error()]

        # Validation
        if join_errors and not is_superadmin and not is_tenant_admin:
            for error in join_errors:
                flash(error, 'error')
        elif not username or not email or not password:
            flash(_l('Nom d\'utilisateur, email et mot de passe sont requis'), 'error')
        elif User.query.filter_by(username=username).first():
            flash(_l('Ce nom d\'utilisateur existe deja'), 'error')
        elif User.query.filter_by(email=email).first():
            flash(_l('Cette adresse email est deja utilisee'), 'error')
        elif not group_ids and not is_superadmin and not is_tenant_admin:
            flash(_l('Vous devez assigner au moins un groupe'), 'error')
        elif is_tenant_admin and not tenant_ids:
            flash(_l('Vous devez assigner au moins un tenant pour un admin de tenant'), 'error')
        else:
            user = User(
                username=username,
                first_name=first_name if first_name else None,
                last_name=last_name if last_name else None,
                email=email,
                is_admin=is_superadmin
            )
            user.set_password(password)
            db.session.add(user)
            db.session.flush()

            # Add to groups with appropriate role (not for superadmin or tenant_admin)
            if not is_superadmin and not is_tenant_admin:
                for gid in group_ids:
                    group = Group.query.get(int(gid))
                    if group:
                        role = 'admin' if is_group_admin else 'member'
                        user.add_to_group(group, role)

            # Add tenant admin relationships
            if is_tenant_admin:
                for tid in tenant_ids:
                    tenant = Tenant.query.get(int(tid))
                    if tenant:
                        user.admin_tenants.append(tenant)

            db.session.commit()

            if is_superadmin:
                role_name = 'super-administrateur'
            elif is_tenant_admin:
                role_name = 'administrateur de tenant'
            elif is_group_admin:
                role_name = 'administrateur de groupe'
            else:
                role_name = 'utilisateur'
            flash(_l('%(role)s "%(username)s" cree avec succes', role=role_name.capitalize(), username=username), 'success')
            return redirect(url_for('admin.users'))

    return render_template('admin/create_user.html', groups=groups, tenants=tenants,
                          is_superadmin=current_user.is_superadmin)


@admin_bp.route('/users/import', methods=['GET', 'POST'])
@login_required
@admin_required
def import_users():
    """Import users from CSV file."""
    import csv
    from io import StringIO

    groups = scoped_groups().all()

    if request.method == 'POST':
        if 'csv_file' not in request.files:
            flash(_l('Aucun fichier selectionne'), 'error')
            return redirect(request.url)

        file = request.files['csv_file']
        if file.filename == '':
            flash(_l('Aucun fichier selectionne'), 'error')
            return redirect(request.url)

        default_group_id = request.form.get('default_group', type=int)
        default_password = request.form.get('default_password', '').strip()

        if not default_group_id:
            flash(_l('Veuillez selectionner un groupe par defaut'), 'error')
            return redirect(request.url)

        # Group must be in scope
        valid = validate_group_ids([default_group_id])
        default_group = valid[0] if valid else None
        if not default_group:
            flash(_l('Groupe invalide'), 'error')
            return redirect(request.url)

        try:
            # Read CSV content
            content = file.read().decode('utf-8-sig')  # Handle BOM
            reader = csv.DictReader(StringIO(content), delimiter=';')

            created_count = 0
            skipped_count = 0
            errors = []

            for row_num, row in enumerate(reader, start=2):
                # Get fields (flexible column names)
                username = (row.get('username') or row.get('identifiant') or row.get('login') or '').strip()
                email = (row.get('email') or row.get('mail') or row.get('courriel') or '').strip()
                first_name = (row.get('first_name') or row.get('prenom') or row.get('prénom') or '').strip()
                last_name = (row.get('last_name') or row.get('nom') or row.get('nom_famille') or '').strip()
                password = (row.get('password') or row.get('mot_de_passe') or default_password or '').strip()

                # Skip empty rows
                if not username and not email:
                    continue

                # Generate username from email if not provided
                if not username and email:
                    username = email.split('@')[0]

                # Generate email from username if not provided
                if username and not email:
                    email = f"{username}@imported.local"

                # Validation
                if not password:
                    errors.append(f"Ligne {row_num}: Mot de passe manquant pour {username}")
                    skipped_count += 1
                    continue

                if User.query.filter_by(username=username).first():
                    errors.append(f"Ligne {row_num}: Identifiant '{username}' existe deja")
                    skipped_count += 1
                    continue

                if User.query.filter_by(email=email).first():
                    errors.append(f"Ligne {row_num}: Email '{email}' existe deja")
                    skipped_count += 1
                    continue

                join_error = default_group.join_error()
                if join_error:
                    errors.append(f"Ligne {row_num}: {join_error}")
                    skipped_count += 1
                    continue

                # Create user
                user = User(
                    username=username,
                    email=email,
                    first_name=first_name if first_name else None,
                    last_name=last_name if last_name else None
                )
                user.set_password(password)
                db.session.add(user)
                db.session.flush()

                # Add to default group
                user.add_to_group(default_group, 'member')
                created_count += 1

            db.session.commit()

            if created_count > 0:
                flash(_l('%(count)s utilisateur(s) importe(s) avec succes dans le groupe "%(group)s"', count=created_count, group=default_group.name), 'success')
            if skipped_count > 0:
                flash(_l('%(count)s utilisateur(s) ignore(s)', count=skipped_count), 'warning')
            if errors:
                for error in errors[:5]:  # Show first 5 errors
                    flash(error, 'error')
                if len(errors) > 5:
                    flash(_l('... et %(count)s autre(s) erreur(s)', count=len(errors) - 5), 'error')

            return redirect(url_for('admin.users'))

        except Exception as e:
            db.session.rollback()
            flash(_l('Erreur lors de l\'import: %(error)s', error=str(e)), 'error')

    return render_template('admin/import_users.html', groups=groups)


@admin_bp.route('/user/<identifier>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def edit_user(identifier):
    """Edit an existing user."""
    from app.models.user import user_groups
    user = User.get_by_identifier(identifier)
    if not user:
        flash(_l('Utilisateur introuvable'), 'error')
        return redirect(url_for('admin.users'))

    user_id = user.id  # Keep for queries

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != user.get_url_identifier():
        return redirect(url_for('admin.edit_user', identifier=user.get_url_identifier()), code=301)

    # Prevent editing yourself to remove admin rights
    if user.id == current_user.id:
        flash(_l('Vous ne pouvez pas modifier votre propre compte ici'), 'error')
        return redirect(url_for('admin.users'))

    # Write access: lower role only, and all of the user's groups must be ours
    if not current_user.can_manage_user(user):
        flash(_l('Vous n\'avez pas acces a cet utilisateur'), 'error')
        return redirect(url_for('admin.users'))

    groups = scoped_groups().all()
    tenants = get_accessible_tenants() if current_user.is_superadmin else []

    # Get user's current groups with roles
    user_group_roles = {}
    for g in user.groups:
        role = user.get_role_in_group(g.id)
        user_group_roles[g.id] = role

    # Get user's current tenant admin assignments
    user_tenant_ids = [t.id for t in user.admin_tenants] if hasattr(user, 'admin_tenants') else []

    if request.method == 'POST':
        action = request.form.get('action')

        # Handle email verification actions
        if action == 'verify_email':
            user.email_verified = True
            user.clear_verification_token()
            db.session.commit()
            flash(_l('Email de %(username)s verifie manuellement.', username=user.username), 'success')
            return redirect(url_for('admin.edit_user', identifier=user.get_url_identifier()))

        elif action == 'resend_verification':
            if send_verification_email(user):
                db.session.commit()
                flash(_l('Email de verification renvoye a %(email)s.', email=user.email), 'success')
            else:
                flash(_l('Erreur lors de l\'envoi de l\'email.'), 'error')
            return redirect(url_for('admin.edit_user', identifier=user.get_url_identifier()))

        username = request.form.get('username', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email', '').strip()
        password = request.form.get('password')
        is_superadmin = request.form.get('is_superadmin') == 'on'
        is_tenant_admin = request.form.get('is_tenant_admin') == 'on'
        is_group_admin = request.form.get('is_group_admin') == 'on'
        selected_group_ids = request.form.getlist('group_ids')
        selected_tenant_ids = request.form.getlist('tenant_ids')

        # Non-superadmins cannot change superadmin/tenant_admin status
        if not current_user.is_superadmin:
            is_superadmin = user.is_superadmin  # Keep original value
            is_tenant_admin = user.is_tenant_admin  # Keep original value
            selected_tenant_ids = []  # Non-superadmins can't modify tenant assignments
            # Tenant admins can modify group admin status, group admins cannot
            if not current_user.is_tenant_admin:
                is_group_admin = False

        # Validation
        if not username or not email:
            flash(_l('Nom d\'utilisateur et email sont requis'), 'error')
        elif User.query.filter(User.username == username, User.id != user_id).first():
            flash(_l('Ce nom d\'utilisateur existe deja'), 'error')
        elif User.query.filter(User.email == email, User.id != user_id).first():
            flash(_l('Cette adresse email est deja utilisee'), 'error')
        else:
            user.username = username
            user.first_name = first_name if first_name else None
            user.last_name = last_name if last_name else None
            user.email = email

            # Only superadmins can change superadmin status
            if current_user.is_superadmin:
                user.is_admin = is_superadmin

                # Update tenant admin assignments
                if is_tenant_admin and not is_superadmin:
                    # Get current tenant IDs
                    current_tenant_ids = set(t.id for t in user.admin_tenants)
                    new_tenant_ids = set(int(tid) for tid in selected_tenant_ids if tid)

                    # Remove from tenants no longer selected
                    for tid in current_tenant_ids - new_tenant_ids:
                        tenant = Tenant.query.get(tid)
                        if tenant:
                            user.admin_tenants.remove(tenant)

                    # Add to newly selected tenants
                    for tid in new_tenant_ids - current_tenant_ids:
                        tenant = Tenant.query.get(tid)
                        if tenant:
                            user.admin_tenants.append(tenant)
                elif not is_tenant_admin:
                    # Remove from all tenants if no longer tenant admin
                    user.admin_tenants = []

            # Update group memberships
            if not is_superadmin and not is_tenant_admin:
                # Determine which groups we can modify
                if current_user.is_superadmin:
                    # Superadmin can modify all groups
                    modifiable_group_ids = set(g.id for g in groups)
                else:
                    # Tenant/group admin can only modify their accessible groups
                    modifiable_group_ids = set(g.id for g in current_user.get_accessible_groups())

                # Get current groups the user is in
                current_group_ids = set(g.id for g in user.groups)

                # Groups to add (selected but not currently member)
                groups_to_add = set(int(gid) for gid in selected_group_ids if gid) - current_group_ids
                # Groups to remove (was member but no longer selected) - only from modifiable groups
                groups_to_remove = (current_group_ids & modifiable_group_ids) - set(int(gid) for gid in selected_group_ids if gid)

                # Add to new groups
                for gid in groups_to_add:
                    if gid in modifiable_group_ids:
                        group = Group.query.get(gid)
                        join_error = group.join_error(user) if group else None
                        if join_error:
                            flash(f'{group.name} : {join_error}', 'error')
                        elif group:
                            role = 'admin' if is_group_admin else 'member'
                            user.add_to_group(group, role=role)

                # Remove from deselected groups
                for gid in groups_to_remove:
                    group = Group.query.get(gid)
                    if group:
                        user.remove_from_group(group)

                # Update roles for existing memberships if changing to/from group admin
                # Superadmins and tenant admins can modify group admin roles
                can_modify_roles = current_user.is_superadmin or current_user.is_tenant_admin
                if can_modify_roles and is_group_admin:
                    # Update role to admin for all selected groups within modifiable scope
                    for gid in selected_group_ids:
                        if gid:
                            gid = int(gid)
                            if gid in current_group_ids and gid in modifiable_group_ids:
                                # Update existing membership role
                                db.session.execute(
                                    user_groups.update().where(
                                        user_groups.c.user_id == user.id,
                                        user_groups.c.group_id == gid
                                    ).values(role='admin')
                                )
                elif can_modify_roles and not is_group_admin:
                    # Demote to member for modifiable groups only
                    for gid in modifiable_group_ids:
                        if gid in current_group_ids:
                            db.session.execute(
                                user_groups.update().where(
                                    user_groups.c.user_id == user.id,
                                    user_groups.c.group_id == gid
                                ).values(role='member')
                            )

            # Only update password if provided
            if password:
                user.set_password(password)

            db.session.commit()
            User.clear_role_cache()
            flash(_l('Utilisateur "%(username)s" mis a jour avec succes', username=username), 'success')
            return redirect(url_for('admin.users'))

    return render_template('admin/edit_user.html', user=user, groups=groups,
                          user_group_roles=user_group_roles, tenants=tenants,
                          user_tenant_ids=user_tenant_ids,
                          is_superadmin=current_user.is_superadmin)

@admin_bp.route('/user/<identifier>/delete', methods=['POST'])
@login_required
@admin_required
def delete_user(identifier):
    """Delete a user."""
    user = User.get_by_identifier(identifier)
    if not user:
        flash(_l('Utilisateur introuvable'), 'error')
        return redirect(url_for('admin.users'))

    # Prevent self-deletion
    if user.id == current_user.id:
        flash(_l('Vous ne pouvez pas supprimer votre propre compte'), 'error')
        return redirect(url_for('admin.users'))

    # Write access: lower role only, and all of the user's groups must be ours
    if not current_user.can_manage_user(user):
        flash(_l('Vous n\'avez pas acces a cet utilisateur'), 'error')
        return redirect(url_for('admin.users'))

    username = user.username
    db.session.delete(user)
    db.session.commit()

    flash(_l('Utilisateur "%(username)s" supprime avec succes', username=username), 'success')
    return redirect(url_for('admin.users'))


# Bulk user actions
@admin_bp.route('/users/bulk-delete', methods=['POST'])
@login_required
@admin_required
def bulk_delete_users():
    """Delete multiple users at once."""
    user_ids = request.form.getlist('user_ids', type=int)
    if not user_ids:
        flash(_l('Aucun utilisateur selectionne'), 'warning')
        return redirect(url_for('admin.users'))

    deleted_count = 0
    skipped_count = 0

    for user_id in user_ids:
        user = User.query.get(user_id)
        if not user:
            continue

        # Skip self-deletion
        if user.id == current_user.id:
            skipped_count += 1
            continue

        # Permission check (write access)
        if not current_user.can_manage_user(user):
            skipped_count += 1
            continue

        db.session.delete(user)
        deleted_count += 1

    db.session.commit()

    if deleted_count > 0:
        flash(_l('%(count)s utilisateur(s) supprime(s)', count=deleted_count), 'success')
    if skipped_count > 0:
        flash(_l('%(count)s utilisateur(s) ignore(s) (pas de permission)', count=skipped_count), 'warning')

    return redirect(url_for('admin.users'))


@admin_bp.route('/users/bulk-change-group', methods=['POST'])
@login_required
@admin_required
def bulk_change_group():
    """Change group for multiple users at once."""
    user_ids = request.form.getlist('user_ids', type=int)
    action = request.form.get('action')  # 'add' or 'remove' or 'replace'
    group_id = request.form.get('group_id', type=int)

    if not user_ids:
        flash(_l('Aucun utilisateur selectionne'), 'warning')
        return redirect(url_for('admin.users'))

    if not group_id or action not in ('add', 'remove', 'replace'):
        flash(_l('Aucun groupe selectionne'), 'warning')
        return redirect(url_for('admin.users'))

    group = Group.query.get(group_id)
    if not group:
        flash(_l('Groupe non trouve'), 'error')
        return redirect(url_for('admin.users'))

    # Check group access
    if not current_user.can_access_group(group):
        flash(_l('Vous n\'avez pas acces a ce groupe'), 'error')
        return redirect(url_for('admin.users'))

    updated_count = 0
    skipped_count = 0
    managed_group_ids = current_user.get_managed_group_ids()  # None = all

    for user_id in user_ids:
        user = User.query.get(user_id)
        if not user:
            continue

        # Skip users we cannot see, ourselves, and peers or superiors
        if (user.id == current_user.id
                or not current_user.can_access_user(user)
                or (not current_user.is_superadmin and user.role_rank >= current_user.role_rank)):
            skipped_count += 1
            continue

        in_group = user.is_member_of_group(group.id)

        # Check group/tenant capacity
        if action in ['add', 'replace'] and not in_group and group.join_error(user):
            skipped_count += 1
            continue

        if action == 'add':
            if not in_group:
                user.add_to_group(group, 'member')
                updated_count += 1
        elif action == 'remove':
            if in_group:
                user.remove_from_group(group)
                updated_count += 1
        elif action == 'replace':
            # Leave only the groups we manage; memberships elsewhere are kept
            for g in user.groups.all():
                if g.id != group.id and (managed_group_ids is None or g.id in managed_group_ids):
                    user.remove_from_group(g)
            if not in_group:
                user.add_to_group(group, 'member')
            updated_count += 1

    db.session.commit()

    action_text = {'add': 'ajoute(s) au', 'remove': 'retire(s) du', 'replace': 'deplace(s) vers le'}.get(action, 'modifie(s) pour le')
    if updated_count > 0:
        flash(_l('%(count)s utilisateur(s) %(action)s groupe "%(group)s"', count=updated_count, action=action_text, group=group.name), 'success')
    if skipped_count > 0:
        flash(_l('%(count)s utilisateur(s) ignore(s)', count=skipped_count), 'warning')

    return redirect(url_for('admin.users'))


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
    if referer and 'user_grades' in referer:
        return redirect(url_for('admin.user_grades', identifier=user.get_url_identifier()))
    return redirect(url_for('admin.quiz_results', identifier=quiz.get_url_identifier()))


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


# Site Settings routes - Superadmin only
@admin_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@superadmin_required
def site_settings():
    """Manage site settings and backup configuration."""
    from app.models.settings import SiteSettings
    from app.utils.backup_scheduler import get_next_backup_time, update_backup_schedule

    settings = SiteSettings.get_settings()

    if request.method == 'POST':
        action = request.form.get('action', 'save')

        if action == 'save':
            # Site branding
            settings.site_title = request.form.get('site_title', 'BrainNotFound').strip()[:100]
            settings.contact_email = request.form.get('contact_email', '').strip()[:255]

            # FTP settings
            settings.ftp_enabled = request.form.get('ftp_enabled') == 'on'
            settings.ftp_host = request.form.get('ftp_host', '').strip()[:255]
            settings.ftp_port = int(request.form.get('ftp_port', 21) or 21)
            settings.ftp_username = request.form.get('ftp_username', '').strip()[:255]
            settings.ftp_path = request.form.get('ftp_path', '/backups').strip()[:500]
            settings.ftp_use_tls = request.form.get('ftp_use_tls') == 'on'

            # Only update password if provided
            new_password = request.form.get('ftp_password', '')
            if new_password:
                settings.set_ftp_password(new_password)

            error = save_ai_settings(settings, request.form)
            if error:
                flash(error, 'error')

            # Backup schedule
            settings.backup_frequency = request.form.get('backup_frequency', 'daily')
            settings.backup_hour = int(request.form.get('backup_hour', 3) or 3)
            settings.backup_day = int(request.form.get('backup_day', 0) or 0)
            settings.backup_retention_days = int(request.form.get('backup_retention_days', 30) or 30)

            db.session.commit()

            # Update scheduler
            try:
                update_backup_schedule()
            except Exception as e:
                current_app.logger.error(f"Failed to update backup schedule: {str(e)}")

            flash(_l('Parametres sauvegardes avec succes'), 'success')
            return redirect(url_for('admin.site_settings'))

    # Get next backup time
    next_backup = get_next_backup_time()

    return render_template('admin/settings.html',
                          settings=settings,
                          next_backup=next_backup,
                          ai=ai_settings_summary(settings))


def save_ai_settings(settings, form):
    """Apply the LLM section of the settings form. Returns an error message or None."""
    from app.utils import ai_client

    provider = form.get('ai_provider', ai_client.ANTHROPIC)
    if provider not in ai_client.PROVIDERS:
        provider = ai_client.ANTHROPIC
    base_url = None
    if provider == ai_client.OPENAI_COMPATIBLE:
        base_url = form.get('ai_base_url', '').strip()[:255] or None
    model = form.get('ai_model', '').strip()[:100] or None
    new_key = form.get('ai_api_key', '').strip()

    if provider == ai_client.OPENAI_COMPATIBLE and not base_url:
        return _l('URL du fournisseur requise')
    if provider == ai_client.OPENAI_COMPATIBLE and not model:
        return _l('Modele requis pour ce fournisseur')
    if ai_client.is_grok(provider, base_url, model) and form.get('grok_confirmed') != '1':
        return _l('Configuration non enregistree : utilisation de Grok non confirmee')

    endpoint_changed = (provider != (settings.ai_provider or ai_client.ANTHROPIC)
                        or base_url != settings.ai_base_url)
    key = new_key or (None if endpoint_changed or form.get('clear_ai_api_key') == 'on'
                      else settings.get_ai_api_key())

    model_error = check_ai_model(provider, base_url, model, key)
    if model_error:
        return model_error

    settings.ai_provider = provider
    settings.ai_base_url = base_url
    settings.ai_model = model
    # A key belongs to one provider/server: it's dropped when switching, never sent elsewhere
    settings.set_ai_api_key(key)
    return None


def ai_settings_summary(settings):
    """Where the LLM config comes from, for display (never the key itself)."""
    from app.utils import ai_client
    config = ai_client.get_config()
    db_key = settings.get_ai_api_key()
    key = config['api_key']
    return {
        'provider': config['provider'],
        'key_source': 'admin' if db_key else ('env' if key else None),
        'key_hint': f"...{key[-4:]}" if key else None,
        'key_unreadable': bool(settings.ai_api_key_encrypted and not db_key),
        'env_model': current_app.config.get('CLAUDE_MODEL') or ai_client.DEFAULT_MODEL,
    }


def check_ai_model(provider, base_url, model, api_key=None):
    """Return an error message if the provider says this model doesn't exist, None otherwise.

    Network/auth problems don't block saving: the model may be valid and the
    admin can use the test button once the key is fixed.
    """
    from app.utils import ai_client
    if not model:
        return None
    try:
        available = {m_id for m_id, _ in ai_client.list_models(provider, api_key, base_url)}
    except Exception as e:  # no key, auth, network, server without /models...
        current_app.logger.warning(f"Could not verify AI model {model}: {e}")
        return None
    if available and model not in available:
        return _l('Modele inconnu chez ce fournisseur : %(model)s. Configuration non modifiee.', model=model)
    return None


@admin_bp.route('/settings/ai-models', methods=['POST'])
@login_required
@superadmin_required
def ai_models():
    """List the models of a provider (typed values or configured ones) - also tests the key."""
    import anthropic
    import openai
    from app.utils import ai_client

    data = request.get_json(silent=True) or {}
    provider = data.get('provider') if data.get('provider') in ai_client.PROVIDERS else None
    try:
        models = ai_client.list_models(provider, data.get('api_key', '').strip() or None,
                                       data.get('base_url', '').strip() or None)
    except (anthropic.AuthenticationError, openai.AuthenticationError):
        return jsonify({'success': False, 'message': str(_l('Cle API refusee par le fournisseur'))})
    except (anthropic.APIConnectionError, openai.APIConnectionError):
        return jsonify({'success': False, 'message': str(_l('Impossible de joindre le fournisseur'))})
    except (anthropic.APIStatusError, openai.APIStatusError) as e:
        return jsonify({'success': False, 'message': f'API error {e.status_code}'})
    except (anthropic.AnthropicError, openai.OpenAIError, ai_client.AIConfigError):
        return jsonify({'success': False, 'message': str(_l('Configuration incomplete (cle ou URL manquante)'))})
    return jsonify({'success': True, 'models': [{'id': m_id, 'name': name} for m_id, name in models]})


@admin_bp.route('/settings/test-ftp', methods=['POST'])
@login_required
@superadmin_required
def test_ftp_connection():
    """Test FTP connection with current settings."""
    from app.utils.backup_manager import BackupManager

    manager = BackupManager()
    success, message = manager.test_ftp_connection()

    return jsonify({
        'success': success,
        'message': message
    })


@admin_bp.route('/settings/run-backup', methods=['POST'])
@login_required
@superadmin_required
def run_manual_backup():
    """Run a manual backup now."""
    from app.utils.backup_manager import BackupManager

    manager = BackupManager()
    result = manager.run_backup()

    return jsonify(result)


@admin_bp.route('/settings/backup-history')
@login_required
@superadmin_required
def backup_history():
    """Backups available for download/restore: on this server and on FTP."""
    from app.utils.backup_manager import BackupManager

    manager = BackupManager()
    local = [{k: v for k, v in f.items() if k != 'mtime'} for f in manager.list_local_backups()]
    ftp_ok, ftp_files, ftp_message = manager.list_ftp_backups()
    return jsonify({
        'local': local,
        'ftp': ftp_files[:50] if ftp_ok else [],
        'ftp_error': None if ftp_ok or not manager._get_settings().ftp_enabled else ftp_message,
    })


@admin_bp.route('/settings/backups/<name>/download')
@login_required
@superadmin_required
def download_backup(name):
    """Download a backup stored on this server."""
    from app.utils.backup_manager import BackupManager

    path = BackupManager().local_backup_path(name)
    if not path:
        abort(404)
    return send_file(path, as_attachment=True, download_name=name)


@admin_bp.route('/settings/backups/download-now', methods=['POST'])
@login_required
@superadmin_required
def download_backup_now():
    """Create a full backup (DB + uploads) and send it straight to the browser."""
    from app.utils.backup_manager import BackupManager

    manager = BackupManager()
    ok, path, message, _ = manager.create_backup()
    if not ok:
        flash(message, 'error')
        return redirect(url_for('admin.site_settings'))
    response = send_file(path, as_attachment=True, download_name=os.path.basename(path))
    response.call_on_close(lambda: manager._cleanup_local(path))
    return response


def _restore_confirmed(value):
    return (value or '').strip().upper() in ('RESTAURER', 'RESTORE')  # FR / EN interface


def _finish_restore(ok, message):
    """After a restore: migrate the restored schema, then log the admin out.

    The restored users table may not contain the current account (or give its
    id to someone else), so the current session must not survive.
    """
    from flask_login import logout_user
    from app.utils.db_schema import upgrade_schema

    if ok:
        try:
            message += '. ' + upgrade_schema()
        except Exception as e:
            current_app.logger.error(f"Schema upgrade after restore failed: {e}")
            ok, message = False, f"{message}. Schema upgrade failed, restart the container: {e}"
        db.session.remove()
        logout_user()
    current_app.logger.warning(f"Backup restore by {current_user.get_id() if current_user.is_authenticated else '?'}: {message}")
    return ok, message


@admin_bp.route('/settings/restore-backup', methods=['POST'])
@login_required
@superadmin_required
def restore_backup():
    """Restore a backup stored on this server (source=local) or on FTP (source=ftp)."""
    from app.utils.backup_manager import BackupManager

    data = request.get_json(silent=True) or request.form
    filename = data.get('filename', '')
    source = data.get('source', 'ftp')
    manager = BackupManager()

    if not manager.is_valid_backup_name(filename):
        return jsonify({'success': False, 'message': 'Invalid backup filename'}), 400
    if not _restore_confirmed(data.get('confirm')):
        return jsonify({'success': False, 'message': str(_l('Tapez RESTAURER pour confirmer'))}), 400

    if source == 'local':
        path = manager.local_backup_path(filename)
        if not path:
            return jsonify({'success': False, 'message': 'Backup not found'}), 404
        ok, message = manager.restore_backup(path)
    else:
        result = manager.restore_from_ftp(filename)
        ok, message = result['success'], result['message']

    ok, message = _finish_restore(ok, message)
    return jsonify({'success': ok, 'message': message, 'redirect': url_for('auth.login') if ok else None})


@admin_bp.route('/settings/restore-upload', methods=['POST'])
@csrf.exempt  # checked below, once the upload size limit has been raised
@login_required
@superadmin_required
def restore_upload():
    """Restore a backup file uploaded from the admin's computer."""
    from flask_wtf.csrf import validate_csrf
    from wtforms import ValidationError
    from app.utils.backup_manager import BackupManager, BACKUP_SUFFIX

    # Backups (DB + uploads) are larger than the global 16 MB request limit
    request.max_content_length = current_app.config['BACKUP_MAX_UPLOAD_MB'] * 1024 * 1024
    try:
        validate_csrf(request.form.get('csrf_token'))
    except ValidationError:
        abort(400)

    upload = request.files.get('backup_file')
    if not upload or not upload.filename:
        flash(_l('Aucun fichier selectionne'), 'error')
        return redirect(url_for('admin.site_settings'))
    if not _restore_confirmed(request.form.get('confirm')):
        flash(_l('Tapez RESTAURER pour confirmer'), 'error')
        return redirect(url_for('admin.site_settings'))

    suffix = BACKUP_SUFFIX if upload.filename.endswith(BACKUP_SUFFIX) else '.sql.gz'
    if not upload.filename.endswith(suffix):
        flash(_l('Format attendu : .tar.gz ou .sql.gz'), 'error')
        return redirect(url_for('admin.site_settings'))

    manager = BackupManager()
    tmp_dir = tempfile.mkdtemp(prefix='restore_upload_')
    path = os.path.join(tmp_dir, f'upload{suffix}')
    try:
        upload.save(path)
        ok, message = manager.restore_backup(path)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    ok, message = _finish_restore(ok, message)
    flash(message, 'success' if ok else 'error')
    return redirect(url_for('auth.login') if ok else url_for('admin.site_settings'))


# ============================================================
# Page Management Routes - Superadmin only
# ============================================================

@admin_bp.route('/pages')
@login_required
@superadmin_required
def pages():
    """List all custom pages."""
    from app.models.page import Page
    all_pages = Page.query.order_by(Page.display_order, Page.title).all()
    return render_template('admin/pages.html', pages=all_pages)


@admin_bp.route('/pages/create', methods=['GET', 'POST'])
@login_required
@superadmin_required
def create_page():
    """Create a new custom page."""
    from app.models.page import Page
    import re

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        slug = request.form.get('slug', '').strip().lower()
        content = request.form.get('content', '')
        location = request.form.get('location', 'footer')
        display_order = int(request.form.get('display_order', 0) or 0)
        is_published = request.form.get('is_published') == 'on'
        open_new_tab = request.form.get('open_new_tab') == 'on'

        # Validate
        if not title:
            flash(_l('Le titre est requis'), 'error')
            return render_template('admin/edit_page.html', page=None)

        # Generate slug if not provided
        if not slug:
            slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')

        # Check slug uniqueness
        existing = Page.query.filter_by(slug=slug).first()
        if existing:
            flash(_l('Ce slug existe deja'), 'error')
            return render_template('admin/edit_page.html', page=None)

        # Validate slug format
        if not re.match(r'^[a-z0-9\-]+$', slug):
            flash(_l('Le slug ne peut contenir que des lettres minuscules, chiffres et tirets'), 'error')
            return render_template('admin/edit_page.html', page=None)

        page = Page(
            title=title,
            slug=slug,
            content=content,
            location=location,
            display_order=display_order,
            is_published=is_published,
            open_new_tab=open_new_tab
        )
        db.session.add(page)
        db.session.commit()

        flash(_l('Page creee avec succes'), 'success')
        return redirect(url_for('admin.pages'))

    return render_template('admin/edit_page.html', page=None)


@admin_bp.route('/pages/<identifier>/edit', methods=['GET', 'POST'])
@login_required
@superadmin_required
def edit_page(identifier):
    """Edit an existing custom page."""
    from app.models.page import Page
    import re

    page = Page.get_by_identifier(identifier)
    if not page:
        flash(_l('Page introuvable'), 'error')
        return redirect(url_for('admin.pages'))

    # Redirect if accessed by old numeric ID
    if identifier != page.get_url_identifier():
        return redirect(url_for('admin.edit_page', identifier=page.get_url_identifier()), code=301)

    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        slug = request.form.get('slug', '').strip().lower()
        content = request.form.get('content', '')
        location = request.form.get('location', 'footer')
        display_order = int(request.form.get('display_order', 0) or 0)
        is_published = request.form.get('is_published') == 'on'
        open_new_tab = request.form.get('open_new_tab') == 'on'

        # Validate
        if not title:
            flash(_l('Le titre est requis'), 'error')
            return render_template('admin/edit_page.html', page=page)

        # Generate slug if not provided
        if not slug:
            slug = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')

        # Check slug uniqueness (excluding current page)
        existing = Page.query.filter(Page.slug == slug, Page.id != page.id).first()
        if existing:
            flash(_l('Ce slug existe deja'), 'error')
            return render_template('admin/edit_page.html', page=page)

        # Validate slug format
        if not re.match(r'^[a-z0-9\-]+$', slug):
            flash(_l('Le slug ne peut contenir que des lettres minuscules, chiffres et tirets'), 'error')
            return render_template('admin/edit_page.html', page=page)

        page.title = title
        page.slug = slug
        page.content = content
        page.location = location
        page.display_order = display_order
        page.is_published = is_published
        page.open_new_tab = open_new_tab

        db.session.commit()

        flash(_l('Page modifiee avec succes'), 'success')
        return redirect(url_for('admin.pages'))

    return render_template('admin/edit_page.html', page=page)


@admin_bp.route('/pages/<identifier>/delete', methods=['POST'])
@login_required
@superadmin_required
def delete_page(identifier):
    """Delete a custom page."""
    from app.models.page import Page

    page = Page.get_by_identifier(identifier)
    if not page:
        flash(_l('Page introuvable'), 'error')
        return redirect(url_for('admin.pages'))
    db.session.delete(page)
    db.session.commit()

    flash(_l('Page supprimee avec succes'), 'success')
    return redirect(url_for('admin.pages'))


@admin_bp.route('/pages/<identifier>/preview')
@login_required
@superadmin_required
def preview_page(identifier):
    """Preview a page (even if not published)."""
    from app.models.page import Page

    page = Page.get_by_identifier(identifier)
    if not page:
        flash(_l('Page introuvable'), 'error')
        return redirect(url_for('admin.pages'))

    # Redirect if accessed by old numeric ID
    if identifier != page.get_url_identifier():
        return redirect(url_for('admin.preview_page', identifier=page.get_url_identifier()), code=301)
    return render_template('page/view.html', page=page, is_preview=True)
