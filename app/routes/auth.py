from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, Response
from flask_login import login_user, logout_user, login_required, current_user
from urllib.parse import urlparse
from datetime import datetime
import json
from app import db, limiter
from app.models.user import User
from app.models.group import Group
from app.utils.email_sender import send_verification_email, send_reset_email

auth_bp = Blueprint('auth', __name__)

# Rate limit error handler
@auth_bp.errorhandler(429)
def ratelimit_handler(e):
    flash('Trop de tentatives. Veuillez reessayer dans quelques minutes.', 'error')
    return redirect(request.url)


def is_safe_url(target):
    """Check if the URL is safe for redirect (prevents open redirect attacks)."""
    if not target:
        return False
    ref_url = urlparse(request.host_url)
    test_url = urlparse(target)
    # Allow relative URLs (no scheme or netloc) or same host
    return test_url.scheme in ('', 'http', 'https') and ref_url.netloc == test_url.netloc or \
           (not test_url.scheme and not test_url.netloc)

@auth_bp.route('/')
def index():
    if current_user.is_authenticated:
        if current_user.is_any_admin:
            return redirect(url_for('admin.dashboard'))
        else:
            return redirect(url_for('quiz.dashboard'))
    # Show landing page for non-authenticated visitors
    return render_template('landing.html')

@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        user = User.query.filter_by(username=username).first()

        if user and user.check_password(password):
            # Check if email is verified
            if not user.email_verified:
                flash('Veuillez verifier votre adresse email avant de vous connecter.', 'warning')
                return render_template('auth/login.html', unverified_email=user.email)

            # Record login info
            user.record_login(request.remote_addr)
            db.session.commit()

            login_user(user)
            next_page = request.args.get('next')
            # Validate redirect URL to prevent open redirect attacks
            if not next_page or not is_safe_url(next_page):
                next_page = url_for('auth.index')
            return redirect(next_page)
        else:
            flash('Identifiants incorrects', 'error')

    return render_template('auth/login.html')

@auth_bp.route('/register', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))

    if request.method == 'POST':
        username = request.form.get('username')
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        email = request.form.get('email')
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')
        join_code = request.form.get('join_code', '').strip().upper()

        # Validation
        if not username or not email or not password or not join_code or not first_name or not last_name:
            flash('Tous les champs sont requis', 'error')
        elif password != password_confirm:
            flash('Les mots de passe ne correspondent pas', 'error')
        elif User.query.filter_by(username=username).first():
            flash('Ce nom d\'utilisateur existe déjà', 'error')
        elif User.query.filter_by(email=email).first():
            flash('Cette adresse email est déjà utilisée', 'error')
        else:
            # Validate join code
            group = Group.query.filter_by(join_code=join_code, is_active=True).first()
            if not group:
                flash('Code de groupe invalide ou inactif', 'error')
            elif group.is_full():
                flash('Ce groupe a atteint sa limite de membres', 'error')
            else:
                user = User(
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    is_admin=False,
                    email_verified=False,  # Requires email verification
                    group_id=group.id  # Legacy field
                )
                user.set_password(password)
                db.session.add(user)
                db.session.flush()  # Get user ID before adding to group

                # Add to group via new many-to-many relationship
                user.add_to_group(group, role='member')

                # Send verification email
                if send_verification_email(user):
                    db.session.commit()
                    return redirect(url_for('auth.verification_sent', email=email))
                else:
                    db.session.rollback()
                    flash('Erreur lors de l\'envoi de l\'email de verification. Veuillez reessayer.', 'error')

    return render_template('auth/register.html')

@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('Vous avez été déconnecté.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/verification-sent')
def verification_sent():
    """Page shown after registration to inform user to check email."""
    email = request.args.get('email', '')
    return render_template('auth/verification_sent.html', email=email)


@auth_bp.route('/verify/<token>')
def verify_email(token):
    """Verify user email with token."""
    user = User.verify_email_token(token)

    if user:
        user.email_verified = True
        user.clear_verification_token()
        db.session.commit()
        flash('Votre adresse email a ete verifiee ! Vous pouvez maintenant vous connecter.', 'success')
    else:
        flash('Le lien de verification est invalide ou a expire.', 'error')

    return redirect(url_for('auth.login'))


@auth_bp.route('/resend-verification', methods=['GET', 'POST'])
@limiter.limit("3 per minute", methods=["POST"])
def resend_verification():
    """Resend verification email."""
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()

        if not email:
            flash('Veuillez entrer votre adresse email.', 'error')
        else:
            user = User.query.filter_by(email=email).first()

            if user and not user.email_verified:
                if send_verification_email(user):
                    db.session.commit()
                    flash('Un nouvel email de verification a ete envoye.', 'success')
                else:
                    flash('Erreur lors de l\'envoi de l\'email. Veuillez reessayer.', 'error')
            else:
                # Generic message to avoid email enumeration
                flash('Si cette adresse est associee a un compte non verifie, un email a ete envoye.', 'info')

            return redirect(url_for('auth.login'))

    return render_template('auth/resend_verification.html')


@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
@limiter.limit("3 per minute", methods=["POST"])
def forgot_password():
    """Request password reset."""
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()

        if not email:
            flash('Veuillez entrer votre adresse email.', 'error')
        else:
            user = User.query.filter_by(email=email).first()

            if user:
                if send_reset_email(user):
                    db.session.commit()

            # Always show same message to avoid email enumeration
            flash('Si cette adresse est associee a un compte, un email de reinitialisation a ete envoye.', 'info')
            return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')


@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=["POST"])
def reset_password(token):
    """Reset password with token."""
    if current_user.is_authenticated:
        return redirect(url_for('auth.index'))

    user = User.verify_reset_token(token)

    if not user:
        flash('Le lien de reinitialisation est invalide ou a expire.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        password_confirm = request.form.get('password_confirm')

        if not password:
            flash('Veuillez entrer un mot de passe.', 'error')
        elif password != password_confirm:
            flash('Les mots de passe ne correspondent pas.', 'error')
        else:
            user.set_password(password)
            user.clear_reset_token()
            db.session.commit()
            flash('Votre mot de passe a ete reinitialise ! Vous pouvez maintenant vous connecter.', 'success')
            return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    """User profile page."""
    if request.method == 'POST':
        action = request.form.get('action')

        if action == 'update_info':
            first_name = request.form.get('first_name', '').strip()
            last_name = request.form.get('last_name', '').strip()

            if first_name and last_name:
                current_user.first_name = first_name
                current_user.last_name = last_name
                db.session.commit()
                flash('Informations mises a jour.', 'success')
            else:
                flash('Le prenom et le nom sont requis.', 'error')

        elif action == 'change_password':
            current_password = request.form.get('current_password')
            new_password = request.form.get('new_password')
            confirm_password = request.form.get('confirm_password')

            if not current_user.check_password(current_password):
                flash('Mot de passe actuel incorrect.', 'error')
            elif not new_password:
                flash('Veuillez entrer un nouveau mot de passe.', 'error')
            elif new_password != confirm_password:
                flash('Les nouveaux mots de passe ne correspondent pas.', 'error')
            else:
                current_user.set_password(new_password)
                db.session.commit()
                flash('Mot de passe modifie avec succes.', 'success')

        elif action == 'change_email':
            new_email = request.form.get('new_email', '').strip()
            password = request.form.get('email_password')

            if not current_user.check_password(password):
                flash('Mot de passe incorrect.', 'error')
            elif not new_email:
                flash('Veuillez entrer une adresse email.', 'error')
            elif User.query.filter(User.email == new_email, User.id != current_user.id).first():
                flash('Cette adresse email est deja utilisee.', 'error')
            else:
                current_user.email = new_email
                current_user.email_verified = False
                if send_verification_email(current_user):
                    db.session.commit()
                    flash('Un email de verification a ete envoye a votre nouvelle adresse.', 'success')
                else:
                    db.session.rollback()
                    flash('Erreur lors de l\'envoi de l\'email de verification.', 'error')

        return redirect(url_for('auth.profile'))

    return render_template('auth/profile.html')


@auth_bp.route('/join-group', methods=['POST'])
@login_required
def join_group():
    """Allow a logged-in user to join an additional group."""
    join_code = request.form.get('join_code', '').strip().upper()

    if not join_code:
        flash('Veuillez entrer un code de groupe', 'error')
        return redirect(url_for('auth.profile'))

    group = Group.query.filter_by(join_code=join_code, is_active=True).first()

    if not group:
        flash('Code de groupe invalide ou inactif', 'error')
    elif group.is_full():
        flash('Ce groupe a atteint sa limite de membres', 'error')
    elif current_user.is_in_group(group):
        flash('Vous êtes déjà membre de ce groupe', 'warning')
    else:
        current_user.add_to_group(group, role='member')
        db.session.commit()
        flash(f'Vous avez rejoint le groupe "{group.name}"', 'success')

    return redirect(url_for('auth.profile'))


# ============================================================
# RGPD Routes (Data Export & Account Deletion)
# ============================================================

@auth_bp.route('/profile/export-data')
@login_required
def export_data():
    """Export all user data as JSON (RGPD compliance)."""
    from app.models.quiz import QuizResponse, Answer
    from app.models.interview import InterviewSession, InterviewMessage

    # Collect user data
    user_data = {
        'export_date': datetime.now().isoformat(),
        'user': {
            'id': current_user.id,
            'username': current_user.username,
            'email': current_user.email,
            'first_name': current_user.first_name,
            'last_name': current_user.last_name,
            'email_verified': current_user.email_verified,
            'created_at': current_user.created_at.isoformat() if current_user.created_at else None,
            'last_login': current_user.last_login.isoformat() if current_user.last_login else None,
            'last_login_ip': current_user.last_login_ip
        },
        'groups': [],
        'quiz_responses': [],
        'interview_sessions': []
    }

    # Groups
    for group in current_user.groups:
        user_data['groups'].append({
            'name': group.name,
            'role': current_user.get_role_in_group(group.id),
            'joined_at': None  # Would need to track this in the model
        })

    # Quiz responses with answers
    responses = QuizResponse.query.filter_by(user_id=current_user.id).all()
    for response in responses:
        response_data = {
            'quiz_title': response.quiz.title,
            'submitted_at': response.submitted_at.isoformat() if response.submitted_at else None,
            'started_at': response.started_at.isoformat() if response.started_at else None,
            'total_score': response.total_score,
            'max_score': response.max_score,
            'is_late': response.is_late,
            'answers': []
        }

        for answer in response.answers:
            answer_data = {
                'question_text': answer.question.question_text,
                'question_type': answer.question.question_type,
                'answer_text': answer.answer_text,
                'selected_options': answer.selected_options,
                'score': answer.score,
                'max_score': answer.max_score,
                'ai_feedback': answer.ai_feedback
            }
            response_data['answers'].append(answer_data)

        user_data['quiz_responses'].append(response_data)

    # Interview sessions with messages
    sessions = InterviewSession.query.filter_by(user_id=current_user.id, is_test=False).all()
    for session in sessions:
        session_data = {
            'interview_title': session.interview.title,
            'status': session.status,
            'started_at': session.started_at.isoformat() if session.started_at else None,
            'ended_at': session.ended_at.isoformat() if session.ended_at else None,
            'total_score': session.total_score,
            'max_score': session.max_score,
            'ai_summary': session.ai_summary,
            'messages': []
        }

        for message in session.messages:
            if message.role != 'system':  # Skip system messages
                session_data['messages'].append({
                    'role': message.role,
                    'content': message.content,
                    'created_at': message.created_at.isoformat() if message.created_at else None
                })

        user_data['interview_sessions'].append(session_data)

    # Return as downloadable JSON file
    json_data = json.dumps(user_data, ensure_ascii=False, indent=2)
    filename = f"mes-donnees-{current_user.username}-{datetime.now().strftime('%Y%m%d')}.json"

    return Response(
        json_data,
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename="{filename}"'}
    )


@auth_bp.route('/profile/delete-account', methods=['POST'])
@login_required
def delete_account():
    """Delete user account and all associated data (RGPD compliance)."""
    from app.models.quiz import QuizResponse, Answer
    from app.models.interview import InterviewSession, InterviewMessage, CriterionScore
    from app.models.user import user_groups

    password = request.form.get('password')
    confirm_text = request.form.get('confirm_text', '').strip()

    # Verify password
    if not current_user.check_password(password):
        flash('Mot de passe incorrect.', 'error')
        return redirect(url_for('auth.profile'))

    # Verify confirmation text
    if confirm_text != 'SUPPRIMER':
        flash('Veuillez taper SUPPRIMER pour confirmer.', 'error')
        return redirect(url_for('auth.profile'))

    # Prevent admin accounts from self-deleting
    if current_user.is_admin:
        flash('Les comptes super-administrateurs ne peuvent pas etre supprimes via cette interface.', 'error')
        return redirect(url_for('auth.profile'))

    user_id = current_user.id
    username = current_user.username

    try:
        # Delete interview data
        sessions = InterviewSession.query.filter_by(user_id=user_id).all()
        for session in sessions:
            # Delete criterion scores for this session
            CriterionScore.query.filter_by(session_id=session.id).delete()
            # Delete messages
            InterviewMessage.query.filter_by(session_id=session.id).delete()
        # Delete sessions
        InterviewSession.query.filter_by(user_id=user_id).delete()

        # Delete quiz data
        responses = QuizResponse.query.filter_by(user_id=user_id).all()
        for response in responses:
            Answer.query.filter_by(quiz_response_id=response.id).delete()
        QuizResponse.query.filter_by(user_id=user_id).delete()

        # Remove from groups (explicit delete from association table)
        db.session.execute(user_groups.delete().where(user_groups.c.user_id == user_id))

        # Logout before deleting
        logout_user()

        # Delete user
        User.query.filter_by(id=user_id).delete()

        db.session.commit()

        flash(f'Le compte "{username}" a ete supprime avec succes.', 'success')
        return redirect(url_for('auth.login'))

    except Exception as e:
        db.session.rollback()
        import traceback
        from flask import current_app
        current_app.logger.error(f'Error deleting account {username}: {str(e)}')
        current_app.logger.error(traceback.format_exc())
        flash('Une erreur est survenue lors de la suppression du compte.', 'error')
        return redirect(url_for('auth.profile'))


# ============================================================
# Public Page Routes
# ============================================================

@auth_bp.route('/page/<slug>')
def view_page(slug):
    """View a public custom page."""
    from app.models.page import Page

    page = Page.query.filter_by(slug=slug, is_published=True).first_or_404()
    return render_template('page/view.html', page=page, is_preview=False)
