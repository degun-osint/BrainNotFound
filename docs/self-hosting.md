# Auto-hébergement

Guide complet pour déployer BrainNotFound sur votre infrastructure.

## Prérequis

- **Docker** et **Docker Compose** (recommandé)
- Ou : Python 3.11+, MySQL 8.0+
- Clé API Anthropic (pour la correction IA)
- 2 Go RAM minimum, 4 Go recommandé

## Installation avec Docker (recommandé)

### 1. Cloner le projet

```bash
git clone https://github.com/degun-osint/brainnotfound
cd brainnotfound
```

### 2. Configurer l'environnement

```bash
cp .env.example .env
```

Éditez `.env` avec vos paramètres :

```env
# Sécurité
SECRET_KEY=votre-cle-secrete-tres-longue-et-aleatoire

# Base de données
DATABASE_URL=mysql+pymysql://quizuser:quizpassword@db/quizdb

# API Anthropic
ANTHROPIC_API_KEY=sk-ant-votre-cle-api

# Email (optionnel)
MAIL_SERVER=smtp.example.com
MAIL_PORT=587
MAIL_USERNAME=noreply@example.com
MAIL_PASSWORD=votre-mot-de-passe
```

### 3. Démarrer les services

```bash
./start.sh
# ou
docker-compose up -d
```

### 4. Accéder à l'application

- URL : http://localhost:5000
- Admin : `admin` / `admin123`

## Installation manuelle

### 1. Base de données MySQL

```sql
CREATE DATABASE quizdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'quizuser'@'%' IDENTIFIED BY 'votre-mot-de-passe';
GRANT ALL PRIVILEGES ON quizdb.* TO 'quizuser'@'%';
FLUSH PRIVILEGES;
```

### 2. Application Python

```bash
# Créer l'environnement virtuel
python3 -m venv venv
source venv/bin/activate

# Installer les dépendances
pip install -r requirements.txt

# Variables d'environnement
export SECRET_KEY="votre-cle-secrete"
export DATABASE_URL="mysql+pymysql://quizuser:password@localhost/quizdb"
export ANTHROPIC_API_KEY="sk-ant-..."

# Initialiser la base de données
flask db upgrade

# Démarrer l'application
gunicorn -w 4 -b 0.0.0.0:5000 wsgi:app
```

## Déploiement en production

### Reverse proxy (Nginx)

```nginx
server {
    listen 80;
    server_name quiz.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl http2;
    server_name quiz.example.com;

    ssl_certificate /etc/letsencrypt/live/quiz.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/quiz.example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket pour les notifications temps réel
    location /socket.io {
        proxy_pass http://127.0.0.1:5000/socket.io;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

### Sécurité en production

1. **HTTPS obligatoire** : Utilisez Let's Encrypt ou un certificat valide
2. **Variables sensibles** : Ne commitez jamais `.env`
3. **Firewall** : N'exposez que les ports 80/443
4. **Mises à jour** : Suivez les releases de sécurité

## Sauvegardes

### Automatiques (FTP)

Les sauvegardes automatiques vers un serveur FTP se configurent depuis l'interface admin :

1. Connectez-vous en tant que super-admin
2. Allez dans **Paramètres** > **Sauvegardes**
3. Configurez le serveur FTP et la fréquence

### Manuelles

```bash
# Backup base de données
docker-compose exec db mysqldump -u quizuser -p quizdb > backup.sql

# Backup fichiers uploadés
tar -czf uploads.tar.gz uploads/
```

### Restauration

```bash
# Restaurer la base
docker-compose exec -T db mysql -u quizuser -p quizdb < backup.sql

# Restaurer les fichiers
tar -xzf uploads.tar.gz
```

## Mise à jour

```bash
# Arrêter les services
docker-compose down

# Récupérer les mises à jour
git pull origin main

# Reconstruire et redémarrer
docker-compose up -d --build

# Appliquer les migrations
docker-compose exec web flask db upgrade
```

## Dépannage

### Les logs

```bash
# Tous les logs
docker-compose logs -f

# Logs de l'application
docker-compose logs -f web

# Logs de la base de données
docker-compose logs -f db
```

### Problèmes courants

| Problème | Solution |
|----------|----------|
| Erreur de connexion DB | Vérifiez DATABASE_URL et que MySQL est démarré |
| Correction IA échoue | Vérifiez ANTHROPIC_API_KEY |
| Emails non envoyés | Vérifiez la configuration SMTP |
| 502 Bad Gateway | Vérifiez que gunicorn est démarré |
