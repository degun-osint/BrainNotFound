from flask_mail import Message
from flask import current_app, url_for
from app import mail


ADMIN_RESET_LINK_HOURS = 72


def send_email_async(msg):
    """Send in the background: Celery worker, or a greenlet of this process without Redis."""
    from app.tasks import run_task, send_email
    run_task(send_email, msg.subject, list(msg.recipients), msg.body, msg.html, msg.sender)


def send_verification_email(user, async_send=True):
    """Send email verification link to user."""
    token = user.generate_verification_token()
    verify_url = url_for('auth.verify_email', token=token, _external=True)

    msg = Message(
        subject='Verifiez votre compte BrainNotFound',
        recipients=[user.email]
    )

    msg.body = f"""Bonjour {user.first_name or user.username},

Bienvenue sur BrainNotFound !

Pour activer votre compte, veuillez cliquer sur le lien suivant :
{verify_url}

Ce lien est valide pendant 24 heures.

Si vous n'avez pas cree de compte, vous pouvez ignorer cet email.

Cordialement,
L'equipe BrainNotFound
"""

    msg.html = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #2563eb;">Bienvenue sur BrainNotFound !</h2>
        <p>Bonjour {user.first_name or user.username},</p>
        <p>Pour activer votre compte, veuillez cliquer sur le bouton ci-dessous :</p>
        <p style="text-align: center; margin: 30px 0;">
            <a href="{verify_url}"
               style="background-color: #2563eb; color: white; padding: 12px 24px;
                      text-decoration: none; border-radius: 6px; display: inline-block;">
                Verifier mon compte
            </a>
        </p>
        <p style="color: #666; font-size: 14px;">
            Ou copiez ce lien dans votre navigateur :<br>
            <a href="{verify_url}" style="color: #2563eb;">{verify_url}</a>
        </p>
        <p style="color: #666; font-size: 14px;">Ce lien est valide pendant 24 heures.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #999; font-size: 12px;">
            Si vous n'avez pas cree de compte, vous pouvez ignorer cet email.
        </p>
    </div>
</body>
</html>
"""

    try:
        if async_send:
            send_email_async(msg)
        else:
            mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send verification email to {user.email}: {e}")
        return False


def send_reset_email(user, async_send=True, by_admin=False):
    """Send password reset link to user (by_admin: sent by an administrator, valid 72 hours)."""
    hours = ADMIN_RESET_LINK_HOURS if by_admin else 1
    token = user.generate_reset_token(hours=hours)
    validity = f"{hours} heures" if hours > 1 else "1 heure"
    intro = ("Un administrateur vous invite a choisir (ou changer) votre mot de passe."
             if by_admin else "Vous avez demande la reinitialisation de votre mot de passe.")
    reset_url = url_for('auth.reset_password', token=token, _external=True)

    msg = Message(
        subject='Reinitialisation de votre mot de passe - BrainNotFound',
        recipients=[user.email]
    )

    msg.body = f"""Bonjour {user.first_name or user.username},

{intro}

Pour creer un nouveau mot de passe, cliquez sur le lien suivant :
{reset_url}

Ce lien est valide pendant {validity}.

Si vous n'avez pas demande cette reinitialisation, vous pouvez ignorer cet email.
Votre mot de passe restera inchange.

Cordialement,
L'equipe BrainNotFound
"""

    msg.html = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #2563eb;">Reinitialisation de mot de passe</h2>
        <p>Bonjour {user.first_name or user.username},</p>
        <p>{intro}</p>
        <p>Pour creer un nouveau mot de passe, cliquez sur le bouton ci-dessous :</p>
        <p style="text-align: center; margin: 30px 0;">
            <a href="{reset_url}"
               style="background-color: #2563eb; color: white; padding: 12px 24px;
                      text-decoration: none; border-radius: 6px; display: inline-block;">
                Reinitialiser mon mot de passe
            </a>
        </p>
        <p style="color: #666; font-size: 14px;">
            Ou copiez ce lien dans votre navigateur :<br>
            <a href="{reset_url}" style="color: #2563eb;">{reset_url}</a>
        </p>
        <p style="color: #666; font-size: 14px;">Ce lien est valide pendant {validity}.</p>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #999; font-size: 12px;">
            Si vous n'avez pas demande cette reinitialisation, vous pouvez ignorer cet email.
            Votre mot de passe restera inchange.
        </p>
    </div>
</body>
</html>
"""

    try:
        if async_send:
            send_email_async(msg)
        else:
            mail.send(msg)
        return True
    except Exception as e:
        current_app.logger.error(f"Failed to send reset email to {user.email}: {e}")
        return False


def send_bulk_email(users, subject, message_body, async_send=True):
    """Send email to multiple users."""
    from app.models.settings import SiteSettings

    success_count = 0
    fail_count = 0

    # Get site title for branding
    site_title = SiteSettings.get_settings().site_title or 'BrainNotFound'

    for user in users:
        if not user.email:
            fail_count += 1
            continue

        msg = Message(
            subject=f"{subject} - {site_title}",
            recipients=[user.email]
        )

        # Personalize message
        personalized_body = message_body.replace('{prenom}', user.first_name or user.username)
        personalized_body = personalized_body.replace('{nom}', user.last_name or '')
        personalized_body = personalized_body.replace('{username}', user.username)

        msg.body = f"""Bonjour {user.first_name or user.username},

{personalized_body}

Cordialement,
L'equipe {site_title}
"""

        msg.html = f"""
<html>
<body style="font-family: Arial, sans-serif; line-height: 1.6; color: #333;">
    <div style="max-width: 600px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #2563eb;">{subject}</h2>
        <p>Bonjour {user.first_name or user.username},</p>
        <div style="white-space: pre-line;">{personalized_body}</div>
        <hr style="border: none; border-top: 1px solid #eee; margin: 20px 0;">
        <p style="color: #999; font-size: 12px;">
            Cet email a ete envoye par {site_title}.
        </p>
    </div>
</body>
</html>
"""

        try:
            if async_send:
                send_email_async(msg)
            else:
                mail.send(msg)
            success_count += 1
        except Exception as e:
            current_app.logger.error(f"Failed to send bulk email to {user.email}: {e}")
            fail_count += 1

    return success_count, fail_count
