"""
Modèle Tenant pour la gestion multi-tenant logique.
Un tenant représente une organisation/client avec ses propres limites et admins.
"""
from app import db
from datetime import datetime
import secrets


# Association table for Tenant-Admin many-to-many
tenant_admins = db.Table('tenant_admins',
    db.Column('tenant_id', db.Integer, db.ForeignKey('tenants.id'), primary_key=True),
    db.Column('user_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('created_at', db.DateTime, default=datetime.utcnow)
)


class Tenant(db.Model):
    """
    Un tenant représente une organisation/client.

    Hiérarchie des rôles :
    - Superadmin : gère tous les tenants (is_admin=True sur User)
    - Tenant Admin : gère un tenant spécifique (via tenant_admins)
    - Group Admin : gère un groupe (via user_groups avec role='admin')
    - Member : utilisateur standard (via user_groups avec role='member')
    """
    __tablename__ = 'tenants'

    id = db.Column(db.Integer, primary_key=True)

    # Identification
    slug = db.Column(db.String(50), unique=True, nullable=False, index=True)
    name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text)

    # État
    is_active = db.Column(db.Boolean, default=True)

    # Limites fixes
    max_users = db.Column(db.Integer, default=0)      # 0 = illimité
    max_quizzes = db.Column(db.Integer, default=0)    # 0 = illimité
    max_groups = db.Column(db.Integer, default=0)     # 0 = illimité
    max_storage_mb = db.Column(db.Integer, default=0) # 0 = illimité

    # Limites mensuelles IA (0 = illimité)
    monthly_ai_corrections = db.Column(db.Integer, default=0)
    monthly_quiz_generations = db.Column(db.Integer, default=0)
    monthly_class_analyses = db.Column(db.Integer, default=0)

    # Usage mensuel (reset automatique chaque mois)
    used_ai_corrections = db.Column(db.Integer, default=0)
    used_quiz_generations = db.Column(db.Integer, default=0)
    used_class_analyses = db.Column(db.Integer, default=0)
    usage_reset_date = db.Column(db.Date)  # Date du dernier reset

    # Limites interviews
    monthly_interviews = db.Column(db.Integer, default=0)  # 0 = illimite
    used_interviews = db.Column(db.Integer, default=0)

    # Alertes quota
    quota_alert_enabled = db.Column(db.Boolean, default=False)
    quota_alert_threshold = db.Column(db.Integer, default=10)  # Pourcentage restant
    quota_alert_sent_at = db.Column(db.DateTime)  # Date du dernier envoi d'alerte

    # Abonnement
    subscription_expires_at = db.Column(db.Date)  # None = pas d'expiration

    # Contact
    contact_email = db.Column(db.String(200))
    contact_name = db.Column(db.String(200))

    # Notes internes (pour le superadmin)
    internal_notes = db.Column(db.Text)

    # Métadonnées
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relations
    groups = db.relationship('Group', backref='tenant', lazy='dynamic')
    quizzes = db.relationship('Quiz', backref='tenant', lazy='dynamic')

    # Admins du tenant (many-to-many avec User)
    admins = db.relationship('User', secondary=tenant_admins,
                            backref=db.backref('admin_tenants', lazy='dynamic'),
                            lazy='dynamic')

    def __repr__(self):
        return f'<Tenant {self.slug}>'

    @classmethod
    def get_by_identifier(cls, identifier):
        """Get tenant by slug or numeric ID."""
        if not identifier:
            return None
        identifier_str = str(identifier)
        # Try by slug first
        tenant = cls.query.filter_by(slug=identifier_str).first()
        if tenant:
            return tenant
        # Fall back to numeric ID
        try:
            tenant_id = int(identifier_str)
            return cls.query.get(tenant_id)
        except (ValueError, TypeError):
            return None

    def get_url_identifier(self):
        """Get the preferred identifier for URLs."""
        return self.slug

    @staticmethod
    def generate_slug(name):
        """Génère un slug à partir du nom."""
        import re
        slug = name.lower()
        slug = re.sub(r'[àáâãäå]', 'a', slug)
        slug = re.sub(r'[èéêë]', 'e', slug)
        slug = re.sub(r'[ìíîï]', 'i', slug)
        slug = re.sub(r'[òóôõö]', 'o', slug)
        slug = re.sub(r'[ùúûü]', 'u', slug)
        slug = re.sub(r'[ç]', 'c', slug)
        slug = re.sub(r'[^a-z0-9]+', '-', slug)
        slug = slug.strip('-')

        # Vérifier unicité
        base_slug = slug
        counter = 1
        while Tenant.query.filter_by(slug=slug).first():
            slug = f"{base_slug}-{counter}"
            counter += 1

        return slug

    # ==================== Méthodes de comptage ====================

    def get_users_count(self):
        """Compte le nombre d'utilisateurs uniques dans ce tenant."""
        from app.models.user import User, user_groups
        return User.query.join(user_groups).join(
            db.Model.metadata.tables['groups']
        ).filter(
            db.Model.metadata.tables['groups'].c.tenant_id == self.id
        ).distinct().count()

    def has_member(self, user):
        """Check if a user already belongs to one of this tenant's groups."""
        from app.models.user import user_groups
        groups = db.Model.metadata.tables['groups']
        return db.session.query(user_groups.c.user_id).join(
            groups, groups.c.id == user_groups.c.group_id
        ).filter(groups.c.tenant_id == self.id, user_groups.c.user_id == user.id).first() is not None

    def get_quizzes_count(self):
        """Compte le nombre de quiz dans ce tenant."""
        return self.quizzes.count()

    def get_groups_count(self):
        """Compte le nombre de groupes dans ce tenant."""
        return self.groups.count()

    # ==================== Vérification des limites ====================

    def can_add_user(self):
        """Vérifie si on peut ajouter un utilisateur."""
        if self.max_users <= 0:
            return True
        return self.get_users_count() < self.max_users

    def can_add_quiz(self):
        """Vérifie si on peut ajouter un quiz."""
        if self.max_quizzes <= 0:
            return True
        return self.get_quizzes_count() < self.max_quizzes

    def can_add_group(self):
        """Vérifie si on peut ajouter un groupe."""
        if self.max_groups <= 0:
            return True
        return self.get_groups_count() < self.max_groups

    def get_usage_stats(self):
        """Retourne les statistiques d'utilisation."""
        return {
            'users': {
                'current': self.get_users_count(),
                'max': self.max_users if self.max_users > 0 else None
            },
            'quizzes': {
                'current': self.get_quizzes_count(),
                'max': self.max_quizzes if self.max_quizzes > 0 else None
            },
            'groups': {
                'current': self.get_groups_count(),
                'max': self.max_groups if self.max_groups > 0 else None
            }
        }

    # ==================== Gestion des admins ====================

    def add_admin(self, user):
        """Ajoute un admin au tenant."""
        from app.models.user import User
        if user not in self.admins.all():
            self.admins.append(user)
            User.clear_role_cache()

    def remove_admin(self, user):
        """Retire un admin du tenant."""
        from app.models.user import User
        if user in self.admins.all():
            self.admins.remove(user)
            User.clear_role_cache()

    def is_admin(self, user):
        """Vérifie si un user est admin de ce tenant."""
        return user.is_admin_of_tenant(self.id)

    # ==================== Abonnement ====================

    def is_subscription_active(self):
        """Vérifie si l'abonnement est actif."""
        if not self.is_active:
            return False
        if self.subscription_expires_at is None:
            return True  # Pas d'expiration = toujours actif
        from datetime import date
        return self.subscription_expires_at >= date.today()

    def days_until_expiration(self):
        """Retourne le nombre de jours avant expiration (None si pas d'expiration)."""
        if self.subscription_expires_at is None:
            return None
        from datetime import date
        delta = self.subscription_expires_at - date.today()
        return delta.days

    # ==================== Usage mensuel IA ====================

    # Usage counters, keyed by kind: (limit column, counter column)
    USAGE_FIELDS = {
        'corrections': ('monthly_ai_corrections', 'used_ai_corrections'),
        'generations': ('monthly_quiz_generations', 'used_quiz_generations'),
        'analyses': ('monthly_class_analyses', 'used_class_analyses'),
        'interviews': ('monthly_interviews', 'used_interviews'),
    }

    def _check_reset_usage(self):
        """Reset the counters when a new month starts (atomic, no commit)."""
        from datetime import date
        first_of_month = date.today().replace(day=1)
        if self.usage_reset_date is not None and self.usage_reset_date >= first_of_month:
            return
        # Conditional UPDATE: only one concurrent worker actually resets
        Tenant.query.filter(
            Tenant.id == self.id,
            db.or_(Tenant.usage_reset_date.is_(None), Tenant.usage_reset_date < first_of_month)
        ).update({
            'used_ai_corrections': 0, 'used_quiz_generations': 0,
            'used_class_analyses': 0, 'used_interviews': 0,
            'usage_reset_date': first_of_month,
        }, synchronize_session=False)
        db.session.refresh(self)

    def can_use(self, kind, count=1):
        """Check subscription and monthly quota for an AI usage kind."""
        if not self.is_subscription_active():
            return False
        limit_field, used_field = self.USAGE_FIELDS[kind]
        limit = getattr(self, limit_field)
        if not limit or limit <= 0:
            return True  # None or 0 = unlimited
        self._check_reset_usage()
        return getattr(self, used_field) + count <= limit

    def increment_usage(self, kind, count=1):
        """Atomically add to a usage counter and commit (safe with concurrent grading tasks)."""
        self._check_reset_usage()
        used_field = self.USAGE_FIELDS[kind][1]
        column = getattr(Tenant, used_field)
        Tenant.query.filter(Tenant.id == self.id).update(
            {used_field: column + count}, synchronize_session=False
        )
        db.session.commit()
        db.session.refresh(self)
        self.check_and_send_quota_alert()

    def can_use_ai_correction(self):
        return self.can_use('corrections')

    def can_generate_quiz(self):
        return self.can_use('generations')

    def can_analyze_class(self):
        return self.can_use('analyses')

    def can_use_interview(self):
        return self.can_use('interviews')

    def increment_ai_corrections(self, count=1):
        self.increment_usage('corrections', count)

    def increment_quiz_generations(self, count=1):
        self.increment_usage('generations', count)

    def increment_class_analyses(self, count=1):
        self.increment_usage('analyses', count)

    def increment_interviews(self, count=1):
        self.increment_usage('interviews', count)

    def get_ai_usage_stats(self):
        """Retourne les statistiques d'utilisation IA."""
        self._check_reset_usage()
        return {
            'corrections': {
                'used': self.used_ai_corrections,
                'limit': self.monthly_ai_corrections if self.monthly_ai_corrections > 0 else None
            },
            'generations': {
                'used': self.used_quiz_generations,
                'limit': self.monthly_quiz_generations if self.monthly_quiz_generations > 0 else None
            },
            'analyses': {
                'used': self.used_class_analyses,
                'limit': self.monthly_class_analyses if self.monthly_class_analyses > 0 else None
            },
            'interviews': {
                'used': self.used_interviews,
                'limit': self.monthly_interviews if self.monthly_interviews > 0 else None
            }
        }

    def check_and_send_quota_alert(self):
        """Vérifie les quotas et envoie une alerte si un seuil est atteint."""
        if not self.quota_alert_enabled or not self.contact_email:
            return

        # Vérifier si on a déjà envoyé une alerte ce mois
        from datetime import date
        today = date.today()
        first_of_month = today.replace(day=1)
        if self.quota_alert_sent_at and self.quota_alert_sent_at.date() >= first_of_month:
            return  # Déjà alerté ce mois

        # Calculer les quotas critiques
        critical_quotas = []
        threshold = self.quota_alert_threshold

        def check_quota(name, used, limit):
            if limit and limit > 0:
                remaining_pct = ((limit - used) / limit) * 100
                if remaining_pct <= threshold:
                    return {'name': name, 'used': used, 'limit': limit, 'remaining_pct': round(remaining_pct, 1)}
            return None

        quotas_to_check = [
            ('Corrections IA', self.used_ai_corrections, self.monthly_ai_corrections),
            ('Générations quiz', self.used_quiz_generations, self.monthly_quiz_generations),
            ('Analyses classe', self.used_class_analyses, self.monthly_class_analyses),
            ('Entretiens IA', self.used_interviews, self.monthly_interviews),
        ]

        for name, used, limit in quotas_to_check:
            result = check_quota(name, used, limit)
            if result:
                critical_quotas.append(result)

        if not critical_quotas:
            return

        # Envoyer l'alerte
        self._send_quota_alert_email(critical_quotas)
        self.quota_alert_sent_at = datetime.utcnow()
        db.session.commit()

    def _send_quota_alert_email(self, critical_quotas):
        """Envoie l'email d'alerte quota."""
        from flask import current_app
        from flask_mail import Message
        from app import mail

        try:
            quota_list = '\n'.join([
                f"  - {q['name']}: {q['used']}/{q['limit']} ({q['remaining_pct']}% restant)"
                for q in critical_quotas
            ])

            msg = Message(
                subject=f"[{current_app.config.get('SITE_TITLE', 'BrainNotFound')}] Alerte quota - {self.name}",
                recipients=[self.contact_email],
                body=f"""Bonjour,

Certains quotas de votre organisation "{self.name}" sont presque atteints :

{quota_list}

Seuil d'alerte configuré : {self.quota_alert_threshold}%

Contactez votre administrateur pour augmenter vos limites si nécessaire.

--
{current_app.config.get('SITE_TITLE', 'BrainNotFound')}
"""
            )
            mail.send(msg)
            current_app.logger.info(f"Quota alert sent to {self.contact_email} for tenant {self.slug}")
        except Exception as e:
            current_app.logger.error(f"Failed to send quota alert: {str(e)}")
