# Configuration

Toutes les options de configuration de BrainNotFound.

## Variables d'environnement

### Obligatoires

| Variable | Description | Exemple |
|----------|-------------|---------|
| `SECRET_KEY` | Clé secrète Flask (sessions, CSRF) | Chaîne aléatoire de 32+ caractères |
| `DATABASE_URL` | URL de connexion MySQL | `mysql+pymysql://user:pass@host/db` |
| `ANTHROPIC_API_KEY` | Clé API Anthropic pour la correction IA | `sk-ant-...` |

### Optionnelles

#### Application

| Variable | Description | Défaut |
|----------|-------------|--------|
| `FLASK_ENV` | Environnement (development/production) | `production` |
| `CLAUDE_MODEL` | Modèle Claude à utiliser | `claude-sonnet-4-20250514` |
| `ALLOWED_HOSTS` | Domaines autorisés (séparés par virgule) | Tous |

#### Sessions et sécurité

| Variable | Description | Défaut |
|----------|-------------|--------|
| `SESSION_COOKIE_SECURE` | Cookies HTTPS uniquement | `false` |
| `SESSION_COOKIE_HTTPONLY` | Cookies non accessibles en JS | `true` |
| `PERMANENT_SESSION_LIFETIME` | Durée des sessions (secondes) | `3600` (1 heure) |

#### Email

| Variable | Description | Défaut |
|----------|-------------|--------|
| `MAIL_SERVER` | Serveur SMTP | - |
| `MAIL_PORT` | Port SMTP | `587` |
| `MAIL_USE_TLS` | Utiliser TLS | `true` |
| `MAIL_USERNAME` | Utilisateur SMTP | - |
| `MAIL_PASSWORD` | Mot de passe SMTP | - |
| `MAIL_DEFAULT_SENDER` | Expéditeur par défaut | `MAIL_USERNAME` |

## Fichier .env

Exemple complet :

```env
# === Application ===
SECRET_KEY=votre-cle-secrete-32-caracteres-minimum
FLASK_ENV=production

# === Base de données ===
DATABASE_URL=mysql+pymysql://quizuser:quizpassword@db/quizdb

# === API Anthropic ===
ANTHROPIC_API_KEY=sk-ant-api03-...
CLAUDE_MODEL=claude-sonnet-4-20250514

# === Sécurité ===
ALLOWED_HOSTS=quiz.example.com,www.quiz.example.com
SESSION_COOKIE_SECURE=true

# === Email ===
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=noreply@example.com
MAIL_PASSWORD=mot-de-passe-smtp
MAIL_DEFAULT_SENDER=BrainNotFound <noreply@example.com>
```

## Paramètres en base de données

Certains paramètres sont stockés en base et modifiables depuis l'interface admin (**Paramètres**) :

### Paramètres du site

- **Nom du site** : Affiché dans la navbar et les emails
- **Email de contact** : Pour les notifications administrateur
- **Logo** : Image personnalisée (optionnel)

### Paramètres de sécurité

- **Vérification email** : Obliger la vérification des emails
- **Expiration des invitations** : Durée de validité des codes d'accès

### Sauvegardes automatiques (FTP)

Les sauvegardes sont configurées depuis l'interface admin, pas via des variables d'environnement :

| Paramètre | Description |
|-----------|-------------|
| **FTP activé** | Active/désactive les backups automatiques |
| **Serveur FTP** | Adresse du serveur de sauvegarde |
| **Fréquence** | Horaire, quotidien ou hebdomadaire |
| **Heure** | Heure d'exécution (0-23) |
| **Jour** | Jour de la semaine (pour les backups hebdomadaires) |

## Modèles Claude

Modèles disponibles pour la correction IA :

| Modèle | Description | Coût relatif |
|--------|-------------|--------------|
| `claude-sonnet-4-20250514` | Équilibre performance/coût (recommandé) | Moyen |
| `claude-opus-4-20250514` | Meilleure qualité | Élevé |
| `claude-3-haiku-20240307` | Rapide et économique | Faible |

Configurez via `CLAUDE_MODEL` dans `.env`.

## Docker Compose

### Variables d'environnement Docker

Le fichier `docker-compose.yml` utilise les variables de `.env` :

```yaml
services:
  web:
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - DATABASE_URL=${DATABASE_URL}
      - ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}
```

### Volumes

| Volume | Usage |
|--------|-------|
| `db_data` | Données MySQL persistantes |
| `./uploads` | Fichiers uploadés (images quiz) |
| `./backups` | Sauvegardes automatiques |

### Ports

| Port | Service | Production |
|------|---------|------------|
| `5000` | Application Flask | Via reverse proxy |
| `3306` | MySQL | Non exposé |

## Génération de SECRET_KEY

```bash
# Python
python -c "import secrets; print(secrets.token_hex(32))"

# OpenSSL
openssl rand -hex 32

# /dev/urandom
head -c 32 /dev/urandom | xxd -p
```

## Validation de la configuration

Au démarrage, l'application vérifie :

1. `SECRET_KEY` est définie et suffisamment longue
2. `DATABASE_URL` est valide et la connexion fonctionne
3. `ANTHROPIC_API_KEY` est définie (warning si absente)

Les erreurs de configuration sont affichées dans les logs.
