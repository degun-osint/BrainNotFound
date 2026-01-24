"""
PDF generation utilities using ReportLab.
"""
from io import BytesIO
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm, mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from datetime import datetime
from app.utils import format_datetime, format_time


def generate_interview_pdf(session, interview):
    """Generate a PDF report for an interview session."""
    buffer = BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2*cm,
        leftMargin=2*cm,
        topMargin=2*cm,
        bottomMargin=2*cm
    )

    # Styles
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(
        name='Title2',
        parent=styles['Heading1'],
        fontSize=18,
        spaceAfter=12,
        textColor=colors.HexColor('#1a1a2e')
    ))
    styles.add(ParagraphStyle(
        name='Heading2Custom',
        parent=styles['Heading2'],
        fontSize=14,
        spaceBefore=20,
        spaceAfter=10,
        textColor=colors.HexColor('#1a1a2e'),
        borderPadding=(0, 0, 5, 0)
    ))
    styles.add(ParagraphStyle(
        name='Info',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.HexColor('#666666')
    ))
    styles.add(ParagraphStyle(
        name='MessageUser',
        parent=styles['Normal'],
        fontSize=10,
        backColor=colors.HexColor('#6366f1'),
        textColor=colors.white,
        borderPadding=8,
        spaceBefore=5,
        spaceAfter=5
    ))
    styles.add(ParagraphStyle(
        name='MessageAssistant',
        parent=styles['Normal'],
        fontSize=10,
        backColor=colors.HexColor('#f0f0f0'),
        borderPadding=8,
        spaceBefore=5,
        spaceAfter=5
    ))
    styles.add(ParagraphStyle(
        name='Feedback',
        parent=styles['Normal'],
        fontSize=9,
        textColor=colors.HexColor('#666666'),
        fontName='Helvetica-Oblique'
    ))

    elements = []

    # Title
    elements.append(Paragraph(interview.title, styles['Title2']))
    elements.append(Spacer(1, 5*mm))

    # Header info
    info_text = f"""
    <b>Candidat:</b> {session.user.full_name} ({session.user.email})<br/>
    <b>Date:</b> {format_datetime(session.started_at)}<br/>
    <b>Duree:</b> {session.get_duration_minutes()} minutes
    """
    if interview.persona_name:
        persona_info = interview.persona_name
        if interview.persona_role:
            persona_info += f" - {interview.persona_role}"
        info_text += f"<br/><b>Personnage:</b> {persona_info}"

    elements.append(Paragraph(info_text, styles['Info']))
    elements.append(Spacer(1, 10*mm))

    # Stats table
    percentage = session.get_score_percentage() if session.status == 'completed' else 0
    stats_data = [
        ['Score', 'Points', 'Echanges', 'Duree'],
        [
            f"{percentage:.0f}%",
            f"{session.total_score:.1f}/{session.max_score:.1f}",
            str(session.interaction_count),
            f"{session.get_duration_minutes()} min"
        ]
    ]

    stats_table = Table(stats_data, colWidths=[4*cm, 4*cm, 4*cm, 4*cm])
    stats_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#6366f1')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 10),
        ('FONTSIZE', (0, 1), (-1, -1), 14),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica-Bold'),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('TOPPADDING', (0, 1), (-1, -1), 12),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 12),
        ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#f5f5f5')),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
    ]))
    elements.append(stats_table)
    elements.append(Spacer(1, 10*mm))

    # AI Summary
    if session.ai_summary:
        elements.append(Paragraph("Synthese", styles['Heading2Custom']))
        summary_table = Table([[Paragraph(session.ai_summary, styles['Normal'])]], colWidths=[16*cm])
        summary_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f0f0ff')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#6366f1')),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(summary_table)
        elements.append(Spacer(1, 5*mm))

    # Scores detail
    elements.append(Paragraph("Detail des scores", styles['Heading2Custom']))

    for score in session.scores:
        pct = score.get_percentage()
        color = '#22c55e' if pct >= 80 else '#f59e0b' if pct >= 50 else '#ef4444'

        score_data = [
            [
                Paragraph(f"<b>{score.criterion.name}</b>", styles['Normal']),
                Paragraph(f"<b>{score.score:.1f} / {score.max_score:.1f}</b>", styles['Normal'])
            ]
        ]

        score_table = Table(score_data, colWidths=[12*cm, 4*cm])
        score_table.setStyle(TableStyle([
            ('ALIGN', (1, 0), (1, 0), 'RIGHT'),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 8),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fafafa')),
            ('LINEBELOW', (0, 0), (0, 0), 3, colors.HexColor(color)),
        ]))
        elements.append(score_table)

        if score.feedback:
            elements.append(Paragraph(score.feedback, styles['Feedback']))

        elements.append(Spacer(1, 3*mm))

    # File content (if any)
    if session.uploaded_file_content:
        elements.append(Paragraph("Document fourni", styles['Heading2Custom']))
        elements.append(Paragraph(f"<b>Fichier:</b> {session.uploaded_file_name}", styles['Info']))

        # Truncate content
        content = session.uploaded_file_content[:1500]
        if len(session.uploaded_file_content) > 1500:
            content += "..."

        file_table = Table([[Paragraph(content.replace('\n', '<br/>'), styles['Normal'])]], colWidths=[16*cm])
        file_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f5f5')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#dddddd')),
            ('LEFTPADDING', (0, 0), (-1, -1), 10),
            ('RIGHTPADDING', (0, 0), (-1, -1), 10),
            ('TOPPADDING', (0, 0), (-1, -1), 10),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 10),
        ]))
        elements.append(file_table)
        elements.append(Spacer(1, 5*mm))

    # Page break before transcript
    elements.append(PageBreak())

    # Transcript
    elements.append(Paragraph("Transcription de l'entretien", styles['Heading2Custom']))

    user_name = session.user.first_name or session.user.username
    persona_name = interview.persona_name or 'Personnage'

    for message in session.messages:
        time_str = format_time(message.created_at)
        content = message.content.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('\n', '<br/>')

        if message.role == 'user':
            header = f"<b>{user_name}</b> - {time_str}"
            msg_style = 'MessageUser'
        else:
            header = f"<b>{persona_name}</b> - {time_str}"
            msg_style = 'MessageAssistant'

        # Create a table for the message
        msg_data = [[
            Paragraph(f"{header}<br/>{content}", styles[msg_style])
        ]]

        if message.role == 'user':
            msg_table = Table(msg_data, colWidths=[12*cm])
            msg_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'RIGHT'),
            ]))
            # Wrap in another table to push right
            outer_table = Table([[None, msg_table]], colWidths=[4*cm, 12*cm])
            elements.append(outer_table)
        else:
            msg_table = Table(msg_data, colWidths=[12*cm])
            elements.append(msg_table)

        elements.append(Spacer(1, 2*mm))

    # Admin comment
    if session.admin_comment:
        elements.append(Spacer(1, 10*mm))
        elements.append(Paragraph("Commentaire de l'evaluateur", styles['Heading2Custom']))
        elements.append(Paragraph(session.admin_comment, styles['Normal']))

    # Footer
    elements.append(Spacer(1, 15*mm))
    footer_text = f"Document genere le {datetime.now().strftime('%d/%m/%Y a %H:%M')}"
    elements.append(Paragraph(footer_text, styles['Info']))

    # Build PDF
    doc.build(elements)
    buffer.seek(0)

    return buffer.getvalue()
