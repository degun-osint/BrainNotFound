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

# Graders of a quiz, in addition to its author (instructors or organization admins)
quiz_graders = db.Table('quiz_graders',
    db.Column('quiz_id', db.Integer, db.ForeignKey('quizzes.id', ondelete='CASCADE'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), primary_key=True),
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

    # Grading trust: 'direct' = the AI grade is final, 'review' = a grader validates each paper
    GRADING_DIRECT = 'direct'
    GRADING_REVIEW = 'review'
    grading_mode = db.Column(db.String(10), default=GRADING_DIRECT)
    contest_days = db.Column(db.Integer, default=7)  # Days to contest a grade once published (0 = no contest)
    notify_learners = db.Column(db.Boolean, default=True)  # Email learners when a grader validates or handles a contest
    # Grouped email to graders: something happened since digest_pending_since, last email at digest_sent_at
    digest_pending_since = db.Column(db.DateTime, nullable=True)
    digest_sent_at = db.Column(db.DateTime, nullable=True)
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
    graders = db.relationship('User', secondary=quiz_graders, lazy='dynamic',
                              backref=db.backref('graded_quizzes', lazy='dynamic'))

    def __repr__(self):
        return f'<Quiz {self.title}>'

    @property
    def needs_review(self):
        return self.grading_mode == self.GRADING_REVIEW

    def grader_ids(self):
        """Author and designated graders."""
        ids = {row[0] for row in db.session.query(quiz_graders.c.user_id).filter(quiz_graders.c.quiz_id == self.id)}
        if self.created_by_id:
            ids.add(self.created_by_id)
        return ids

    def mark_digest_pending(self):
        """Something for the graders (paper to validate, contest): include it in the next digest."""
        if self.digest_pending_since is None:
            self.digest_pending_since = datetime.utcnow()

    def is_available_for_group(self, group_id):
        """Check if quiz is assigned to a specific group."""
        return self.groups.filter_by(id=group_id).first() is not None

    def is_available_for_user(self, user):
        """Check if quiz is assigned to one of the user's groups.

        A quiz without any group is visible to no learner (only to its admins).
        """
        user_group_ids = {g.id for g in user.groups}
        return any(g.id in user_group_ids for g in self.groups)

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
    STATUS_REVIEW = 'review'  # graded, waiting for a grader (review mode, AI quota reached or AI failure)

    id = db.Column(db.Integer, primary_key=True)
    uid = db.Column(db.String(100), unique=True, nullable=True, index=True)  # Coolname-based identifier
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    quiz_id = db.Column(db.Integer, db.ForeignKey('quizzes.id'), nullable=False)
    total_score = db.Column(db.Float, default=0.0)
    max_score = db.Column(db.Float, default=0.0)
    started_at = db.Column(db.DateTime, nullable=True)  # When quiz was started
    submitted_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_late = db.Column(db.Boolean, default=False)  # Submitted after time limit
    grading_status = db.Column(db.String(20), default='pending')  # pending, grading, completed, review, error
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

    # Publication: when the grade became final (AI in direct mode, or a grader's validation);
    # the contest delay starts here
    graded_at = db.Column(db.DateTime, nullable=True)
    # Why a paper waits (status review): 'mode' = AI graded it, a grader validates;
    # 'ai' = the AI could not grade some answers (quota, error): a grader must grade them
    REVIEW_MODE = 'mode'
    REVIEW_AI = 'ai'
    review_reason = db.Column(db.String(10), nullable=True)
    reviewed_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    reviewed_at = db.Column(db.DateTime, nullable=True)

    # Relationships
    user = db.relationship('User', back_populates='responses', foreign_keys=[user_id])
    reviewed_by = db.relationship('User', foreign_keys=[reviewed_by_id])
    quiz = db.relationship('Quiz', back_populates='responses')
    answers = db.relationship('Answer', back_populates='quiz_response', cascade='all, delete-orphan')

    def get_url_identifier(self):
        """Get the URL identifier (uid)."""
        return self.uid if self.uid else str(self.id)

    def publish(self, reviewer=None):
        """The grade becomes final (the contest delay starts now)."""
        now = datetime.utcnow()
        self.grading_status = self.STATUS_COMPLETED
        self.review_reason = None
        self.graded_at = now
        if reviewer is not None:
            self.reviewed_by_id = reviewer.id
            self.reviewed_at = now

    def contest_deadline(self):
        """Last moment the learner may contest, or None if contests are closed or not possible."""
        from datetime import timedelta
        days = self.quiz.contest_days or 0
        if self.is_test or days <= 0 or self.grading_status != self.STATUS_COMPLETED or not self.graded_at:
            return None
        return self.graded_at + timedelta(days=days)

    def can_contest(self):
        deadline = self.contest_deadline()
        return deadline is not None and datetime.utcnow() <= deadline

    def recompute_total(self):
        self.total_score = sum(a.score or 0 for a in self.answers)

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
    contest = db.relationship('AnswerContest', back_populates='answer', uselist=False, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Answer Q:{self.question_id} Score:{self.score}/{self.max_score}>'


class AnswerContest(db.Model):
    """A learner contests the grade of one answer (once per answer), a grader resolves it."""
    __tablename__ = 'answer_contests'

    STATUS_OPEN = 'open'
    STATUS_ACCEPTED = 'accepted'  # grade changed
    STATUS_REJECTED = 'rejected'  # grade kept

    id = db.Column(db.Integer, primary_key=True)
    answer_id = db.Column(db.Integer, db.ForeignKey('answers.id', ondelete='CASCADE'), nullable=False, unique=True)
    reason = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(10), default=STATUS_OPEN, nullable=False, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    reply = db.Column(db.Text, nullable=True)
    score_before = db.Column(db.Float, nullable=True)
    score_after = db.Column(db.Float, nullable=True)
    resolved_by_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='SET NULL'), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)

    answer = db.relationship('Answer', back_populates='contest')
    resolved_by = db.relationship('User', foreign_keys=[resolved_by_id])

    @property
    def is_open(self):
        return self.status == self.STATUS_OPEN


# Register event listeners for auto-generating UIDs
event.listen(Quiz, 'before_insert', init_uid_on_create)
event.listen(QuizResponse, 'before_insert', init_uid_on_create)