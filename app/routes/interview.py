"""
Interview routes - Admin and student routes for conversational AI interviews.
"""

from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify, current_app
from flask_login import login_required, current_user
from flask_babel import lazy_gettext as _l
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
import unicodedata

interview_bp = Blueprint('interview', __name__)


def sanitize_filename(text):
    """Sanitize text for use in HTTP Content-Disposition filename header.

    Removes or replaces non-ASCII characters to avoid encoding issues.
    """
    # Normalize unicode (decompose accented characters)
    text = unicodedata.normalize('NFKD', text)
    # Encode to ASCII, ignoring non-encodable characters
    text = text.encode('ascii', 'ignore').decode('ascii')
    # Replace common problematic characters
    text = text.replace('/', '-').replace('\\', '-').replace('"', '')
    # Remove any remaining non-safe characters
    text = re.sub(r'[^\w\s\-\.]', '', text)
    # Replace multiple spaces/dashes with single
    text = re.sub(r'[\s\-]+', '_', text)
    return text.strip('_')


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



def admin_required(f):
    """Decorator to require admin access."""
    from functools import wraps
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            return redirect(url_for('auth.login'))
        if not current_user.is_any_admin:
            flash(_l('Acces non autorise'), 'error')
            return redirect(url_for('quiz.dashboard'))
        return f(*args, **kwargs)
    return decorated_function


def get_admin_groups():
    """Get groups accessible to current admin."""
    if current_user.is_admin:  # Superadmin
        return Group.query.order_by(Group.name).all()
    # Tenant/Group admin - get their accessible groups
    return current_user.get_accessible_groups()


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
    """Access an interview by uid, slug, or ID."""
    interview = Interview.get_by_identifier(identifier)
    if not interview:
        flash(_l('Entretien introuvable'), 'error')
        return redirect(url_for('interview.interview_list'))
    return redirect(url_for('interview.start', identifier=interview.get_url_identifier()))


@interview_bp.route('/<identifier>/start', methods=['GET', 'POST'])
@login_required
def start(identifier):
    """Start or resume an interview session."""
    interview = Interview.get_by_identifier(identifier)
    if not interview:
        flash(_l('Entretien introuvable'), 'error')
        return redirect(url_for('interview.interview_list'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != interview.get_url_identifier():
        return redirect(url_for('interview.start', identifier=interview.get_url_identifier()), code=301)

    interview_id = interview.id  # Keep for queries

    # Check availability
    if not interview.is_open():
        flash(_l("Cet entretien n'est pas disponible actuellement"), 'error')
        return redirect(url_for('interview.interview_list'))

    # Check group access
    if not interview.is_available_for_user(current_user):
        flash(_l("Vous n'avez pas acces a cet entretien"), 'error')
        return redirect(url_for('interview.interview_list'))

    # Check for existing session
    existing_session = InterviewSession.query.filter_by(
        interview_id=interview_id,
        user_id=current_user.id
    ).first()

    if existing_session:
        if existing_session.status == InterviewSession.STATUS_IN_PROGRESS:
            # Resume existing session
            return redirect(url_for('interview.chat', identifier=existing_session.get_url_identifier()))
        elif existing_session.status == InterviewSession.STATUS_COMPLETED:
            # Already completed
            flash(_l('Vous avez deja complete cet entretien'), 'info')
            return redirect(url_for('interview.result', identifier=existing_session.get_url_identifier()))
        elif existing_session.status == InterviewSession.STATUS_EVALUATING:
            # Still evaluating
            return redirect(url_for('interview.evaluating', identifier=existing_session.get_url_identifier()))

    # Check tenant quota for new sessions
    if interview.tenant_id:
        from app.models import Tenant
        tenant = Tenant.query.get(interview.tenant_id)
        if tenant and not tenant.can_use_interview():
            flash(_l("Quota d'entretiens IA atteint pour ce mois. Contactez votre administrateur."), 'error')
            return redirect(url_for('interview.interview_list'))

    # If file upload is required, show start page first
    if interview.require_file_upload:
        if request.method == 'POST':
            # Handle file upload
            uploaded_file = request.files.get('file')
            if not uploaded_file or uploaded_file.filename == '':
                flash(_l('Veuillez telecharger un fichier'), 'error')
                return render_template('interview/start.html', interview=interview)

            # Extract file content
            try:
                file_content = extract_file_content(uploaded_file)
                if not file_content:
                    flash(_l('Impossible de lire le contenu du fichier'), 'error')
                    return render_template('interview/start.html', interview=interview)
            except Exception as e:
                current_app.logger.error(f"File extraction error: {str(e)}")
                flash(_l('Erreur lors de la lecture du fichier'), 'error')
                return render_template('interview/start.html', interview=interview)

            # Create session with file
            session = create_interview_session(
                interview=interview,
                user=current_user,
                file_name=uploaded_file.filename,
                file_content=file_content
            )
            return redirect(url_for('interview.chat', identifier=session.get_url_identifier()))

        # GET - show start page
        return render_template('interview/start.html', interview=interview)

    # No file required - create session directly
    session = create_interview_session(interview=interview, user=current_user)
    return redirect(url_for('interview.chat', identifier=session.get_url_identifier()))


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


@interview_bp.route('/session/<identifier>/chat')
@login_required
def chat(identifier):
    """Chat interface for an interview session."""
    session = InterviewSession.get_by_identifier(identifier)
    if not session:
        flash(_l('Session introuvable'), 'error')
        return redirect(url_for('interview.interview_list'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != session.get_url_identifier():
        return redirect(url_for('interview.chat', identifier=session.get_url_identifier()), code=301)

    # Verify ownership
    if session.user_id != current_user.id and not current_user.is_any_admin:
        flash(_l('Acces non autorise'), 'error')
        return redirect(url_for('interview.interview_list'))

    # Check session status
    if session.status == InterviewSession.STATUS_COMPLETED:
        return redirect(url_for('interview.result', identifier=session.get_url_identifier()))
    elif session.status == InterviewSession.STATUS_EVALUATING:
        return redirect(url_for('interview.evaluating', identifier=session.get_url_identifier()))

    interview = session.interview

    return render_template(
        'interview/chat.html',
        session=session,
        interview=interview,
        messages=session.messages
    )


@interview_bp.route('/session/<identifier>/end', methods=['POST'])
@login_required
def end_interview(identifier):
    """End an interview session manually."""
    session = InterviewSession.get_by_identifier(identifier)
    if not session:
        return jsonify({'error': 'Session introuvable'}), 404

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

    return jsonify({'success': True, 'redirect': url_for('interview.evaluating', identifier=session.get_url_identifier())})


@interview_bp.route('/session/<identifier>/evaluating')
@login_required
def evaluating(identifier):
    """Show evaluation progress page."""
    session = InterviewSession.get_by_identifier(identifier)
    if not session:
        flash(_l('Session introuvable'), 'error')
        return redirect(url_for('interview.interview_list'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != session.get_url_identifier():
        return redirect(url_for('interview.evaluating', identifier=session.get_url_identifier()), code=301)

    if session.user_id != current_user.id and not current_user.is_any_admin:
        flash(_l('Acces non autorise'), 'error')
        return redirect(url_for('interview.interview_list'))

    if session.status == InterviewSession.STATUS_COMPLETED:
        return redirect(url_for('interview.result', identifier=session.get_url_identifier()))

    return render_template(
        'interview/evaluating.html',
        session=session
    )


@interview_bp.route('/session/<identifier>/result')
@login_required
def result(identifier):
    """Show interview results."""
    session = InterviewSession.get_by_identifier(identifier)
    if not session:
        flash(_l('Session introuvable'), 'error')
        return redirect(url_for('interview.interview_list'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != session.get_url_identifier():
        return redirect(url_for('interview.result', identifier=session.get_url_identifier()), code=301)

    if session.user_id != current_user.id and not current_user.is_any_admin:
        flash(_l('Acces non autorise'), 'error')
        return redirect(url_for('interview.interview_list'))

    # Make sure session is complete
    if session.status not in [InterviewSession.STATUS_COMPLETED, InterviewSession.STATUS_ERROR]:
        return redirect(url_for('interview.chat', identifier=session.get_url_identifier()))

    return render_template(
        'interview/result.html',
        session=session,
        interview=session.interview
    )


@interview_bp.route('/session/<identifier>/pdf')
@login_required
def result_pdf(identifier):
    """Export interview results as PDF for student."""
    session = InterviewSession.get_by_identifier(identifier)
    if not session:
        flash(_l('Session introuvable'), 'error')
        return redirect(url_for('interview.interview_list'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != session.get_url_identifier():
        return redirect(url_for('interview.result_pdf', identifier=session.get_url_identifier()), code=301)

    # Check access
    if session.user_id != current_user.id and not current_user.is_any_admin:
        flash(_l('Acces non autorise'), 'error')
        return redirect(url_for('interview.interview_list'))

    # Make sure session is complete
    if session.status != InterviewSession.STATUS_COMPLETED:
        flash(_l('Entretien non termine'), 'error')
        return redirect(url_for('interview.result', identifier=session.get_url_identifier()))

    interview = session.interview

    # Generate PDF using reportlab
    try:
        from app.utils.pdf_generator import generate_interview_pdf
        from flask import Response

        pdf_data = generate_interview_pdf(session, interview)
        safe_title = sanitize_filename(interview.title[:30])
        filename = f"entretien_{safe_title}_{session.started_at.strftime('%Y%m%d')}.pdf"

        return Response(
            pdf_data,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )

    except Exception as e:
        current_app.logger.error(f"PDF generation error: {e}")
        flash(_l('Erreur lors de la generation du PDF'), 'error')
        return redirect(url_for('interview.result', identifier=session.get_url_identifier()))


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
        # Get accessible group IDs (includes tenant admin groups)
        admin_groups = current_user.get_accessible_groups()
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
            flash(_l('Le titre est requis'), 'error')
            return redirect(url_for('interview.admin_create'))

        if not system_prompt:
            flash(_l('Le prompt systeme est requis'), 'error')
            return redirect(url_for('interview.admin_create'))

        # Parse slug
        slug = data.get('slug', '').strip() or None
        if slug:
            slug = re.sub(r'[^a-z0-9-]', '', slug.lower())
            # Check uniqueness
            if Interview.query.filter_by(slug=slug).first():
                flash(_l('Ce slug est deja utilise'), 'error')
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
        flash(_l('Entretien cree avec succes'), 'success')
        return redirect(url_for('interview.admin_list'))

    # GET request - show wizard
    groups_by_tenant = get_groups_by_tenant()
    criteria_templates = get_criteria_templates()

    return render_template(
        'admin/interviews/wizard.html',
        groups_by_tenant=groups_by_tenant,
        criteria_templates=criteria_templates
    )


@interview_bp.route('/admin/interviews/<identifier>')
@login_required
@admin_required
def admin_view(identifier):
    """View interview details and sessions."""
    interview = Interview.get_by_identifier(identifier)
    if not interview:
        flash(_l('Entretien introuvable'), 'error')
        return redirect(url_for('interview.admin_list'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != interview.get_url_identifier():
        return redirect(url_for('interview.admin_view', identifier=interview.get_url_identifier()), code=301)

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


@interview_bp.route('/admin/interviews/<identifier>/edit', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_edit(identifier):
    """Edit an interview."""
    interview = Interview.get_by_identifier(identifier)
    if not interview:
        flash(_l('Entretien introuvable'), 'error')
        return redirect(url_for('interview.admin_list'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != interview.get_url_identifier():
        return redirect(url_for('interview.admin_edit', identifier=interview.get_url_identifier()), code=301)

    interview_id = interview.id  # Keep for queries

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
                flash(_l('Ce slug est deja utilise'), 'error')
                return redirect(url_for('interview.admin_edit', identifier=interview.get_url_identifier()))
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
        flash(_l('Entretien mis a jour'), 'success')
        return redirect(url_for('interview.admin_view', identifier=interview.get_url_identifier()))

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


@interview_bp.route('/admin/interviews/<identifier>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete(identifier):
    """Delete an interview."""
    interview = Interview.get_by_identifier(identifier)
    if not interview:
        flash(_l('Entretien introuvable'), 'error')
        return redirect(url_for('interview.admin_list'))
    db.session.delete(interview)
    db.session.commit()
    flash(_l('Entretien supprime'), 'success')
    return redirect(url_for('interview.admin_list'))


@interview_bp.route('/admin/interviews/<identifier>/session/<session_identifier>')
@login_required
@admin_required
def admin_session(identifier, session_identifier):
    """View a specific session transcript."""
    interview = Interview.get_by_identifier(identifier)
    if not interview:
        flash(_l('Entretien introuvable'), 'error')
        return redirect(url_for('interview.admin_list'))

    session = InterviewSession.get_by_identifier(session_identifier)
    if not session:
        flash(_l('Session non trouvee'), 'error')
        return redirect(url_for('interview.admin_view', identifier=interview.get_url_identifier()))

    if session.interview_id != interview.id:
        flash(_l('Session non trouvee'), 'error')
        return redirect(url_for('interview.admin_view', identifier=interview.get_url_identifier()))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != interview.get_url_identifier() or session_identifier != session.get_url_identifier():
        return redirect(url_for('interview.admin_session', identifier=interview.get_url_identifier(), session_identifier=session.get_url_identifier()), code=301)

    return render_template(
        'admin/interviews/session.html',
        session=session,
        interview=session.interview
    )


@interview_bp.route('/admin/interviews/<identifier>/session/<session_identifier>/comment', methods=['POST'])
@login_required
@admin_required
def admin_add_comment(identifier, session_identifier):
    """Add admin comment to a session."""
    interview = Interview.get_by_identifier(identifier)
    if not interview:
        return jsonify({'error': 'Entretien non trouve'}), 404

    session = InterviewSession.get_by_identifier(session_identifier)
    if not session:
        return jsonify({'error': 'Session non trouvee'}), 404

    if session.interview_id != interview.id:
        return jsonify({'error': 'Session non trouvee'}), 404

    comment = request.form.get('comment', '').strip()
    session.admin_comment = comment
    db.session.commit()

    flash(_l('Commentaire enregistre'), 'success')
    return redirect(url_for('interview.admin_session', identifier=interview.get_url_identifier(), session_identifier=session.get_url_identifier()))


@interview_bp.route('/admin/interviews/<identifier>/session/<session_identifier>/reevaluate', methods=['POST'])
@login_required
@admin_required
def admin_reevaluate_session(identifier, session_identifier):
    """Re-run evaluation for a session (in case of error or bug)."""
    interview = Interview.get_by_identifier(identifier)
    if not interview:
        flash(_l('Entretien introuvable'), 'error')
        return redirect(url_for('interview.admin_list'))

    session = InterviewSession.get_by_identifier(session_identifier)
    if not session:
        flash(_l('Session non trouvee'), 'error')
        return redirect(url_for('interview.admin_view', identifier=interview.get_url_identifier()))

    if session.interview_id != interview.id:
        flash(_l('Session non trouvee'), 'error')
        return redirect(url_for('interview.admin_view', identifier=interview.get_url_identifier()))

    # Delete existing scores
    CriterionScore.query.filter_by(session_id=session.id).delete()

    # Reset session evaluation fields
    session.status = InterviewSession.STATUS_EVALUATING
    session.total_score = 0
    session.ai_summary = None
    db.session.commit()

    # Run evaluation asynchronously
    from app.utils.interview_tasks import evaluate_interview_async
    from app import socketio
    socketio.start_background_task(
        evaluate_interview_async,
        current_app._get_current_object(),
        session.id
    )

    flash(_l('Re-evaluation lancee. Veuillez patienter quelques secondes puis rafraichir la page.'), 'info')
    return redirect(url_for('interview.admin_session', identifier=interview.get_url_identifier(), session_identifier=session.get_url_identifier()))


@interview_bp.route('/admin/interviews/<identifier>/session/<session_identifier>/pdf')
@login_required
@admin_required
def admin_session_pdf(identifier, session_identifier):
    """Export session results as PDF."""
    interview = Interview.get_by_identifier(identifier)
    if not interview:
        flash(_l('Entretien introuvable'), 'error')
        return redirect(url_for('interview.admin_list'))

    session = InterviewSession.get_by_identifier(session_identifier)
    if not session:
        flash(_l('Session non trouvee'), 'error')
        return redirect(url_for('interview.admin_view', identifier=interview.get_url_identifier()))

    if session.interview_id != interview.id:
        flash(_l('Session non trouvee'), 'error')
        return redirect(url_for('interview.admin_view', identifier=interview.get_url_identifier()))

    interview = session.interview

    # Generate PDF using reportlab
    try:
        from app.utils.pdf_generator import generate_interview_pdf
        from flask import Response

        pdf_data = generate_interview_pdf(session, interview)
        safe_username = sanitize_filename(session.user.username)
        filename = f"entretien_{safe_username}_{session.started_at.strftime('%Y%m%d')}.pdf"

        return Response(
            pdf_data,
            mimetype='application/pdf',
            headers={'Content-Disposition': f'attachment; filename="{filename}"'}
        )

    except Exception as e:
        current_app.logger.error(f"PDF generation error: {e}")
        flash(_l('Erreur lors de la generation du PDF'), 'error')
        return redirect(url_for('interview.admin_session', identifier=interview.get_url_identifier(), session_identifier=session.get_url_identifier()))


@interview_bp.route('/admin/interviews/<identifier>/test', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_test(identifier):
    """Start a test session for admin preview."""
    interview = Interview.get_by_identifier(identifier)
    if not interview:
        flash(_l('Entretien introuvable'), 'error')
        return redirect(url_for('interview.admin_list'))

    # Redirect to canonical URL if accessed by numeric ID
    if identifier != interview.get_url_identifier():
        return redirect(url_for('interview.admin_test', identifier=interview.get_url_identifier()), code=301)

    # Delete any existing test session for this admin
    existing_test = InterviewSession.query.filter_by(
        interview_id=interview.id,
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
                flash(_l('Veuillez telecharger un fichier'), 'error')
                return render_template('interview/start.html', interview=interview, is_test=True)

            # Extract file content
            try:
                file_content = extract_file_content(uploaded_file)
                if not file_content:
                    flash(_l('Impossible de lire le contenu du fichier'), 'error')
                    return render_template('interview/start.html', interview=interview, is_test=True)
            except Exception as e:
                current_app.logger.error(f"File extraction error: {str(e)}")
                flash(_l('Erreur lors de la lecture du fichier'), 'error')
                return render_template('interview/start.html', interview=interview, is_test=True)

            # Create test session with file
            session = create_interview_session(
                interview=interview,
                user=current_user,
                file_name=uploaded_file.filename,
                file_content=file_content,
                is_test=True
            )
            flash(_l('Session de test demarree'), 'info')
            return redirect(url_for('interview.chat', identifier=session.get_url_identifier()))

        # GET - show start page for file upload
        return render_template('interview/start.html', interview=interview, is_test=True)

    # No file required - create test session directly
    session = create_interview_session(interview=interview, user=current_user, is_test=True)
    flash(_l('Session de test demarree'), 'info')
    return redirect(url_for('interview.chat', identifier=session.get_url_identifier()))


@interview_bp.route('/admin/interviews/<identifier>/toggle', methods=['POST'])
@login_required
@admin_required
def admin_toggle(identifier):
    """Toggle interview active status."""
    interview = Interview.get_by_identifier(identifier)
    if not interview:
        flash(_l('Entretien introuvable'), 'error')
        return redirect(url_for('interview.admin_list'))
    interview.is_active = not interview.is_active
    db.session.commit()
    status = _l('active') if interview.is_active else _l('desactive')
    flash(_l('Entretien %(status)s', status=status), 'success')
    return redirect(url_for('interview.admin_list'))


@interview_bp.route('/admin/interviews/<identifier>/session/<session_identifier>/delete', methods=['POST'])
@login_required
@admin_required
def admin_delete_session(identifier, session_identifier):
    """Delete a session."""
    interview = Interview.get_by_identifier(identifier)
    if not interview:
        flash(_l('Entretien introuvable'), 'error')
        return redirect(url_for('interview.admin_list'))

    session = InterviewSession.get_by_identifier(session_identifier)
    if not session:
        flash(_l('Session non trouvee'), 'error')
        return redirect(url_for('interview.admin_view', identifier=interview.get_url_identifier()))

    if session.interview_id != interview.id:
        flash(_l('Session non trouvee'), 'error')
        return redirect(url_for('interview.admin_view', identifier=interview.get_url_identifier()))

    db.session.delete(session)
    db.session.commit()
    flash(_l('Session supprimee'), 'success')
    return redirect(url_for('interview.admin_view', identifier=interview.get_url_identifier()))


@interview_bp.route('/admin/interviews/<identifier>/export')
@login_required
@admin_required
def admin_export(identifier):
    """Export interview results as CSV."""
    from flask import Response
    import csv
    from io import StringIO

    interview = Interview.get_by_identifier(identifier)
    if not interview:
        flash(_l('Entretien introuvable'), 'error')
        return redirect(url_for('interview.admin_list'))
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


# ============================================================================
# Export / Import
# ============================================================================

@interview_bp.route('/admin/interviews/<identifier>/export-json')
@login_required
@admin_required
def admin_export_json(identifier):
    """Export interview configuration as JSON."""
    from flask import Response

    interview = Interview.get_by_identifier(identifier)
    if not interview:
        flash(_l('Entretien introuvable'), 'error')
        return redirect(url_for('interview.admin_list'))

    # Build export data
    export_data = {
        'version': '1.0',
        'export_type': 'interview',
        'exported_at': datetime.now().isoformat(),

        # Basic info
        'title': interview.title,
        'description': interview.description,
        'slug': interview.slug,

        # System prompt
        'system_prompt': interview.system_prompt,

        # Persona fields (for wizard re-editing)
        'persona_name': interview.persona_name,
        'persona_role': interview.persona_role,
        'persona_context': interview.persona_context,
        'persona_personality': interview.persona_personality,
        'persona_knowledge': interview.persona_knowledge,
        'persona_objectives': interview.persona_objectives,
        'persona_triggers': interview.persona_triggers,
        'student_context': interview.student_context,
        'student_objective': interview.student_objective,

        # Settings
        'max_interactions': interview.max_interactions,
        'max_duration_minutes': interview.max_duration_minutes,
        'allow_student_end': interview.allow_student_end,
        'ai_can_end': interview.ai_can_end,
        'student_starts': interview.student_starts,
        'opening_message': interview.opening_message,

        # File upload
        'require_file_upload': interview.require_file_upload,
        'file_upload_label': interview.file_upload_label,
        'file_upload_description': interview.file_upload_description,
        'file_upload_prompt_injection': interview.file_upload_prompt_injection,

        # Criteria
        'criteria': [
            {
                'name': c.name,
                'description': c.description,
                'max_points': c.max_points,
                'order': c.order,
                'evaluation_hints': c.evaluation_hints
            }
            for c in interview.criteria
        ]
    }

    # Generate filename
    safe_title = ''.join(c if c.isalnum() or c in '-_' else '_' for c in interview.title[:30])
    filename = f"entretien_{safe_title}_{datetime.now().strftime('%Y%m%d')}.json"

    return Response(
        json.dumps(export_data, ensure_ascii=False, indent=2),
        mimetype='application/json',
        headers={'Content-Disposition': f'attachment; filename={filename}'}
    )


@interview_bp.route('/admin/interviews/import', methods=['GET', 'POST'])
@login_required
@admin_required
def admin_import():
    """Import interview from JSON file."""
    if request.method == 'GET':
        return render_template('admin/interviews/import.html')

    # Handle POST - file upload
    if 'file' not in request.files:
        flash(_l('Aucun fichier selectionne.'), 'error')
        return redirect(url_for('interview.admin_import'))

    file = request.files['file']
    if file.filename == '':
        flash(_l('Aucun fichier selectionne.'), 'error')
        return redirect(url_for('interview.admin_import'))

    if not file.filename.endswith('.json'):
        flash(_l('Le fichier doit etre au format JSON.'), 'error')
        return redirect(url_for('interview.admin_import'))

    try:
        # Parse JSON
        data = json.load(file)

        # Validate format
        if data.get('export_type') != 'interview':
            flash(_l('Format de fichier invalide.'), 'error')
            return redirect(url_for('interview.admin_import'))

        # Check if slug already exists
        original_slug = data.get('slug')
        slug = original_slug
        if slug:
            counter = 1
            while Interview.query.filter_by(slug=slug).first():
                slug = f"{original_slug}-{counter}"
                counter += 1

        # Create new interview
        interview = Interview(
            title=data.get('title', 'Entretien importe'),
            description=data.get('description'),
            slug=slug,
            system_prompt=data.get('system_prompt', ''),

            # Persona fields
            persona_name=data.get('persona_name'),
            persona_role=data.get('persona_role'),
            persona_context=data.get('persona_context'),
            persona_personality=data.get('persona_personality'),
            persona_knowledge=data.get('persona_knowledge'),
            persona_objectives=data.get('persona_objectives'),
            persona_triggers=data.get('persona_triggers'),
            student_context=data.get('student_context'),
            student_objective=data.get('student_objective'),

            # Settings
            max_interactions=data.get('max_interactions', 30),
            max_duration_minutes=data.get('max_duration_minutes', 30),
            allow_student_end=data.get('allow_student_end', True),
            ai_can_end=data.get('ai_can_end', True),
            student_starts=data.get('student_starts', False),
            opening_message=data.get('opening_message'),

            # File upload
            require_file_upload=data.get('require_file_upload', False),
            file_upload_label=data.get('file_upload_label', 'Fichier'),
            file_upload_description=data.get('file_upload_description'),
            file_upload_prompt_injection=data.get('file_upload_prompt_injection'),

            # Ownership
            is_active=False,  # Imported interviews start inactive
            tenant_id=get_tenant_context().id if get_tenant_context() else None,
            created_by_id=current_user.id
        )

        db.session.add(interview)
        db.session.flush()  # Get the interview ID

        # Create criteria
        for i, crit_data in enumerate(data.get('criteria', [])):
            criterion = EvaluationCriterion(
                interview_id=interview.id,
                name=crit_data.get('name', f'Critere {i+1}'),
                description=crit_data.get('description'),
                max_points=crit_data.get('max_points', 5.0),
                order=crit_data.get('order', i),
                evaluation_hints=crit_data.get('evaluation_hints')
            )
            db.session.add(criterion)

        db.session.commit()

        flash(_l('Entretien "%(title)s" importe avec succes ! Il est inactif par defaut.', title=interview.title), 'success')
        return redirect(url_for('interview.admin_edit', identifier=interview.get_url_identifier()))

    except json.JSONDecodeError:
        flash(_l('Erreur de lecture du fichier JSON.'), 'error')
        return redirect(url_for('interview.admin_import'))
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"Import error: {str(e)}")
        flash(_l("Erreur lors de l'import: %(error)s", error=str(e)), 'error')
        return redirect(url_for('interview.admin_import'))
