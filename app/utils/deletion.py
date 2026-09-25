"""Deleting users and whole organizations without leaving orphans or FK errors."""
from app import db
from app.models import Group, Interview, Quiz, QuizResponse, Tenant, User, tenant_admins, user_groups
from app.models.interview import InterviewSession, interview_groups
from app.models.quiz import AnswerContest, quiz_graders, quiz_groups


def delete_user_account(user):
    """Delete a user and their data (quiz answers, interview sessions).

    Content they created (quizzes, interviews) stays, without an author.
    """
    db.session.execute(user_groups.delete().where(user_groups.c.user_id == user.id))
    db.session.execute(tenant_admins.delete().where(tenant_admins.c.user_id == user.id))
    Quiz.query.filter_by(created_by_id=user.id).update({'created_by_id': None}, synchronize_session=False)
    Interview.query.filter_by(created_by_id=user.id).update({'created_by_id': None}, synchronize_session=False)
    # Papers they validated and contests they resolved stay, without the grader's name
    db.session.execute(quiz_graders.delete().where(quiz_graders.c.user_id == user.id))
    QuizResponse.query.filter_by(reviewed_by_id=user.id).update({'reviewed_by_id': None}, synchronize_session=False)
    AnswerContest.query.filter_by(resolved_by_id=user.id).update({'resolved_by_id': None}, synchronize_session=False)
    db.session.delete(user)  # cascades: quiz responses + answers, interview sessions + messages


def tenant_deletion_plan(tenant):
    """What deleting this organization would remove, for the confirmation page."""
    group_ids = [g.id for g in tenant.groups]
    linked = set()
    if group_ids:
        linked |= {row[0] for row in db.session.query(user_groups.c.user_id)
                   .filter(user_groups.c.group_id.in_(group_ids))}
    linked |= {row[0] for row in db.session.query(tenant_admins.c.user_id)
               .filter(tenant_admins.c.tenant_id == tenant.id)}

    exclusive, shared = [], []
    for user in User.query.filter(User.id.in_(linked)).all() if linked else []:
        other_groups = [g for g in user.groups if g.id not in group_ids]
        other_tenants = user.admin_tenant_ids() - {tenant.id}
        (shared if user.is_admin or other_groups or other_tenants else exclusive).append(user)

    quiz_ids = [q.id for q in Quiz.query.filter_by(tenant_id=tenant.id)]
    interview_ids = [i.id for i in Interview.query.filter_by(tenant_id=tenant.id)]
    return {
        'groups': len(group_ids),
        'quizzes': len(quiz_ids),
        'interviews': len(interview_ids),
        'responses': QuizResponse.query.filter(QuizResponse.quiz_id.in_(quiz_ids)).count() if quiz_ids else 0,
        'sessions': InterviewSession.query.filter(
            InterviewSession.interview_id.in_(interview_ids)).count() if interview_ids else 0,
        'exclusive_users': exclusive,
        'shared_users': shared,
    }


def delete_tenant(tenant, delete_accounts=True):
    """Delete an organization with its groups and content.

    delete_accounts: also delete the accounts that belong to this organization
    only (superadmins and accounts shared with another organization are kept,
    just detached). Caller commits.
    """
    plan = tenant_deletion_plan(tenant)
    group_ids = [g.id for g in tenant.groups]

    for quiz in Quiz.query.filter_by(tenant_id=tenant.id).all():
        db.session.delete(quiz)  # cascades: questions, responses, answers
    for interview in Interview.query.filter_by(tenant_id=tenant.id).all():
        db.session.delete(interview)  # cascades: criteria, sessions, messages, scores
    db.session.flush()

    if delete_accounts:
        for user in plan['exclusive_users']:
            delete_user_account(user)
        db.session.flush()

    if group_ids:
        # Content of other organizations assigned to these groups is only unassigned
        db.session.execute(quiz_groups.delete().where(quiz_groups.c.group_id.in_(group_ids)))
        db.session.execute(interview_groups.delete().where(interview_groups.c.group_id.in_(group_ids)))
        db.session.execute(user_groups.delete().where(user_groups.c.group_id.in_(group_ids)))
        Group.query.filter(Group.id.in_(group_ids)).delete(synchronize_session=False)
    db.session.execute(tenant_admins.delete().where(tenant_admins.c.tenant_id == tenant.id))
    db.session.delete(tenant)
    User.clear_role_cache()
    return plan
