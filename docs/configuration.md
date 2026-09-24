# Configuration

Toutes les options de configuration de BrainNotFound : variables d'environnement (fichier `.env`) et paramètres modifiables depuis l'interface.

## Variables d'environnement

Le fichier `.env` est lu par le conteneur de l'application (`env_file` dans `docker-compose.yml`). Il contient des secrets : ne le commitez jamais et ne le montez pas dans un conteneur.

### Indispensables

| Variable | Description |
|----------|-------------|
| `SECRET_KEY` | Clé secrète Flask (sessions, jetons CSRF, liens d'invitation). Chaîne aléatoire de 32 caractères ou plus. Sans elle, une clé temporaire est générée et toutes les sessions sautent au redémarrage. |
| `DATABASE_URL` | Connexion à la base, par exemple `mysql+pymysql://quizuser:motdepasse@db:3306/quizdb` (MariaDB utilise le même pilote). |
| `MYSQL_ROOT_PASSWORD`, `MYSQL_DATABASE`, `MYSQL_USER`, `MYSQL_PASSWORD` | Initialisation du conteneur MariaDB, à accorder avec `DATABASE_URL`. |
| `ADMIN_DEFAULT_PASSWORD` | Mot de passe du compte `admin` créé au premier démarrage (`admin123` si absent). |

### Intelligence artificielle

Toutes ces valeurs peuvent aussi être réglées dans **Paramètres**, qui ont la priorité. Le `.env` sert de valeur par défaut.

| Variable | Description | Défaut |
|----------|-------------|--------|
| `ANTHROPIC_API_KEY` | Clé API Anthropic | aucune |
| `CLAUDE_MODEL` | Modèle Claude | `claude-opus-5-5` |
| `AI_PROVIDER` | `anthropic` ou `openai_compatible` | `anthropic` |
| `AI_BASE_URL` | URL d'un service compatible OpenAI, par exemple `http://ollama:11434/v1` | aucune |
| `AI_API_KEY` | Clé de ce service | aucune |
| `AI_MODEL` | Modèle de ce service | aucun |

Sans clé, l'application fonctionne mais les fonctions IA sont indisponibles : les réponses ouvertes passent « à corriger ».

### Sécurité

| Variable | Description | Défaut |
|----------|-------------|--------|
| `ALLOWED_HOSTS` | Noms d'hôte acceptés, séparés par des virgules. Toute autre valeur de l'en-tête `Host` reçoit une erreur 403. Sert aussi de liste d'origines pour les WebSockets. | vide = tous |
| `SESSION_COOKIE_SECURE` | Cookie de session envoyé en HTTPS uniquement. À activer derrière HTTPS, jamais en HTTP simple (la connexion échouerait). | `false` |
| `SETTINGS_ENCRYPTION_KEY` | Clé de chiffrement des secrets enregistrés en base (clé API, mot de passe FTP). Si absente, elle est dérivée de `SECRET_KEY`. | dérivée |
| `FLASK_DEBUG` | Mode debug. Jamais en production. | `false` |

Changer `SECRET_KEY` ou `SETTINGS_ENCRYPTION_KEY` rend illisibles les secrets déjà enregistrés en base : l'application revient alors aux valeurs du `.env`, et il faut ressaisir la clé API et le mot de passe FTP dans **Paramètres**.

Non configurables par variable : cookie inaccessible au JavaScript, `SameSite=Lax`, session d'une heure, taille maximale d'un envoi de fichier de 16 Mo (hors restauration de sauvegarde).

### Email

Utilisé pour la vérification des adresses, les liens de mot de passe, les emails de groupe et les alertes de quota.

| Variable | Description | Défaut |
|----------|-------------|--------|
| `MAIL_SERVER` | Serveur SMTP | `localhost` |
| `MAIL_PORT` | Port SMTP | `587` |
| `MAIL_USE_TLS` | STARTTLS | `true` |
| `MAIL_USE_SSL` | SSL direct (port 465 en général) | `false` |
| `MAIL_USERNAME` | Utilisateur SMTP | aucun |
| `MAIL_PASSWORD` | Mot de passe SMTP | aucun |
| `MAIL_DEFAULT_SENDER` | Expéditeur, par exemple `BrainNotFound <noreply@example.com>` | `noreply@localhost` |

### Sauvegardes

| Variable | Description | Défaut |
|----------|-------------|--------|
| `BACKUP_LOCAL_DIR` | Dossier des sauvegardes conservées sur le serveur (sauvegardes manuelles sans FTP, états d'avant restauration, d'avant déploiement et d'avant suppression d'un établissement) | `backups` |
| `BACKUP_MAX_UPLOAD_MB` | Taille maximale d'une sauvegarde envoyée depuis le navigateur pour restauration | `2048` |

Derrière Nginx ou CloudPanel, relevez aussi `client_max_body_size` pour que la restauration depuis le navigateur passe.

### Exemple de `.env`

```env
# Application
SECRET_KEY=remplacez-par-une-cle-aleatoire-de-64-caracteres
ADMIN_DEFAULT_PASSWORD=un-mot-de-passe-solide

# Base de données
MYSQL_ROOT_PASSWORD=mot-de-passe-root
MYSQL_DATABASE=quizdb
MYSQL_USER=quizuser
MYSQL_PASSWORD=mot-de-passe-base
DATABASE_URL=mysql+pymysql://quizuser:mot-de-passe-base@db:3306/quizdb

# IA (modifiable ensuite dans Paramètres)
ANTHROPIC_API_KEY=sk-ant-...
CLAUDE_MODEL=claude-opus-5-5

# Sécurité
ALLOWED_HOSTS=quiz.example.com
SESSION_COOKIE_SECURE=true

# Email
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=noreply@example.com
MAIL_PASSWORD=mot-de-passe-smtp
MAIL_DEFAULT_SENDER=BrainNotFound <noreply@example.com>
```

`.env.example` à la racine du dépôt liste toutes les variables.

## Paramètres dans l'interface

Les super-administrateurs règlent le reste dans **Paramètres** (icône engrenage). Les changements s'appliquent immédiatement, sans redémarrage.

### Identité du site

- **Nom du site** : affiché dans la barre de navigation et les titres de page
- **Email de contact** : affiché pour le support et les notifications
- **Pages personnalisées** : pages libres, affichables dans le menu ou le pied de page

### Intelligence artificielle

| Réglage | Description |
|---------|-------------|
| **Fournisseur** | Anthropic Claude (défaut) ou service compatible OpenAI |
| **URL du fournisseur** | Pour un service compatible OpenAI : OpenAI, Mistral, Gemini, OpenRouter, Groq, Ollama en local... |
| **Clé API** | Laisser vide pour conserver la clé actuelle. La page indique si elle vient de la base ou du `.env`. |
| **Modèle** | Vide = modèle du `.env` |

**Tester et lister les modèles** vérifie la clé et remplit la liste des modèles réellement disponibles.

Changer de fournisseur ou d'URL efface la clé enregistrée, pour qu'elle ne soit jamais envoyée à un autre serveur. Choisir Grok (URL `x.ai` ou modèle dont le nom contient `grok`, y compris via un agrégateur) demande une confirmation.

Le réglage est global à l'instance : tous les établissements utilisent le même fournisseur.

#### Modèles Claude

| Modèle | Usage |
|--------|-------|
| `claude-opus-5-5` | Défaut, recommandé : très bon rapport qualité / coût |
| `claude-sonnet-5` | Plus économique, pour de gros volumes de corrections |
| `claude-haiku-4-5` | Le plus rapide et le moins cher |
| `claude-fable-5-1` | Le plus performant, au prix le plus élevé |

Sur les modèles 5.x, la réflexion est toujours active ; l'application fixe l'effort selon l'usage (`low` pour les répliques du personnage en entretien, `medium` ailleurs). Les modèles qui ne gèrent pas ce paramètre reçoivent la requête sans lui.

#### Autres fournisseurs

La qualité des corrections dépend beaucoup du modèle. Avant de l'ouvrir aux apprenants, testez un quiz avec questions ouvertes et un entretien sur le modèle choisi. Un modèle local (Ollama) évite d'envoyer les réponses des apprenants à un tiers, mais demande une machine bien plus puissante que l'application elle-même.

### Sauvegardes

| Réglage | Description |
|---------|-------------|
| **Sauvegardes automatiques** | Active l'envoi planifié vers un serveur FTP |
| **Serveur FTP**, **Port**, **Nom d'utilisateur**, **Mot de passe**, **Chemin distant** | Destination ; **Tester la connexion** la vérifie |
| **Fréquence** | Toutes les heures, quotidienne ou hebdomadaire |
| **Heure (0-23)**, **Jour de la semaine** | Moment de l'exécution |
| **Conservation (jours)** | Au-delà, les sauvegardes sont supprimées automatiquement (30 jours par défaut) |

Une sauvegarde contient la base de données et les fichiers envoyés (images des quiz). Voir [Administration](admin-guide#sauvegarde-et-restauration) pour la restauration.

## Docker Compose

### Services

| Service | Image | Rôle |
|---------|-------|------|
| `db` | `mariadb:12.3` | Base de données, avec des réglages mémoire réduits (`docker/mariadb/low-memory.cnf`) |
| `web` | construite depuis le `Dockerfile` | Application (gunicorn, un worker gevent) |

### Volumes

| Volume | Contenu |
|--------|---------|
| `mariadb_data` | Données MariaDB |
| `mysql_data` | Ancien volume MySQL, conservé tel quel après la migration (retour arrière possible) |
| `./uploads` | Fichiers envoyés (images des quiz) |
| `./backups` | Sauvegardes conservées sur le serveur |

### Ports

| Port hôte | Service | En production |
|-----------|---------|---------------|
| `5006` | Application | Derrière un reverse proxy HTTPS |
| `3312` | MariaDB | À fermer au pare-feu, ou à retirer du `docker-compose.yml` |

## Générer une clé secrète

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
# ou
openssl rand -hex 32
```

## Au démarrage

Le conteneur `web` attend que MariaDB soit prête (healthcheck de `docker-compose.yml`), puis son script de démarrage :

1. applique les migrations de schéma (`scripts/migrate_db.py`) ;
2. crée s'ils n'existent pas le compte `admin`, un « Groupe par défaut » (code `DEMO2024`) et les pages par défaut ;
3. compile les traductions et lance gunicorn.

Sur une instance ouverte au public, générez un nouveau code pour le groupe par défaut, ou supprimez-le.

Les erreurs (clé secrète absente, base injoignable, migration en échec) apparaissent dans `docker compose logs web`.
