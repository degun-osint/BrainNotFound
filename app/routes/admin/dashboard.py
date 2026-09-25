"""Admin dashboard."""
from flask import render_template, request
from flask_login import login_required, current_user
from app import db
from app.models.user import User
from app.models.group import Group
from app.models.quiz import Quiz, QuizResponse
from app.models.interview import Interview, InterviewSession
from app.utils.prompt_loader import get_fallback_warnings, is_using_fallback
from app.utils.scope import get_tenant_context, scoped_groups, scoped_quizzes, scoped_interviews, scoped_users
from app.routes.admin import admin_bp
from app.routes.admin.common import admin_required
from app.routes.admin.results import grading_todo


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
    todo = grading_todo()

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
                           recent_responses=recent_responses, pending_grading=pending_grading, grading_todo=todo,
                           fallback_warnings=fallback_warnings, recent_interviews=recent_interviews)
