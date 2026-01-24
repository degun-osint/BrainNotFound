"""
Interview models for conversational AI evaluation.

This module provides models for:
- Interview: Configuration/template for an AI persona interview
- EvaluationCriterion: Individual evaluation criteria with points
- InterviewSession: A student's interview attempt
- InterviewMessage: Individual messages in a conversation
- CriterionScore: Score for a specific criterion in a session
"""

from app import db
from datetime import datetime
from sqlalchemy import event
from app.models.mixins import UIDMixin, init_uid_on_create

# Association table for Interview-Group many-to-many relationship
interview_groups = db.Table('interview_groups',
    db.Column('interview_id', db.Integer, db.ForeignKey('interviews.id'), primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('groups.id'), primary_key=True),
    db.Column('assigned_at', db.DateTime, default=datetime.utcnow)
)


class Interview(UIDMixin, db.Model):
    """Interview template configured by admin - defines the AI persona and evaluation criteria."""
    __tablename__ = 'interviews'

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(100), unique=True, nullable=True, index=True)  # Coolname-based identifier
    slug = db.Column(db.String(100), unique=True, nullable=True, index=True)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)

    # AI Persona Configuration (the final system prompt for Claude)
    system_prompt = db.Column(db.Text, nullable=False)

    # Wizard-generated fields (stored for reference/re-editing)
    persona_name = db.Column(db.String(100))
    persona_role = db.Column(db.String(200))
    persona_context = db.Column(db.Text)
    persona_personality = db.Column(db.Text)
    persona_knowledge = db.Column(db.Text)
    persona_objectives = db.Column(db.Text)
    persona_triggers = db.Column(db.Text)  # Behaviors triggered by certain approaches
    student_context = db.Column(db.Text)  # What the student knows before interview
    student_objective = db.Column(db.Text)  # What the student should try to achieve

    # Settings
    is_active = db.Column(db.Boolean, default=True)
    max_interactions = db.Column(db.Integer, default=30)
    max_duration_minutes = db.Column(db.Integer, default=30)
    allow_student_end = db.Column(db.Boolean, default=True)
    ai_can_end = db.Column(db.Boolean, default=True)

    # Opening message (first message from AI persona)
    opening_message = db.Column(db.Text, nullable=True)

    # Who starts the conversation
    student_starts = db.Column(db.Boolean, default=False)  # False = bot starts, True = student starts

    # File upload requirement
    require_file_upload = db.Column(db.Boolean, default=False)
    file_upload_label = db.Column(db.String(100), default='Fichier')  # e.g., "Votre CV"
    file_upload_description = db.Column(db.Text, nullable=True)  # Instructions for the file
    file_upload_prompt_injection = db.Column(db.Text, nullable=True)  # How to inject file content in prompt

    # Availability
    available_from = db.Column(db.DateTime, nullable=True)
    available_until = db.Column(db.DateTime, nullable=True)

    # Tenant and ownership
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    criteria = db.relationship('EvaluationCriterion', back_populates='interview',
                               cascade='all, delete-orphan', order_by='EvaluationCriterion.order')
    sessions = db.relationship('InterviewSession', back_populates='interview',
                               cascade='all, delete-orphan', lazy='dynamic')
    groups = db.relationship('Group', secondary=interview_groups,
                             backref=db.backref('interviews', lazy='dynamic'), lazy='dynamic')
    created_by = db.relationship('User', foreign_keys=[created_by_id], backref='created_interviews')
    tenant = db.relationship('Tenant', backref='interviews')

    def __repr__(self):
        return f'<Interview {self.title}>'

    def is_available_for_group(self, group_id):
        """Check if interview is assigned to a specific group."""
        if not self.groups.count():
            return True
        return self.groups.filter_by(id=group_id).first() is not None

    def is_available_for_user(self, user):
        """Check if interview is available for a user (any of their groups)."""
        if not self.groups.count():
            return True
        user_group_ids = set(g.id for g in user.groups)
        interview_group_ids = set(g.id for g in self.groups)
        return bool(user_group_ids & interview_group_ids)

    def is_open(self):
        """Check if interview is currently open (within time window)."""
        now = datetime.now()
        if self.available_from and now < self.available_from:
            return False
        if self.available_until and now > self.available_until:
            return False
        return self.is_active

    def get_url_identifier(self):
        """Get the URL identifier (slug if available, then uid, finally id)."""
        if self.slug:
            return self.slug
        if self.uid:
            return self.uid
        return str(self.id)

    def get_max_score(self):
        """Calculate maximum possible score from all criteria."""
        return sum(c.max_points for c in self.criteria)


class EvaluationCriterion(db.Model):
    """Individual evaluation criterion for multi-criteria grading."""
    __tablename__ = 'evaluation_criteria'

    id = db.Column(db.Integer, primary_key=True)
    interview_id = db.Column(db.Integer, db.ForeignKey('interviews.id'), nullable=False)

    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    max_points = db.Column(db.Float, default=5.0)
    order = db.Column(db.Integer, default=0)

    # Evaluation guidance for AI
    evaluation_hints = db.Column(db.Text)

    interview = db.relationship('Interview', back_populates='criteria')
    scores = db.relationship('CriterionScore', back_populates='criterion', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<EvaluationCriterion {self.name} ({self.max_points}pts)>'


class InterviewSession(UIDMixin, db.Model):
    """A student's interview attempt - tracks state and enables resumption."""
    __tablename__ = 'interview_sessions'

    # Status constants
    STATUS_IN_PROGRESS = 'in_progress'
    STATUS_ENDED_BY_STUDENT = 'ended_by_student'
    STATUS_ENDED_BY_AI = 'ended_by_ai'
    STATUS_ENDED_BY_LIMIT = 'ended_by_limit'
    STATUS_ENDED_BY_TIMEOUT = 'ended_by_timeout'
    STATUS_EVALUATING = 'evaluating'
    STATUS_COMPLETED = 'completed'
    STATUS_ERROR = 'error'

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(100), unique=True, nullable=True, index=True)  # Coolname-based identifier
    interview_id = db.Column(db.Integer, db.ForeignKey('interviews.id'), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    # Session state
    status = db.Column(db.String(30), default=STATUS_IN_PROGRESS)
    interaction_count = db.Column(db.Integer, default=0)

    # Uploaded file (if required by interview)
    uploaded_file_name = db.Column(db.String(255), nullable=True)
    uploaded_file_content = db.Column(db.Text, nullable=True)  # Extracted text content

    # Timing
    started_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_activity_at = db.Column(db.DateTime, default=datetime.utcnow)
    ended_at = db.Column(db.DateTime, nullable=True)

    # End reason (for analytics)
    end_reason = db.Column(db.String(50), nullable=True)

    # Scoring
    total_score = db.Column(db.Float, default=0.0)
    max_score = db.Column(db.Float, default=0.0)

    # AI's final summary/feedback
    ai_summary = db.Column(db.Text, nullable=True)

    # Admin feedback
    admin_comment = db.Column(db.Text, nullable=True)

    # Test mode flag (for admin previews)
    is_test = db.Column(db.Boolean, default=False)

    # Relationships
    interview = db.relationship('Interview', back_populates='sessions')
    user = db.relationship('User', backref=db.backref('interview_sessions', lazy='dynamic'))
    messages = db.relationship('InterviewMessage', back_populates='session',
                               cascade='all, delete-orphan', order_by='InterviewMessage.created_at')
    scores = db.relationship('CriterionScore', back_populates='session',
                             cascade='all, delete-orphan')

    def __repr__(self):
        return f'<InterviewSession User:{self.user_id} Interview:{self.interview_id}>'

    def get_duration_minutes(self):
        """Get session duration in minutes."""
        end = self.ended_at or datetime.utcnow()
        delta = end - self.started_at
        return int(delta.total_seconds() / 60)

    def get_score_percentage(self):
        """Get score as percentage."""
        if self.max_score == 0:
            return 0
        return round((self.total_score / self.max_score) * 100, 1)

    def is_resumable(self):
        """Check if session can be resumed."""
        return self.status == self.STATUS_IN_PROGRESS

    def can_send_message(self):
        """Check if user can still send messages."""
        if self.status != self.STATUS_IN_PROGRESS:
            return False
        if self.interaction_count >= self.interview.max_interactions:
            return False
        # Check timeout
        elapsed = (datetime.utcnow() - self.started_at).total_seconds() / 60
        if elapsed >= self.interview.max_duration_minutes:
            return False
        return True

    def get_url_identifier(self):
        """Get the URL identifier (uid)."""
        return self.uid if self.uid else str(self.id)


class InterviewMessage(db.Model):
    """Individual message in an interview conversation."""
    __tablename__ = 'interview_messages'

    ROLE_USER = 'user'
    ROLE_ASSISTANT = 'assistant'
    ROLE_SYSTEM = 'system'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('interview_sessions.id'), nullable=False)

    role = db.Column(db.String(20), nullable=False)
    content = db.Column(db.Text, nullable=False)

    # Token tracking (for context management)
    token_count = db.Column(db.Integer, nullable=True)

    # Timing
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # AI detected end signal in this message
    contains_end_signal = db.Column(db.Boolean, default=False)

    session = db.relationship('InterviewSession', back_populates='messages')

    def __repr__(self):
        return f'<InterviewMessage {self.role}: {self.content[:30]}...>'


class CriterionScore(db.Model):
    """Score for a specific criterion in a session."""
    __tablename__ = 'criterion_scores'

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(db.Integer, db.ForeignKey('interview_sessions.id'), nullable=False)
    criterion_id = db.Column(db.Integer, db.ForeignKey('evaluation_criteria.id'), nullable=False)

    score = db.Column(db.Float, default=0.0)
    max_score = db.Column(db.Float, default=0.0)
    feedback = db.Column(db.Text)

    session = db.relationship('InterviewSession', back_populates='scores')
    criterion = db.relationship('EvaluationCriterion', back_populates='scores')

    def __repr__(self):
        return f'<CriterionScore {self.criterion.name if self.criterion else "?"}: {self.score}/{self.max_score}>'

    def get_percentage(self):
        """Get score as percentage."""
        if self.max_score == 0:
            return 0
        return round((self.score / self.max_score) * 100, 1)


# Register event listeners for auto-generating UIDs
event.listen(Interview, 'before_insert', init_uid_on_create)
event.listen(InterviewSession, 'before_insert', init_uid_on_create)
