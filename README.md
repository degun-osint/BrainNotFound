# BrainNotFound

Plateforme d'évaluation en ligne open-source avec correction IA, entretiens simulés, mode examen anti-triche et gestion multi-établissements, pour les écoles comme pour la formation en entreprise.

Les nouveautés et les points à vérifier avant une mise à jour sont dans le [CHANGELOG](CHANGELOG.md).

## Fonctionnalités principales

### Évaluation via IA
- **Questions QCM** : Réponses uniques ou multiples, correction automatique
- **Questions ouvertes** : Correction par l'IA avec feedback personnalisé ; si l'IA ne peut pas corriger (quota atteint, refus), la réponse est laissée à l'intervenant
- **Fournisseur d'IA au choix** : Claude (Anthropic, par défaut et recommandé) ou tout service compatible OpenAI (OpenAI, Mistral, Gemini, OpenRouter, Ollama en local...), réglable dans Paramètres sans redémarrage
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
- **Randomisation** : Options QCM mélangées pour chaque apprenant

### Entretiens conversationnels
- **Personnages IA** : Créez des scénarios avec des personnages simulés par l'IA
- **Évaluation multi-critères** : Définissez des grilles d'évaluation personnalisées
- **Cas pratiques** : Entretiens d'embauche, gestion de conflits, détection de biais cognitifs
- **Feedback détaillé** : Analyse automatique de la conversation avec conseils d'amélioration
- **Templates prédéfinis** : RPS, entretien d'embauche, biais cognitifs et plus

### Analyse IA
- **Analyse individuelle** : Détection d'anomalies par réponse
- **Analyse de classe** : Patterns suspects, collusion potentielle
- **Indicateurs** : Temps anormaux, corrélations focus/notes

### Établissements, groupes et rôles
- **Vocabulaire** : Établissement / Groupe / Intervenant / Apprenant
- **Rôles** :
  - Super-admin : gère toute la plateforme
  - Admin d'établissement : gère les groupes, intervenants, apprenants et contenus de ses établissements
  - Intervenant : gère les groupes où il a ce rôle (un rôle par groupe : on peut être intervenant dans un groupe et apprenant dans un autre)
  - Apprenant : passe les quiz et entretiens des groupes dont il fait partie
- **Page Groupe** : apprenants, intervenants, contenus assignés et taux de réponse, code d'accès, lien d'invitation
- **Isolation** : chacun ne voit et ne modifie que son périmètre ; un contenu sans groupe n'est visible par aucun apprenant
- **Quotas par établissement** : utilisateurs, groupes, quiz, stockage, limites mensuelles IA (corrections, générations, analyses, entretiens), alertes email, date d'expiration de l'abonnement

### Administration
- **Comptes** : création avec invitation par email (la personne choisit son mot de passe), import CSV, liens de réinitialisation
- **Sauvegardes** : planifiées vers un FTP, ou à la demande (téléchargement, conservation sur le serveur)
- **Restauration** : depuis le FTP, le serveur ou un fichier envoyé ; instantané automatique de l'état actuel et retour arrière en cas d'échec
- **Suppression d'un établissement** avec son contenu, après sauvegarde automatique
- **Paramètres** : titre du site, email, fournisseur et modèle d'IA
- **Pages personnalisées** : Création de pages en Markdown (mentions légales, CGU, etc.)

### Internationalisation (i18n)
- **Langues supportées** : Français (défaut) et Anglais
- **Sélecteur de langue** : Dans la barre de navigation
- **Préférence utilisateur** : Sauvegardée en base de données
- **Prompts IA multilingues** : Correction et feedback dans la langue choisie
- **Détection automatique** : Via Accept-Language du navigateur

### Documentation intégrée
- **Portail `/docs`** : Documentation complète accessible dans l'application
- **Navigation** : Sidebar, table des matières, pagination
- **Syntaxe Markdown** : Coloration syntaxique, tableaux, code

## Installation

### Prérequis
- Docker et Docker Compose
- Une clé d'API Anthropic (ou d'un autre fournisseur compatible OpenAI, ou un serveur Ollama local)
- Un serveur SMTP pour les envois de mail (invitations, réinitialisation de mot de passe)

### Ressources serveur

Mesures sur la pile Docker complète (application + MariaDB 12.3), avec un établissement de 600 apprenants et 6 000 copies :

| | Au repos | En charge (20 utilisateurs en continu) |
|---|---|---|
| Application | ~100 Mo | ~125 Mo, 1 cœur |
| MariaDB (config `docker/mariadb/low-memory.cnf`) | ~70 Mo | ~170 Mo |

- **Minimum** : 1 vCPU, 1 Go de RAM, 3 Go de disque (images Docker ~1,3 Go + données).
- **Confortable** : 2 vCPU, 2 Go de RAM.
- L'IA tourne chez le fournisseur (Anthropic...) : elle ne consomme rien localement, sauf avec un modèle local type Ollama, qui demande alors sa propre machine (GPU ou beaucoup de RAM).
- Débit mesuré : ~90 pages admin par seconde en continu, une page servie en 10 à 50 ms. Une classe de 30 apprenants en génère quelques-unes par seconde.
- L'application tourne sur un seul processus (nécessaire pour les WebSockets sans broker Redis) : plus de 2 cœurs n'apportent rien à l'application elle-même.

### Démarrage rapide

```bash
# Cloner le projet
git clone <repo-url>
cd BrainNotFound

# Configurer l'environnement
cp .env.example .env
# Éditer .env : SECRET_KEY, mots de passe MYSQL_*, ADMIN_DEFAULT_PASSWORD, clé d'API

# Lancer
docker compose up -d --build
```

Application accessible sur http://localhost:5006. Au premier démarrage, la base est créée et les migrations s'appliquent automatiquement.

### Identifiants par défaut

| Rôle | Identifiant | Mot de passe |
|------|-------------|--------------|
| Super-admin | admin | valeur de `ADMIN_DEFAULT_PASSWORD` (`admin123` si absente) |

Changez ce mot de passe dès la première connexion. Code du groupe de démo : `DEMO2024`.

### Déploiement sur un serveur

`deploy.sh` déploie sur un VPS par SSH (`VPS_HOST=... VPS_PATH=... ./deploy.sh`) : sauvegarde de la base avant tout envoi, synchronisation qui ne touche jamais aux `.env*`, `uploads/` et `backups/` du serveur, reconstruction sans couper le site, puis vérification que l'application répond. Détails et procédure manuelle : [docs/self-hosting.md](docs/self-hosting.md).

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

# Base de données (MariaDB ; le conteneur lit aussi les MYSQL_*)
MYSQL_ROOT_PASSWORD=xxx
MYSQL_DATABASE=brainnotfound
MYSQL_USER=brainnotfound
MYSQL_PASSWORD=xxx
DATABASE_URL=mysql+pymysql://brainnotfound:xxx@db:3306/brainnotfound

# Compte admin créé au premier démarrage
ADMIN_DEFAULT_PASSWORD=xxx

# IA : réglable aussi dans Paramètres (prioritaire, sans redémarrage)
ANTHROPIC_API_KEY=sk-ant-xxx
CLAUDE_MODEL=claude-opus-5-5
# Autre fournisseur compatible OpenAI (optionnel)
# AI_PROVIDER=openai_compatible
# AI_BASE_URL=http://ollama:11434/v1
# AI_API_KEY=
# AI_MODEL=llama3.1

# Sécurité (production)
ALLOWED_HOSTS=monsite.com
SESSION_COOKIE_SECURE=true

# Email (optionnel)
MAIL_SERVER=smtp.example.com
MAIL_USERNAME=noreply@example.com
MAIL_PASSWORD=xxx
```

### Sauvegardes

Configurables dans Administration > Paramètres :
- Sauvegarde automatique vers un serveur FTP/FTPS (fréquence horaire, quotidienne ou hebdomadaire, rétention en jours)
- Sauvegarde à la demande : téléchargement direct, ou conservation dans `backups/` (volume Docker) sans FTP
- Contenu : base de données + fichiers envoyés (images des quiz)
- Restauration depuis le FTP, le serveur ou un fichier envoyé (confirmation par `RESTAURER`), avec instantané automatique de l'état actuel

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
├── models/       # User, Group, Quiz, Question, Answer, Tenant, Interview, SiteSettings, Page
├── routes/       # auth, admin, quiz, interview, tenant, docs
├── templates/    # Jinja2
├── static/       # CSS, JS
└── utils/
    ├── scope.py        # Périmètre d'un admin (établissements, groupes, contenus, utilisateurs)
    ├── ai_client.py    # Accès unique au fournisseur d'IA
    ├── deletion.py     # Suppression d'utilisateurs et d'établissements
    ├── db_schema.py    # Mise à jour du schéma (démarrage, restauration)
    └── ...             # Parser Markdown, correction IA, sauvegardes, détection d'anomalies

docker/mariadb/   # Configuration MariaDB pour petits serveurs
docs/             # Documentation Markdown intégrée
migrations/       # Migrations Alembic (appliquées au démarrage)
scripts/          # Migration au démarrage, restauration, étapes de déploiement
tests/            # Tests pytest
```

### Tests

```bash
pip install -r requirements-dev.txt
pytest tests          # SQLite en mémoire, ni base MariaDB ni clé d'API nécessaires
```

## Internationalisation

L'application utilise Flask-Babel pour le support multilingue. Les traductions sont compilées automatiquement au démarrage du conteneur Docker.

### Ajouter/modifier des traductions

```bash
# 1. Extraire les nouvelles chaînes à traduire
pybabel extract -F babel.cfg -k _l -k _ -o messages.pot .

# 2. Mettre à jour les catalogues existants
pybabel update -i messages.pot -d translations

# 3. Éditer les traductions
# Fichier : translations/en/LC_MESSAGES/messages.po

# 4. Compiler (automatique au démarrage Docker, ou manuellement)
pybabel compile -d translations
```

### Structure des fichiers

```
babel.cfg                    # Configuration d'extraction
messages.pot                 # Catalogue source (généré)
translations/
├── fr/LC_MESSAGES/
│   ├── messages.po         # Traductions françaises
│   └── messages.mo         # Compilé (généré)
└── en/LC_MESSAGES/
    ├── messages.po         # Traductions anglaises
    └── messages.mo         # Compilé (généré)
```

### Prompts IA multilingues

Les prompts dans `private.example/prompts/` utilisent des dictionnaires par langue :

```python
GRADING_PROMPT_TEMPLATE = {
    'fr': """Tu es un correcteur...""",
    'en': """You are a grader..."""
}
```

## Technologies

- **Backend** : Flask 3.x, SQLAlchemy, Flask-SocketIO, Flask-Babel
- **Base de données** : MariaDB 12.3 LTS
- **IA** : Anthropic Claude (par défaut), ou API compatible OpenAI
- **Temps réel** : WebSocket (Flask-SocketIO, gevent, simple-websocket)
- **Planification** : APScheduler
- **Déploiement** : Docker, Gunicorn

## Sécurité

- Mots de passe hashés (Werkzeug), sessions liées à l'identifiant unique du compte
- Protection CSRF (Flask-WTF)
- Limitation des tentatives sur la connexion, l'inscription et la réinitialisation (Flask-Limiter)
- Headers sécurité (X-Frame-Options, CSP, etc.)
- Validation des hosts autorisés (`ALLOWED_HOSTS`)
- Chiffrement des données sensibles en base (clé d'API, mot de passe FTP)
- Isolation des établissements et des groupes, droits d'écriture limités aux rôles inférieurs
- Contenus des apprenants délimités dans les prompts (protection contre l'injection de consignes)
- `.env` jamais copié dans l'image Docker

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
