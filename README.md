# BrainNotFound

Plateforme d'évaluation en ligne open-source avec correction IA, mode examen anti-triche, analyse comportementale et support multi-organisations.

## Fonctionnalités principales

### Évaluation via IA
- **Questions QCM** : Réponses uniques ou multiples, correction automatique
- **Questions ouvertes** : Correction par Claude (Anthropic) avec feedback personnalisé
- **Sévérité configurable** : Indulgent, modéré ou strict selon le contexte
- **Génération de quiz** : Création automatique depuis un PDF, DOCX, Markdown ou TXT
- **Images dans les questions** : Support des images uploadées dans les quiz

### Mode examen (proctoring)
- **Une question par page** : Navigation contrôlée
- **Chronométrage** : Temps global et par question
- **Détection anti-triche** :
  - Changements d'onglet/fenêtre détectés
  - Raccourcis clavier bloqués (F12, Ctrl+U, etc.)
  - DevTools détectés
  - Copier-coller surveillé
- **Randomisation** : Options QCM mélangées par étudiant

### Entretiens conversationnels
- **Personnages IA** : Créez des scénarios avec des personnages simulés par Claude
- **Évaluation multi-critères** : Définissez des grilles d'évaluation personnalisées
- **Cas pratiques** : Entretiens d'embauche, gestion de conflits, détection de biais cognitifs
- **Feedback détaillé** : Analyse automatique de la conversation avec conseils d'amélioration
- **Templates prédéfinis** : RPS, entretien d'embauche, biais cognitifs et plus

### Analyse IA
- **Analyse individuelle** : Détection d'anomalies par réponse
- **Analyse de classe** : Patterns suspects, collusion potentielle
- **Indicateurs** : Temps anormaux, corrélations focus/notes

### Multi-organisations (tenants)
- **Isolation des données** : Chaque organisation a ses propres groupes, quiz et utilisateurs
- **Hiérarchie des rôles** :
  - Superadmin : Gère toutes les organisations
  - Admin organisation : Gère une organisation spécifique
  - Admin groupe : Gère un groupe
  - Membre : Utilisateur standard
- **Quotas configurables** :
  - Nombre max d'utilisateurs, quiz, groupes
  - Espace de stockage
  - Limites mensuelles IA (corrections, générations, analyses, entretiens)
- **Alertes quota** : Notification email quand un quota approche sa limite
- **Abonnements** : Date d'expiration optionnelle par organisation

### Administration
- **Multi-groupes** : Étudiants dans plusieurs groupes
- **Import CSV** : Import en masse des utilisateurs
- **Backup automatique** : Sauvegarde FTP planifiée (BDD + fichiers uploadés)
- **Restauration** : Restauration complète depuis les backups FTP
- **Paramètres** : Titre du site et email configurables
- **Pages personnalisées** : Création de pages en Markdown (mentions légales, CGU, etc.)

### Documentation intégrée
- **Portail `/docs`** : Documentation complète accessible dans l'application
- **Navigation** : Sidebar, table des matières, pagination
- **Syntaxe Markdown** : Coloration syntaxique, tableaux, code

## Installation

### Prérequis
- Docker et Docker Compose
- Clé API Anthropic
- Serveur SMTP pour les envois de mail

### Démarrage rapide

```bash
# Cloner le projet
git clone <repo-url>
cd BrainNotFound

# Configurer l'environnement
cp .env.example .env
# Éditer .env avec votre clé API

# Lancer
./start.sh
# ou: docker-compose up -d
```

Application accessible sur http://localhost:5000

### Identifiants par défaut

| Rôle | Username | Password |
|------|----------|----------|
| Superadmin | admin | admin123 |

Code groupe de démo : `DEMO2024`

## Format des quiz

Les quiz sont écrits en Markdown :

```markdown
# Titre du Quiz

Description optionnelle du quiz.

## QCM - Question à choix unique [2 points]
- [ ] Mauvaise réponse
- [x] Bonne réponse
- [ ] Autre option

## QCM - Question à choix multiples [3 points]
- [x] Correcte 1
- [ ] Incorrecte
- [x] Correcte 2

## OUVERTE - Question ouverte [5 points]
Expliquez le concept de...

### Réponse attendue
La réponse attendue qui servira de référence pour l'IA.
```

Documentation complète : `/docs/quiz-syntax` dans l'application.

## Configuration

### Variables d'environnement (.env)

```env
# Obligatoire
SECRET_KEY=cle-secrete-32-caracteres-minimum
ANTHROPIC_API_KEY=sk-ant-xxx

# Base de données
DATABASE_URL=mysql+pymysql://user:pass@host:3306/db

# Modèle Claude (optionnel)
CLAUDE_MODEL=claude-sonnet-4-20250514

# Sécurité (production)
ALLOWED_HOSTS=monsite.com
SESSION_COOKIE_SECURE=true

# Email (optionnel)
MAIL_SERVER=smtp.example.com
MAIL_USERNAME=noreply@example.com
MAIL_PASSWORD=xxx
```

### Backup FTP

Configurable dans Admin > Paramètres :
- Serveur FTP/FTPS avec chiffrement TLS
- Fréquence : horaire, quotidienne, hebdomadaire
- Rétention : suppression automatique des vieux backups
- Contenu : base de données + fichiers uploadés (images, PDF)
- Restauration : un clic depuis l'historique des backups

## Personnalisation

Les prompts IA et pages par défaut sont dans `private.example/`. Pour personnaliser :

```bash
# Copier le dossier exemple
cp -r private.example private

# Modifier les fichiers selon vos besoins
```

### Structure

```
private.example/          # Version par défaut (commitée)
├── prompts/
│   ├── grading.py       # Prompts de correction (sévérité, ton)
│   ├── generator.py     # Prompts de génération de quiz
│   ├── anomaly.py       # Prompts de détection de triche
│   └── interview.py     # Prompts pour entretiens IA
├── seed_data/
│   ├── a-propos.md      # Page "À propos"
│   └── mentions-legales.md
└── landing.html         # Page d'accueil personnalisable

private/                  # Vos personnalisations (non commitée)
└── ...                  # Même structure
```

### Priorité de chargement

1. `private/` (prioritaire)
2. `private.example/` (fallback)

## Architecture

```
app/
├── models/       # User, Group, Quiz, Question, Answer, Tenant, SiteSettings, Page
├── routes/       # auth, admin, quiz, tenant, docs
├── templates/    # Jinja2
├── static/       # CSS, JS
└── utils/        # Parser Markdown, Grading IA, Backup, Anomaly detection

docs/             # Documentation Markdown intégrée
migrations/       # Migrations Alembic
```

## Technologies

- **Backend** : Flask 3.x, SQLAlchemy, Flask-SocketIO
- **Base de données** : MySQL 8.0
- **IA** : Anthropic Claude API
- **Temps réel** : WebSocket (gevent)
- **Planification** : APScheduler
- **Déploiement** : Docker, Gunicorn

## Sécurité

- Mots de passe hashés (Werkzeug)
- Protection CSRF (Flask-WTF)
- Rate limiting (Flask-Limiter)
- Headers sécurité (X-Frame-Options, CSP, etc.)
- Validation des hosts autorisés
- Chiffrement des données sensibles (Fernet)
- Isolation des organisations (multi-tenant)

## Documentation

La documentation complète est accessible dans l'application à l'adresse `/docs` :

- **Démarrage** : Installation et premiers pas
- **Syntaxe Quiz** : Format Markdown des quiz
- **Guide Admin** : Gestion utilisateurs, quiz, analyses
- **Organisations** : Multi-tenant et groupes
- **Self-hosting** : Déploiement en production
- **Configuration** : Variables d'environnement
- **API** : Endpoints internes et WebSocket

## Licence

Ce projet est distribué sous licence **GNU General Public License v3.0** (GPLv3).

Voir le fichier [LICENSE](LICENSE) pour les détails.

---

Développé par [Manufacture Française d'OSINT](https://manufacture-osint.fr)
