"""Add interview tables for conversational AI evaluation.

Revision ID: 009_interviews
Revises: 008_tenant_monthly_limits
Create Date: 2026-01-22
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '009_interviews'
down_revision = '008_tenant_limits'
branch_labels = None
depends_on = None


def upgrade():
    # Create interviews table
    op.create_table(
        'interviews',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('slug', sa.String(100), nullable=True),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),

        # AI Persona Configuration
        sa.Column('system_prompt', sa.Text(), nullable=False),

        # Wizard-generated fields for re-editing
        sa.Column('persona_name', sa.String(100), nullable=True),
        sa.Column('persona_role', sa.String(200), nullable=True),
        sa.Column('persona_context', sa.Text(), nullable=True),
        sa.Column('persona_personality', sa.Text(), nullable=True),
        sa.Column('persona_knowledge', sa.Text(), nullable=True),
        sa.Column('persona_objectives', sa.Text(), nullable=True),
        sa.Column('persona_triggers', sa.Text(), nullable=True),
        sa.Column('student_context', sa.Text(), nullable=True),
        sa.Column('student_objective', sa.Text(), nullable=True),

        # Settings
        sa.Column('is_active', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('max_interactions', sa.Integer(), nullable=True, server_default='30'),
        sa.Column('max_duration_minutes', sa.Integer(), nullable=True, server_default='30'),
        sa.Column('allow_student_end', sa.Boolean(), nullable=True, server_default='1'),
        sa.Column('ai_can_end', sa.Boolean(), nullable=True, server_default='1'),

        # Opening message
        sa.Column('opening_message', sa.Text(), nullable=True),

        # Who starts the conversation
        sa.Column('student_starts', sa.Boolean(), nullable=True, server_default='0'),

        # File upload requirement
        sa.Column('require_file_upload', sa.Boolean(), nullable=True, server_default='0'),
        sa.Column('file_upload_label', sa.String(100), nullable=True, server_default="'Fichier'"),
        sa.Column('file_upload_description', sa.Text(), nullable=True),
        sa.Column('file_upload_prompt_injection', sa.Text(), nullable=True),

        # Availability
        sa.Column('available_from', sa.DateTime(), nullable=True),
        sa.Column('available_until', sa.DateTime(), nullable=True),

        # Tenant and ownership
        sa.Column('tenant_id', sa.Integer(), nullable=True),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id'])
    )
    op.create_index('ix_interviews_slug', 'interviews', ['slug'], unique=True)
    op.create_index('ix_interviews_tenant_id', 'interviews', ['tenant_id'])

    # Create evaluation_criteria table
    op.create_table(
        'evaluation_criteria',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('interview_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('max_points', sa.Float(), nullable=True, server_default='5.0'),
        sa.Column('order', sa.Integer(), nullable=True, server_default='0'),
        sa.Column('evaluation_hints', sa.Text(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['interview_id'], ['interviews.id'], ondelete='CASCADE')
    )
    op.create_index('ix_evaluation_criteria_interview_id', 'evaluation_criteria', ['interview_id'])

    # Create interview_sessions table
    op.create_table(
        'interview_sessions',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('interview_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),

        # Session state
        sa.Column('status', sa.String(30), nullable=True, server_default='in_progress'),
        sa.Column('interaction_count', sa.Integer(), nullable=True, server_default='0'),

        # Uploaded file (if required by interview)
        sa.Column('uploaded_file_name', sa.String(255), nullable=True),
        sa.Column('uploaded_file_content', sa.Text(), nullable=True),

        # Timing
        sa.Column('started_at', sa.DateTime(), nullable=True),
        sa.Column('last_activity_at', sa.DateTime(), nullable=True),
        sa.Column('ended_at', sa.DateTime(), nullable=True),

        # End reason
        sa.Column('end_reason', sa.String(50), nullable=True),

        # Scoring
        sa.Column('total_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('max_score', sa.Float(), nullable=True, server_default='0.0'),

        # AI summary
        sa.Column('ai_summary', sa.Text(), nullable=True),

        # Admin feedback
        sa.Column('admin_comment', sa.Text(), nullable=True),

        # Test mode
        sa.Column('is_test', sa.Boolean(), nullable=True, server_default='0'),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['interview_id'], ['interviews.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'])
    )
    op.create_index('ix_interview_sessions_interview_id', 'interview_sessions', ['interview_id'])
    op.create_index('ix_interview_sessions_user_id', 'interview_sessions', ['user_id'])

    # Create interview_messages table
    op.create_table(
        'interview_messages',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('role', sa.String(20), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('token_count', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('contains_end_signal', sa.Boolean(), nullable=True, server_default='0'),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['session_id'], ['interview_sessions.id'], ondelete='CASCADE')
    )
    op.create_index('ix_interview_messages_session_id', 'interview_messages', ['session_id'])

    # Create criterion_scores table
    op.create_table(
        'criterion_scores',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('session_id', sa.Integer(), nullable=False),
        sa.Column('criterion_id', sa.Integer(), nullable=False),
        sa.Column('score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('max_score', sa.Float(), nullable=True, server_default='0.0'),
        sa.Column('feedback', sa.Text(), nullable=True),

        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['session_id'], ['interview_sessions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['criterion_id'], ['evaluation_criteria.id'], ondelete='CASCADE')
    )
    op.create_index('ix_criterion_scores_session_id', 'criterion_scores', ['session_id'])
    op.create_index('ix_criterion_scores_criterion_id', 'criterion_scores', ['criterion_id'])

    # Create interview_groups association table
    op.create_table(
        'interview_groups',
        sa.Column('interview_id', sa.Integer(), nullable=False),
        sa.Column('group_id', sa.Integer(), nullable=False),
        sa.Column('assigned_at', sa.DateTime(), nullable=True),

        sa.PrimaryKeyConstraint('interview_id', 'group_id'),
        sa.ForeignKeyConstraint(['interview_id'], ['interviews.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['group_id'], ['groups.id'], ondelete='CASCADE')
    )

    # Add interview quotas to tenants table
    op.add_column('tenants', sa.Column('monthly_interviews', sa.Integer(), nullable=True, server_default='0'))
    op.add_column('tenants', sa.Column('used_interviews', sa.Integer(), nullable=True, server_default='0'))


def downgrade():
    # Remove interview quotas from tenants
    op.drop_column('tenants', 'used_interviews')
    op.drop_column('tenants', 'monthly_interviews')

    # Drop interview_groups
    op.drop_table('interview_groups')

    # Drop criterion_scores
    op.drop_index('ix_criterion_scores_criterion_id', table_name='criterion_scores')
    op.drop_index('ix_criterion_scores_session_id', table_name='criterion_scores')
    op.drop_table('criterion_scores')

    # Drop interview_messages
    op.drop_index('ix_interview_messages_session_id', table_name='interview_messages')
    op.drop_table('interview_messages')

    # Drop interview_sessions
    op.drop_index('ix_interview_sessions_user_id', table_name='interview_sessions')
    op.drop_index('ix_interview_sessions_interview_id', table_name='interview_sessions')
    op.drop_table('interview_sessions')

    # Drop evaluation_criteria
    op.drop_index('ix_evaluation_criteria_interview_id', table_name='evaluation_criteria')
    op.drop_table('evaluation_criteria')

    # Drop interviews
    op.drop_index('ix_interviews_tenant_id', table_name='interviews')
    op.drop_index('ix_interviews_slug', table_name='interviews')
    op.drop_table('interviews')
