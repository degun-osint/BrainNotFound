"""
Interview routes - Admin and student routes for conversational AI interviews.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from datetime import datetime
import json
import re
from app import db
from app.models.interview import (
    Interview, EvaluationCriterion, InterviewSession,
    InterviewMessage, CriterionScore, interview_groups
)
from app.models.group import Group
from app.models.tenant import Tenant
from app.utils.claude_interviewer import ClaudeInterviewer, get_criteria_templates

interview_bp = Blueprint('interview', __name__)


# ============================================================================
# Context Processor - Tenant Selector for Admin Pages
# ============================================================================

def get_tenant_context():
    """Get the current tenant context from session."""
    from flask import session
    tenant_id = session.get('admin_tenant_context')
    if tenant_id:
        return Tenant.query.get(tenant_id)
    return None


def get_accessible_tenants():
    """Get list of tenants the current user can access."""
    if current_user.is_superadmin:
        return Tenant.query.filter_by(is_active=True).order_by(Tenant.name).all()
    elif current_user.is_tenant_admin:
        return list(current_user.admin_tenants.filter_by(is_active=True).order_by(Tenant.name))
    return []


@interview_bp.context_processor
def inject_tenant_context():
    """Make tenant context available in all interview admin templates."""
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


# ============================================================================
# Helper Functions
# ============================================================================

def get_interview_by_identifier(identifier):
    """Get an interview by ID or slug."""
    try:
        interview_id = int(identifier)
        return Interview.query.get(interview_id)
    except (ValueError, TypeError):
        pass
    return Interview.query.filter_by(slug=identifier).first()


def admin_required(f):
    """Decorator to require admin access."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.is_any_admin:
            flash('Acces non autorise', 'error')
            return redirect(url_for('quiz.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def get_admin_groups():
    """Get groups accessible to current admin."""
    if current_user.is_admin:  # Superadmin
        return Group.query.order_by(Group.name).all()
    # Tenant/Group admin - get their admin groups
    return current_user.get_admin_groups()


def get_groups_by_tenant():
    """Get groups organized by tenant for admin views."""
    groups = get_admin_groups()
    groups_by_tenant = {}

    for group in groups:
        tenant_id = group.tenant_id or 0
        if tenant_id not in groups_by_tenant:
            tenant = Tenant.query.get(tenant_id) if tenant_id else None
            groups_by_tenant[tenant_id] = {
                'tenant': tenant,
                'name': tenant.name if tenant else 'Sans organisation',
                'groups': []
            }
        groups_by_tenant[tenant_id]['groups'].append(group)

    return groups_by_tenant


# ============================================================================
# Student Routes
# ============================================================================

@interview_bp.route('/list')
@login_required
def interview_list():
    """List available interviews for students."""
    if current_user.is_any_admin:
        return redirect(url_for('interview.admin_list'))

    now = datetime.now()

    # Get user's groups
    user_groups = list(current_user.groups)
    user_group_ids = [g.id for g in user_groups]

    # Base query for active interviews
    base_query = Interview.query.filter(
        Interview.is_active == True,
        db.or_(Interview.available_from == None, Interview.available_from <= now),
        db.or_(Interview.available_until == None, Interview.available_until >= now)
    )

    # Filter by user's groups
    if user_group_ids:
        interviews_with_groups = db.session.query(interview_groups.c.interview_id).distinct()
        base_query = base_query.filter(
            db.or_(
                Interview.groups.any(Group.id.in_(user_group_ids)),
                ~Interview.id.in_(interviews_with_groups)
            )
        )
    else:
        interviews_with_groups = db.session.query(interview_groups.c.interview_id).distinct()
        base_query = base_query.filter(~Interview.id.in_(interviews_with_groups))

    interviews = base_query.order_by(Interview.created_at.desc()).all()

    # Get user's sessions for each interview
    user_sessions = {}
    for interview in interviews:
        session = InterviewSession.query.filter_by(
            user_id=current_user.id,
            interview_id=interview.id
        ).first()
        if session:
            user_sessions[interview.id] = session

    return render_template(
        'interview/list.html',
        interviews=interviews,
        user_sessions=user_sessions
    )


@interview_bp.route('/<identifier>')
@login_required
def interview_by_slug(identifier):
    """Access an interview by slug or ID."""
    interview = get_interview_by_identifier(identifier)
    if not interview:
        flash('Entretien introuvable', 'error')
        return redirect(url_for('interview.interview_list'))
    return redirect(url_for('interview.start', interview_id=interview.id))


@interview_bp.route('/<int:interview_id>/start', methods=['GET', 'POST'])
@login_required
def start(interview_id):
    """Start or resume an interview session."""
    interview = Interview.query.get_or_404(interview_id)

    # Check availability
    if not interview.is_open():
        flash('Cet entretien n\'est pas disponible actuellement', 'error')
        return redirect(url_for('interview.interview_list'))

    # Check group access
    if not interview.is_available_for_user(current_user):
        flash('Vous n\'avez pas acces a cet entretien', 'error')
        return redirect(url_for('interview.interview_list'))

    # Check for existing session
    existing_session = InterviewSession.query.filter_by(
        interview_id=interview_id,
        user_id=current_user.id
    ).first()

    if existing_session:
        if existing_session.status == InterviewSession.STATUS_IN_PROGRESS:
            # Resume existing session
            return redirect(url_for('interview.chat', session_id=existing_session.id))
        elif existing_session.status == InterviewSession.STATUS_COMPLETED:
            # Already completed
            flash('Vous avez deja complete cet entretien', 'info')
            return redirect(url_for('interview.result', session_id=existing_session.id))
        elif existing_session.status == InterviewSession.STATUS_EVALUATING:
            # Still evaluating
            return redirect(url_for('interview.evaluating', session_id=existing_session.id))

    # Check tenant quota for new sessions
    if interview.tenant_id:
        from app.models import Tenant
        tenant = Tenant.query.get(interview.tenant_id)
        if tenant and not tenant.can_use_interview():
            flash('Quota d\'entretiens IA atteint pour ce mois. Contactez votre administrateur.', 'error')
            return redirect(url_for('interview.interview_list'))

    # If file upload is required, show start page first
    if interview.require_file_upload:
        if request.method == 'POST':
            # Handle file upload
            uploaded_file = request.files.get('file')
            if not uploaded_file or uploaded_file.filename == '':
                flash('Veuillez telecharger un fichier', 'error')
                return render_template('interview/start.html', interview=interview)

            # Extract file content
            try:
                file_content = extract_file_content(uploaded_file)
                if not file_content:
                    flash('Impossible de lire le contenu du fichier', 'error')
                    return render_template('interview/start.html', interview=interview)
            except Exception as e:
                current_app.logger.error(f"File extraction error: {str(e)}")
                flash('Erreur lors de la lecture du fichier', 'error')
                return render_template('interview/start.html', interview=interview)

            # Create session with file
            session = create_interview_session(
                interview=interview,
                user=current_user,
                file_name=uploaded_file.filename,
                file_content=file_content
            )
            return redirect(url_for('interview.chat', session_id=session.id))

        # GET - show start page
        return render_template('interview/start.html', interview=interview)

    # No file required - create session directly
    session = create_interview_session(interview=interview, user=current_user)
    return redirect(url_for('interview.chat', session_id=session.id))


def extract_file_content(uploaded_file):
    """Extract text content from uploaded file."""
    import os

    filename = uploaded_file.filename.lower()
    content = None

    if filename.endswith('.txt'):
        content = uploaded_file.read().decode('utf-8', errors='ignore')
    elif filename.endswith('.pdf'):
        try:
            from pypdf import PdfReader
            from io import BytesIO
            pdf_reader = PdfReader(BytesIO(uploaded_file.read()))
            content = '\n'.join(page.extract_text() for page in pdf_reader.pages if page.extract_text())
        except ImportError:
            # pypdf not installed
            content = "[Contenu PDF - extraction non disponible]"
        except Exception as e:
            current_app.logger.error(f"PDF extraction error: {e}")
            content = None
    elif filename.endswith(('.doc', '.docx')):
        try:
            import docx
            from io import BytesIO
            doc = docx.Document(BytesIO(uploaded_file.read()))
            content = '\n'.join(para.text for para in doc.paragraphs if para.text)
        except ImportError:
            content = "[Contenu Word - extraction non disponible]"
        except Exception:
            content = None
    else:
        # Try reading as text
        try:
            content = uploaded_file.read().decode('utf-8', errors='ignore')
        except Exception:
            content = None

    return content


def create_interview_session(interview, user, file_name=None, file_content=None, is_test=False):
    """Create a new interview session with optional file."""
    session = InterviewSession(
        interview_id=interview.id,
        user_id=user.id,
        status=InterviewSession.STATUS_IN_PROGRESS,
        max_score=interview.get_max_score(),
        uploaded_file_name=file_name,
        uploaded_file_content=file_content,
        is_test=is_test
    )
    db.session.add(session)
    db.session.flush()

    # Add opening message if configured AND bot starts first
    if not interview.student_starts and interview.opening_message:
        opening_msg = InterviewMessage(
            session_id=session.id,
            role=InterviewMessage.ROLE_ASSISTANT,
            content=interview.opening_message,
            token_count=len(interview.opening_message) // 4
        )
        db.session.add(opening_msg)

    db.session.commit()

    # Increment tenant interview quota (only for non-test sessions)
    if not is_test and interview.tenant_id:
        from app.models import Tenant
        tenant = Tenant.query.get(interview.tenant_id)
        if tenant:
            tenant.increment_interviews()

    return session


@interview_bp.route('/session/<int:session_id>/chat')
@login_required
def chat(session_id):
    """Chat interface for an interview session."""
    session = InterviewSession.query.get_or_404(session_id)

    # Verify ownership
    if session.user_id != current_user.id and not current_user.is_any_admin:
        flash('Acces non autorise', 'error')
        return redirect(url_for('interview.interview_list'))

    # Check session status
    if session.status == InterviewSession.STATUS_COMPLETED:
        return redirect(url_for('interview.result', session_id=session_id))
    elif session.status == InterviewSession.STATUS_EVALUATING:
        return redirect(url_for('interview.evaluating', session_id=session_id))

    interview = session.interview

    return render_template(
        'interview/chat.html',
        session=session,
        interview=interview,
        messages=session.messages
    )


@interview_bp.route('/session/<int:session_id>/end', methods=['POST'])
@login_required
def end_interview(session_id):
    """End an interview session manually."""
    session = InterviewSession.query.get_or_404(session_id)

    if session.user_id != current_user.id:
        return jsonify({'error': 'Acces non autorise'}), 403

    if session.status != InterviewSession.STATUS_IN_PROGRESS:
        return jsonify({'error': 'Session deja terminee'}), 400

    # Update session status
    session.status = InterviewSession.STATUS_ENDED_BY_STUDENT
    session.end_reason = 'student'
    session.ended_at = datetime.utcnow()
    db.session.commit()

    # Trigger evaluation in background
    from app import socketio
    from app.utils.interview_tasks import evaluate_interview_async
    socketio.start_background_task(
        evaluate_interview_async,
        current_app._get_current_object(),
        session.id
    )

    return jsonify({'success': True, 'redirect': url_for('interview.evaluating', session_id=session_id)})


@interview_bp.route('/session/<int:session_id>/evaluating')
@login_required
def evaluating(session_id):
    """Show evaluation progress page."""
    session = InterviewSession.query.get_or_404(session_id)

    if session.user_id != current_user.id and not current_user.is_any_admin:
        flash('Acces non autorise', 'error')
        return redirect(url_for('interview.interview_list'))

    if session.status == InterviewSession.STATUS_COMPLETED:
        return redirect(url_for('interview.result', session_id=session_id))

    return render_template(
        'interview/evaluating.html',
        session=session
    )


@interview_bp.route('/session/<int:session_id>/result')
@login_required
def result(session_id):
    """Show interview results."""
    session = InterviewSession.query.get_or_404(session_id)

    if session.user_id != current_user.id and not current_user.is_any_admin:
        flash('Acces non autorise', 'error')
        return redirect(url_for('interview.interview_list'))

    # Make sure session is complete
    if session.status not in [InterviewSession.STATUS_COMPLETED, InterviewSession.STATUS_ERROR]:
        return redirect(url_for('interview.chat', session_id=session_id))

    return render_template(
        'interview/result.html',
        session=session,
        interview=session.interview
    )


@interview_bp.route('/session/<int:session_id>/pdf')
@login_required
def result_pdf(session_id):
    """Export interview results as PDF for student."""
    session = InterviewSession.query.get_or_404(session_id)

    # Check access
    if session.user_id != current_user.id and not current_user.is_any_admin:
        flash('Acces non autorise', 'error')
        return redirect(url_for('interview.interview_list'))

    # Make sure session is complete
    if session.status != InterviewSession.STATUS_COMPLETED:
        flash('Entretien non termine', 'error')
        return redirect(url_for('interview.result', session_id=session_id))

    interview = session.interview

    # Generate PDF using reportlab
    try:
        from app.utils.pdf_generator import generate_interview_pdf
        from flask import Response

        pdf_data = generate_interview_pdf(session, interview)
        filename = f"entretien_{interview.title[:30]}_{session.started_at.strftime('%Y%m%d')}.pdf"

        return Response(
            pdf_data,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )

    except Exception as e:
        current_app.logger.error(f"PDF generation error: {e}")
        flash('Erreur lors de la generation du PDF', 'error')
        return redirect(url_for('interview.result', session_id=session_id))


# ============================================================================
# Admin Routes
# ============================================================================

@interview_bp.route('/admin/interviews')
@login_required
@admin_required
def admin_list():
    """Admin list of all interviews."""
    # Pagination and filters
    page = request.args.get('page', 1, type=int)
    per_page = 20
    filter_group_id = request.args.get('group', 0, type=int)
    search = request.args.get('search', '').strip()

    # Build query based on admin level
    if current_user.is_admin:  # Superadmin
        query = Interview.query
    else:
        # Get accessible group IDs
        admin_groups = current_user.get_admin_groups()
        admin_group_ids = [g.id for g in admin_groups]

        # Interviews created by user OR assigned to their groups
        query = Interview.query.filter(
            db.or_(
                Interview.created_by_id == current_user.id,
                Interview.groups.any(Group.id.in_(admin_group_ids))
            )
        )

    # Apply tenant context filter
    tenant_context = get_tenant_context()
    if tenant_context:
        query = query.filter(Interview.tenant_id == tenant_context.id)

    # Apply group filter
    if filter_group_id:
        query = query.filter(Interview.groups.any(Group.id == filter_group_id))

    # Apply search filter
    if search:
        search_pattern = f'%{search}%'
        query = query.filter(
            db.or_(
                Interview.title.ilike(search_pattern),
                Interview.description.ilike(search_pattern),
                Interview.persona_name.ilike(search_pattern),
                Interview.persona_role.ilike(search_pattern)
            )
        )

    interviews = query.order_by(Interview.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )

    # Get all accessible groups for filter dropdown
    all_groups = get_admin_groups()

    return render_template(
        'admin/interviews/list.html',
        interviews=interviews,
        all_groups=all_groups,
        filter_group_id=filter_group_id,
        search=search
    )


@interview_bp.route('/admin/interviews/create', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_create():
    """Create new interview with wizard."""
    if request.method == 'POST':
        # Get form data
        data = request.form

        # Validate required fields
        title = data.get('title', '').strip()
        system_prompt = data.get('system_prompt', '').strip()

        if not title:
            flash('Le titre est requis', 'error')
            return redirect(url_for('interview.admin_create'))

        if not system_prompt:
            flash('Le prompt systeme est requis', 'error')
            return redirect(url_for('interview.admin_create'))

        # Parse slug
        slug = data.get('slug', '').strip() or None
        if slug:
            slug = re.sub(r'[^a-z0-9-]', '', slug.lower())
            # Check uniqueness
            if Interview.query.filter_by(slug=slug).first():
                flash('Ce slug est deja utilise', 'error')
                return redirect(url_for('interview.admin_create'))

        # Parse dates
        available_from = None
        available_until = None
        try:
            if data.get('available_from'):
                available_from = datetime.fromisoformat(data['available_from'])
            if data.get('available_until'):
                available_until = datetime.fromisoformat(data['available_until'])
        except ValueError:
            pass

        # Create interview
        interview = Interview(
            title=title,
            description=data.get('description', '').strip(),
            slug=slug,
            system_prompt=system_prompt,
            persona_name=data.get('persona_name', '').strip(),
            persona_role=data.get('persona_role', '').strip(),
            persona_context=data.get('persona_context', '').strip(),
            persona_personality=data.get('persona_personality', '').strip(),
            persona_knowledge=data.get('persona_knowledge', '').strip(),
            persona_objectives=data.get('persona_objectives', '').strip(),
            persona_triggers=data.get('persona_triggers', '').strip(),
            student_context=data.get('student_context', '').strip(),
            student_objective=data.get('student_objective', '').strip(),
            opening_message=data.get('opening_message', '').strip(),
            max_interactions=int(data.get('max_interactions', 30)),
            max_duration_minutes=int(data.get('max_duration_minutes', 30)),
            allow_student_end=data.get('allow_student_end') == 'on',
            ai_can_end=data.get('ai_can_end') == 'on',
            student_starts=data.get('student_starts') == '1',
            require_file_upload=data.get('require_file_upload') == 'on',
            file_upload_label=data.get('file_upload_label', 'Fichier').strip(),
            file_upload_description=data.get('file_upload_description', '').strip(),
            file_upload_prompt_injection=data.get('file_upload_prompt_injection', '').strip(),
            available_from=available_from,
            available_until=available_until,
            created_by_id=current_user.id,
            tenant_id=data.get('tenant_id') or None
        )
        db.session.add(interview)
        db.session.flush()

        # Add groups
        group_ids = request.form.getlist('group_ids')
        for group_id in group_ids:
            try:
                group = Group.query.get(int(group_id))
                if group:
                    interview.groups.append(group)
            except ValueError:
                pass

        # Add criteria
        criteria_json = data.get('criteria_json', '[]')
        try:
            criteria_list = json.loads(criteria_json)
            for i, c in enumerate(criteria_list):
                criterion = EvaluationCriterion(
                    interview_id=interview.id,
                    name=c.get('name', ''),
                    description=c.get('description', ''),
                    max_points=float(c.get('max_points', 5)),
                    order=i,
                    evaluation_hints=c.get('hints', '')
                )
                db.session.add(criterion)
        except json.JSONDecodeError:
            pass

        db.session.commit()
        flash('Entretien cree avec succes', 'success')
        return redirect(url_for('interview.admin_list'))

    # GET request - show wizard
    groups_by_tenant = get_groups_by_tenant()
    criteria_templates = get_criteria_templates()

    return render_template(
        'admin/interviews/wizard.html',
        groups_by_tenant=groups_by_tenant,
        criteria_templates=criteria_templates
    )


@interview_bp.route('/admin/interviews/<int:interview_id>')
@login_required
@admin_required
def admin_view(interview_id):
    """View interview details and sessions."""
    interview = Interview.query.get_or_404(interview_id)

    # Get sessions statistics
    sessions = interview.sessions.all()
    completed_sessions = [s for s in sessions if s.status == InterviewSession.STATUS_COMPLETED]

    stats = {
        'total': len(sessions),
        'completed': len(completed_sessions),
        'in_progress': len([s for s in sessions if s.status == InterviewSession.STATUS_IN_PROGRESS]),
        'avg_score': 0,
        'avg_duration': 0
    }

    if completed_sessions:
        stats['avg_score'] = sum(s.get_score_percentage() for s in completed_sessions) / len(completed_sessions)
        stats['avg_duration'] = sum(s.get_duration_minutes() for s in completed_sessions) / len(completed_sessions)

    return render_template(
        'admin/interviews/view.html',
        interview=interview,
        sessions=sessions,
        stats=stats
    )


@interview_bp.route('/admin/interviews/<int:interview_id>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit(interview_id):
    """Edit an interview."""
    interview = Interview.query.get_or_404(interview_id)

    # Check if there are completed sessions (non-test) - criteria cannot be edited
    has_results = InterviewSession.query.filter(
        InterviewSession.interview_id == interview_id,
        InterviewSession.is_test.is_(False),
        InterviewSession.status == InterviewSession.STATUS_COMPLETED
    ).first() is not None

    if request.method == 'POST':
        data = request.form

        # Update fields
        interview.title = data.get('title', '').strip()
        interview.description = data.get('description', '').strip()
        interview.system_prompt = data.get('system_prompt', '').strip()
        interview.persona_name = data.get('persona_name', '').strip()
        interview.persona_role = data.get('persona_role', '').strip()
        interview.persona_context = data.get('persona_context', '').strip()
        interview.persona_personality = data.get('persona_personality', '').strip()
        interview.persona_knowledge = data.get('persona_knowledge', '').strip()
        interview.persona_objectives = data.get('persona_objectives', '').strip()
        interview.persona_triggers = data.get('persona_triggers', '').strip()
        interview.student_context = data.get('student_context', '').strip()
        interview.student_objective = data.get('student_objective', '').strip()
        interview.opening_message = data.get('opening_message', '').strip()
        interview.max_interactions = int(data.get('max_interactions', 30))
        interview.max_duration_minutes = int(data.get('max_duration_minutes', 30))
        interview.allow_student_end = data.get('allow_student_end') == 'on'
        interview.ai_can_end = data.get('ai_can_end') == 'on'
        interview.is_active = data.get('is_active') == 'on'
        interview.student_starts = data.get('student_starts') == '1'
        interview.require_file_upload = data.get('require_file_upload') == 'on'
        interview.file_upload_label = data.get('file_upload_label', 'Fichier').strip()
        interview.file_upload_description = data.get('file_upload_description', '').strip()
        interview.file_upload_prompt_injection = data.get('file_upload_prompt_injection', '').strip()

        # Handle slug
        new_slug = data.get('slug', '').strip() or None
        if new_slug:
            new_slug = re.sub(r'[^a-z0-9-]', '', new_slug.lower())
            existing = Interview.query.filter_by(slug=new_slug).first()
            if existing and existing.id != interview.id:
                flash('Ce slug est deja utilise', 'error')
                return redirect(url_for('interview.admin_edit', interview_id=interview_id))
        interview.slug = new_slug

        # Update dates
        try:
            interview.available_from = datetime.fromisoformat(data['available_from']) if data.get('available_from') else None
            interview.available_until = datetime.fromisoformat(data['available_until']) if data.get('available_until') else None
        except ValueError:
            pass

        # Update groups
        interview.groups = []
        for group_id in request.form.getlist('group_ids'):
            try:
                group = Group.query.get(int(group_id))
                if group:
                    interview.groups.append(group)
            except ValueError:
                pass

        # Update criteria only if no completed sessions exist
        if not has_results:
            # Remove old criteria
            for criterion in list(interview.criteria):
                db.session.delete(criterion)
            db.session.flush()

            # Add new criteria
            criteria_json = data.get('criteria_json', '[]')
            try:
                criteria_list = json.loads(criteria_json)
                for i, c in enumerate(criteria_list):
                    criterion = EvaluationCriterion(
                        interview_id=interview.id,
                        name=c.get('name', ''),
                        description=c.get('description', ''),
                        max_points=float(c.get('max_points', 5)),
                        order=i,
                        evaluation_hints=c.get('hints', '')
                    )
                    db.session.add(criterion)
            except json.JSONDecodeError:
                pass

        db.session.commit()
        flash('Entretien mis a jour', 'success')
        return redirect(url_for('interview.admin_view', interview_id=interview_id))

    # GET request
    groups_by_tenant = get_groups_by_tenant()
    criteria_templates = get_criteria_templates()

    # Prepare current criteria as JSON
    current_criteria = [
        {
            'name': c.name,
            'description': c.description or '',
            'max_points': c.max_points,
            'hints': c.evaluation_hints or ''
        }
        for c in interview.criteria
    ]

    return render_template(
        'admin/interviews/wizard.html',
        interview=interview,
        groups_by_tenant=groups_by_tenant,
        criteria_templates=criteria_templates,
        current_criteria=json.dumps(current_criteria),
        edit_mode=True,
        has_results=has_results
    )


@interview_bp.route('/admin/interviews/<int:interview_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete(interview_id):
    """Delete an interview."""
    interview = Interview.query.get_or_404(interview_id)
    db.session.delete(interview)
    db.session.commit()
    flash('Entretien supprime', 'success')
    return redirect(url_for('interview.admin_list'))


@interview_bp.route('/admin/interviews/<int:interview_id>/session/<int:session_id>')
@login_required
@admin_required
def admin_session(interview_id, session_id):
    """View a specific session transcript."""
    session = InterviewSession.query.get_or_404(session_id)

    if session.interview_id != interview_id:
        flash('Session non trouvee', 'error')
        return redirect(url_for('interview.admin_view', interview_id=interview_id))

    return render_template(
        'admin/interviews/session.html',
        session=session,
        interview=session.interview
    )


@interview_bp.route('/admin/interviews/<int:interview_id>/session/<int:session_id>/comment', methods=['POST'])
@login_required
@admin_required
def admin_add_comment(interview_id, session_id):
    """Add admin comment to a session."""
    session = InterviewSession.query.get_or_404(session_id)

    if session.interview_id != interview_id:
        return jsonify({'error': 'Session non trouvee'}), 404

    comment = request.form.get('comment', '').strip()
    session.admin_comment = comment
    db.session.commit()

    flash('Commentaire enregistre', 'success')
    return redirect(url_for('interview.admin_session', interview_id=interview_id, session_id=session_id))


@interview_bp.route('/admin/interviews/<int:interview_id>/session/<int:session_id>/pdf')
@login_required
@admin_required
def admin_session_pdf(interview_id, session_id):
    """Export session results as PDF."""
    session = InterviewSession.query.get_or_404(session_id)

    if session.interview_id != interview_id:
        flash('Session non trouvee', 'error')
        return redirect(url_for('interview.admin_view', interview_id=interview_id))

    interview = session.interview

    # Generate PDF using reportlab
    try:
        from app.utils.pdf_generator import generate_interview_pdf
        from flask import Response

        pdf_data = generate_interview_pdf(session, interview)
        filename = f"entretien_{session.user.username}_{session.started_at.strftime('%Y%m%d')}.pdf"

        return Response(
            pdf_data,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )

    except Exception as e:
        current_app.logger.error(f"PDF generation error: {e}")
        flash('Erreur lors de la generation du PDF', 'error')
        return redirect(url_for('interview.admin_session', interview_id=interview_id, session_id=session_id))


@interview_bp.route('/admin/interviews/<int:interview_id>/test', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_test(interview_id):
    """Start a test session for admin preview."""
    interview = Interview.query.get_or_404(interview_id)

    # Delete any existing test session for this admin
    existing_test = InterviewSession.query.filter_by(
        interview_id=interview_id,
        user_id=current_user.id,
        is_test=True
    ).first()
    if existing_test:
        db.session.delete(existing_test)
        db.session.commit()

    # If file upload is required, show start page first
    if interview.require_file_upload:
        if request.method == 'POST':
            # Handle file upload
            uploaded_file = request.files.get('file')
            if not uploaded_file or uploaded_file.filename == '':
                flash('Veuillez telecharger un fichier', 'error')
                return render_template('interview/start.html', interview=interview, is_test=True)

            # Extract file content
            try:
                file_content = extract_file_content(uploaded_file)
                if not file_content:
                    flash('Impossible de lire le contenu du fichier', 'error')
                    return render_template('interview/start.html', interview=interview, is_test=True)
            except Exception as e:
                current_app.logger.error(f"File extraction error: {str(e)}")
                flash('Erreur lors de la lecture du fichier', 'error')
                return render_template('interview/start.html', interview=interview, is_test=True)

            # Create test session with file
            session = create_interview_session(
                interview=interview,
                user=current_user,
                file_name=uploaded_file.filename,
                file_content=file_content,
                is_test=True
            )
            flash('Session de test demarree', 'info')
            return redirect(url_for('interview.chat', session_id=session.id))

        # GET - show start page for file upload
        return render_template('interview/start.html', interview=interview, is_test=True)

    # No file required - create test session directly
    session = create_interview_session(interview=interview, user=current_user, is_test=True)
    flash('Session de test demarree', 'info')
    return redirect(url_for('interview.chat', session_id=session.id))


@interview_bp.route('/admin/interviews/<int:interview_id>/toggle', methods=['POST'])
@login_required
@admin_required
def admin_toggle(interview_id):
    """Toggle interview active status."""
    interview = Interview.query.get_or_404(interview_id)
    interview.is_active = not interview.is_active
    db.session.commit()
    flash(f'Entretien {"active" if interview.is_active else "desactive"}', 'success')
    return redirect(url_for('interview.admin_list'))


@interview_bp.route('/admin/interviews/<int:interview_id>/session/<int:session_id>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_session(interview_id, session_id):
    """Delete a session."""
    session = InterviewSession.query.get_or_404(session_id)

    if session.interview_id != interview_id:
        flash('Session non trouvee', 'error')
        return redirect(url_for('interview.admin_view', interview_id=interview_id))

    db.session.delete(session)
    db.session.commit()
    flash('Session supprimee', 'success')
    return redirect(url_for('interview.admin_view', interview_id=interview_id))


@interview_bp.route('/admin/interviews/<int:interview_id>/export')
@login_required
@admin_required
def admin_export(interview_id):
    """Export interview results as CSV."""
    from flask import Response
    import csv
    from io import StringIO

    interview = Interview.query.get_or_404(interview_id)
    sessions = interview.sessions.filter(InterviewSession.is_test == False).all()

    output = StringIO()
    writer = csv.writer(output, delimiter=';')

    # Header
    header = ['Etudiant', 'Username', 'Date', 'Duree (min)', 'Echanges', 'Score', 'Score Max', 'Pourcentage', 'Statut']
    # Add criteria columns
    for criterion in interview.criteria:
        header.append(f'{criterion.name} (/{criterion.max_points})')
    writer.writerow(header)

    # Data rows
    for session in sessions:
        row = [
            session.user.full_name,
            session.user.username,
            session.started_at.strftime('%d/%m/%Y %H:%M'),
            session.get_duration_minutes(),
            session.interaction_count,
            f'{session.total_score:.1f}',
            f'{session.max_score:.1f}',
            f'{session.get_score_percentage():.0f}%',
            session.status
        ]
        # Add criterion scores
        scores_dict = {s.criterion_id: s for s in session.scores}
        for criterion in interview.criteria:
            score = scores_dict.get(criterion.id)
            row.append(f'{score.score:.1f}' if score else '-')
        writer.writerow(row)

    output.seek(0)
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=entretien_{interview.id}_resultats.csv'}
    )


# ============================================================================
# AJAX Endpoints
# ============================================================================

@interview_bp.route('/admin/interviews/generate-prompt', methods=['POST'])
@login_required
@admin_required
def generate_prompt():
    """Generate system prompt from wizard data."""
    try:
        data = request.get_json()
        interviewer = ClaudeInterviewer()
        system_prompt = interviewer.generate_system_prompt(data)
        return jsonify({'success': True, 'system_prompt': system_prompt})
    except Exception as e:
        current_app.logger.error(f"Prompt generation error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@interview_bp.route('/admin/interviews/generate-opening', methods=['POST'])
@login_required
@admin_required
def generate_opening():
    """Generate opening message from system prompt."""
    try:
        data = request.get_json()
        system_prompt = data.get('system_prompt', '')

        if not system_prompt:
            return jsonify({'success': False, 'error': 'System prompt requis'}), 400

        interviewer = ClaudeInterviewer()
        opening = interviewer.generate_opening_message(system_prompt)
        return jsonify({'success': True, 'opening_message': opening})
    except Exception as e:
        current_app.logger.error(f"Opening generation error: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@interview_bp.route('/admin/interviews/criteria-templates')
@login_required
@admin_required
def get_templates():
    """Get criteria templates."""
    templates = get_criteria_templates()
    return jsonify(templates)
