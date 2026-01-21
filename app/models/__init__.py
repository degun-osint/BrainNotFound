# Models package - Import all models for Alembic discovery
from app.models.user import User, user_groups
from app.models.group import Group
from app.models.quiz import Quiz, Question, QuizResponse, Answer, quiz_groups
from app.models.settings import SiteSettings
from app.models.page import Page
from app.models.tenant import Tenant, tenant_admins

__all__ = [
    'User', 'user_groups',
    'Group',
    'Quiz', 'Question', 'QuizResponse', 'Answer', 'quiz_groups',
    'SiteSettings',
    'Page',
    'Tenant', 'tenant_admins'
]
