from app import db
from datetime import datetime
from sqlalchemy import event
from app.models.mixins import UIDMixin, init_uid_on_create

# Association table for Quiz-Group many-to-many relationship
quiz_groups = db.Table('quiz_groups',
    db.Column('quiz_id', db.Integer, db.ForeignKey('quizzes.id'), primary_key=True),
    db.Column('group_id', db.Integer, db.ForeignKey('groups.id'), primary_key=True),
    db.Column('assigned_at', db.DateTime, default=datetime.utcnow)
)


class Quiz(UIDMixin, db.Model):
    __tablename__ = 'quizzes'

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(100), unique=True, nullable=True, index=True)  # Coolname-based identifier
    slug = db.Column(db.String(100), unique=True, nullable=True, index=True)  # User-defined URL-friendly identifier
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)
    markdown_content = db.Column(db.Text, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    randomize_questions = db.Column(db.Boolean, default=False)  # Shuffle question order for each attempt
    randomize_options = db.Column(db.Boolean, default=False)  # Shuffle MCQ options order
    one_question_per_page = db.Column(db.Boolean, default=False)  # Exam mode: one question at a time
    time_limit_minutes = db.Column(db.Integer, nullable=True)  # Optional time limit in minutes
    available_from = db.Column(db.DateTime, nullable=True)  # When quiz becomes available (None = immediately)
    available_until = db.Column(db.DateTime, nullable=True)  # When quiz closes (None = no deadline)
    grading_severity = db.Column(db.String(20), default='modere')  # gentil, modere, severe
    grading_mood = db.Column(db.JSON, default=list)  # List of moods: neutre, jovial, severe, taquin, encourageant, sarcastique
    class_analysis_result = db.Column(db.JSON, nullable=True)  # AI class-wide analysis result
    created_by_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)  # Creator of the quiz
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Tenant relationship (nullable for backward compatibility)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenants.id'), nullable=True, index=True)

    # Relationships
    questions = db.relationship('Question', back_populates='quiz', cascade='all, delete-orphan', lazy='dynamic')
    responses = db.relationship('QuizResponse', back_populates='quiz', cascade='all, delete-orphan', lazy='dynamic')
    groups = db.relationship('Group', secondary=quiz_groups, backref=db.backref('quizzes', lazy='dynamic'), lazy='dynamic')
    created_by = db.relationship('User', foreign_keys=[created_by_id], backref='created_quizzes')

    def __repr__(self):
        return f'<Quiz {self.title}>'

    def is_available_for_group(self, group_id):
        """Check if quiz is assigned to a specific group."""
        if not self.groups.count():  # No groups assigned = available to all
            return True
        return self.groups.filter_by(id=group_id).first() is not None

    def is_available_for_user(self, user):
        """Check if quiz is available for a user (any of their groups)."""
        if not self.groups.count():  # No groups assigned = available to all
            return True
        # Check if any of the user's groups match the quiz's groups
        user_group_ids = set(g.id for g in user.groups)
        quiz_group_ids = set(g.id for g in self.groups)
        return bool(user_group_ids & quiz_group_ids)

    def is_open(self):
        """Check if quiz is currently open (within time window)."""
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


class Question(db.Model):
    __tablename__ = 'questions'

    id = db.Column(db.Integer, primary_key=True)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    question_type = db.Column(db.String(20), nullable=False)  # 'mcq' or 'open'
    question_text = db.Column(db.Text, nullable=False)
    points = db.Column(db.Float, default=1.0)
    order = db.Column(db.Integer, default=0)

    # For MCQ questions
    options = db.Column(db.JSON)  # List of options
    correct_answers = db.Column(db.JSON)  # List of correct option indices
    allow_multiple = db.Column(db.Boolean, default=False)  # Allow multiple answers (checkbox vs radio)

    # For open questions
    expected_answer = db.Column(db.Text)  # Model answer for comparison

    # Images
    images = db.Column(db.JSON, nullable=True)  # List of {"filename": "...", "alt": "..."}

    # Relationships
    quiz = db.relationship('Quiz', back_populates='questions')
    answers = db.relationship('Answer', back_populates='question', cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Question {self.id} - {self.question_type}>'


class QuizResponse(UIDMixin, db.Model):
    __tablename__ = 'quiz_responses'

    # Grading status constants
    STATUS_PENDING = 'pending'
    STATUS_GRADING = 'grading'
    STATUS_COMPLETED = 'completed'
    STATUS_ERROR = 'error'

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(100), unique=True, nullable=True, index=True)  # Coolname-based identifier
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    total_score = db.Column(db.Float, default=0.0)
    max_score = db.Column(db.Float, default=0.0)
    started_at = db.Column(db.DateTime, nullable=True)  # When quiz was started
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_late = db.Column(db.Boolean, default=False)  # Submitted after time limit
    grading_status = db.Column(db.String(20), default='pending')  # pending, grading, completed, error
    grading_progress = db.Column(db.Integer, default=0)  # Number of questions graded
    grading_total = db.Column(db.Integer, default=0)  # Total questions to grade

    # Anti-cheat tracking
    focus_events = db.Column(db.JSON, nullable=True)  # [{question_id, timestamp, event_type}]
    total_focus_lost = db.Column(db.Integer, default=0)  # Total focus loss events
    ai_analysis_status = db.Column(db.String(20), nullable=True)  # pending, completed
    ai_analysis_result = db.Column(db.JSON, nullable=True)  # AI anomaly detection result

    # Test/preview mode
    is_test = db.Column(db.Boolean, default=False)  # True if this is an admin test response

    # Admin feedback
    admin_comment = db.Column(db.Text, nullable=True)  # Manual comment from admin/teacher

    # Relationships
    user = db.relationship('User', back_populates='responses')
    quiz = db.relationship('Quiz', back_populates='responses')
    answers = db.relationship('Answer', back_populates='quiz_response', cascade='all, delete-orphan')

    def get_url_identifier(self):
        """Get the URL identifier (uid)."""
        return self.uid if self.uid else str(self.id)

    def __repr__(self):
        return f'<QuizResponse User:{self.user_id} Quiz:{self.quiz_id}>'


class Answer(db.Model):
    __tablename__ = 'answers'

    id = db.Column(db.Integer, primary_key=True)
    quiz_response_id = db.Column(db.Integer, db.ForeignKey('quiz_responses.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)

    # For MCQ answers
    selected_options = db.Column(db.JSON)  # List of selected option indices

    # For open answers
    answer_text = db.Column(db.Text)

    # Grading
    score = db.Column(db.Float, default=0.0)
    max_score = db.Column(db.Float, default=0.0)
    ai_feedback = db.Column(db.Text)  # Claude's evaluation feedback

    # Time tracking (anti-cheat)
    time_spent_seconds = db.Column(db.Integer, nullable=True)  # Time spent on this question
    focus_lost_count = db.Column(db.Integer, default=0)  # Focus loss events on this question

    # Relationships
    quiz_response = db.relationship('QuizResponse', back_populates='answers')
    question = db.relationship('Question', back_populates='answers')

    def __repr__(self):
        return f'<Answer Q:{self.question_id} Score:{self.score}/{self.max_score}>'


# Register event listeners for auto-generating UIDs
event.listen(Quiz, 'before_insert', init_uid_on_create)
event.listen(QuizResponse, 'before_insert', init_uid_on_create)