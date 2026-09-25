# Auto-hébergement

Déployer BrainNotFound sur votre propre serveur.

## Prérequis

- **Docker** avec le plugin **Compose** (recommandé), ou Python 3.13 et MariaDB 11.4 ou plus
- Une clé API d'un fournisseur d'IA : Anthropic par défaut, ou tout service compatible OpenAI (voir [Configuration](configuration#intelligence-artificielle))
- Un serveur SMTP pour les emails (vérification des adresses, liens de mot de passe)

### Ressources

Mesures en charge, avec la configuration fournie :

| Composant | Au repos | En charge |
|-----------|----------|-----------|
| Application (`web`) | ~120 Mo | ~140 Mo, 1 cœur |
| Tâches de fond (`worker`) | ~125 Mo | ~150 Mo |
| Redis | ~12 Mo | ~15 Mo |
| MariaDB (`docker/mariadb/low-memory.cnf`) | ~70 Mo | ~170 Mo |

- **Minimum** : 1 vCPU, 1 Go de RAM, 3 Go de disque (images Docker ~1,3 Go, plus les données).
- **Confortable** : 2 vCPU, 2 Go de RAM.

L'IA tourne chez le fournisseur et ne consomme rien localement, sauf avec un modèle local (Ollama), qui demande sa propre machine.

La configuration de MariaDB fournie limite le cache à 64 Mo : c'est largement assez pour un établissement de plusieurs centaines d'apprenants. Une grosse instance peut relever `innodb_buffer_pool_size` ou retirer ce fichier du `docker-compose.yml`.

## Installation avec Docker (recommandé)

### 1. Récupérer le projet

```bash
git clone https://github.com/degun-osint/brainnotfound
cd brainnotfound
```

### 2. Configurer l'environnement

```bash
cp .env.example .env
```

Dans `.env`, changez au minimum :

- `SECRET_KEY` : `python3 -c "import secrets; print(secrets.token_hex(32))"`
- `MYSQL_ROOT_PASSWORD`, `MYSQL_PASSWORD`, et le mot de passe dans `DATABASE_URL`
- `ADMIN_DEFAULT_PASSWORD`
- la clé API (`ANTHROPIC_API_KEY`), ou laissez-la vide et renseignez-la ensuite dans **Paramètres**
- les variables `MAIL_*`

Toutes les variables sont décrites dans [Configuration](configuration).

### 3. Démarrer

```bash
docker compose up -d --build
```

Au premier démarrage, l'application crée le schéma, le compte `admin` et un « Groupe par défaut » (code `DEMO2024`).

### 4. Se connecter

- En local : `http://localhost:5006`
- Sur un serveur : le port n'écoute que sur `127.0.0.1`, passez par le reverse proxy (voir plus bas), ou mettez `APP_BIND=0.0.0.0` dans le `.env` le temps d'un test
- Identifiant `admin`, mot de passe `ADMIN_DEFAULT_PASSWORD`

Changez ce mot de passe dès la première connexion, et générez un nouveau code pour le groupe par défaut (ou supprimez-le).

## Installation manuelle

### 1. Base de données

```sql
CREATE DATABASE quizdb CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'quizuser'@'localhost' IDENTIFIED BY 'mot-de-passe-base';
GRANT ALL PRIVILEGES ON quizdb.* TO 'quizuser'@'localhost';
FLUSH PRIVILEGES;
```

### 2. Application

```bash
python3.13 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# .env à la racine du projet, ou variables exportées
export SECRET_KEY="..."
export DATABASE_URL="mysql+pymysql://quizuser:mot-de-passe-base@localhost:3306/quizdb"

# Schéma de la base
python -m scripts.migrate_db

# Traductions
pybabel compile -d translations

# Lancement : un seul worker gevent (WebSockets)
gunicorn --bind 127.0.0.1:5000 --workers 1 --worker-class gevent wsgi:app
```

Le compte `admin` et les données par défaut sont créés par `entrypoint.sh` dans l'image Docker ; en installation manuelle, reprenez la partie Python de ce script, ou créez un super-administrateur avec `flask shell`.

Les sauvegardes et restaurations depuis l'interface utilisent `mysqldump` et `mysql` : installez le client MariaDB sur le serveur.

Sans `REDIS_URL`, les corrections, entretiens et emails tournent dans le processus web, comme les tâches périodiques : gardez alors un seul worker gunicorn. Avec Redis, lancez aussi le worker Celery (un seul) :

```bash
celery -A celery_worker worker -P gevent --concurrency 20 --loglevel INFO
```

### Sans Redis ni worker (très petite machine)

Dans `docker-compose.yml`, supprimez les services `redis` et `worker`, retirez `REDIS_URL` et la dépendance à `redis` du service `web`. Tout tourne alors dans le processus web, comme avant la version 2.2 : environ 140 Mo de moins, mais une grosse vague de corrections ralentit les pages.

## Mise en production

### Reverse proxy (Nginx)

```nginx
server {
    listen 80;
    server_name quiz.example.com;
    return 301 https://$server_name$request_uri;
}

server {
    listen 443 ssl;
    http2 on;
    server_name quiz.example.com;

    ssl_certificate /etc/letsencrypt/live/quiz.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/quiz.example.com/privkey.pem;

    # Restauration de sauvegarde depuis le navigateur
    client_max_body_size 2g;

    location / {
        proxy_pass http://127.0.0.1:5006;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # WebSocket (correction et entretiens en temps réel)
    location /socket.io {
        proxy_pass http://127.0.0.1:5006/socket.io;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 3600s;
    }
}
```

En installation manuelle, remplacez le port `5006` par celui de gunicorn (`5000`).

### Sécurité

1. **HTTPS** : certificat Let's Encrypt ou équivalent, puis `SESSION_COOKIE_SECURE=true`.
2. **`ALLOWED_HOSTS`** : votre nom de domaine, pour refuser les requêtes adressées à un autre hôte.
3. **Ports** : seuls 80 et 443 doivent être ouverts. Le `docker-compose.yml` ne publie pas MariaDB et ne publie l'application que sur `127.0.0.1:5006`. Attention : un port publié par Docker contourne ufw, le pare-feu ne le fermerait pas.
4. **Secrets** : le `.env` ne se commite pas et ne se copie pas dans une image. Changez les mots de passe d'exemple.
5. **Mises à jour** : suivez les versions (voir le `CHANGELOG.md`).

## Sauvegardes

### Depuis l'interface

**Paramètres > Sauvegarde et restauration** (super-administrateurs) :

- **Télécharger une sauvegarde** : archive `.tar.gz` avec la base et les fichiers envoyés ;
- **Sauvegardes automatiques** vers un serveur FTP, avec fréquence et durée de conservation ;
- **Restaurer depuis un fichier**, ou depuis l'historique.

Chaque restauration vérifie l'archive, sauvegarde l'état actuel et le remet en place si l'opération échoue. Voir [Administration](admin-guide#sauvegarde-et-restauration).

### En ligne de commande

```bash
# Base de données
docker compose exec db sh -c 'mariadb-dump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction "$MYSQL_DATABASE"' > sauvegarde.sql

# Fichiers envoyés
tar -czf uploads.tar.gz uploads/
```

Restauration :

```bash
docker compose exec -T db sh -c 'mariadb -uroot -p"$MYSQL_ROOT_PASSWORD" "$MYSQL_DATABASE"' < sauvegarde.sql
tar -xzf uploads.tar.gz
docker compose restart web   # applique les migrations si la sauvegarde est plus ancienne
```

## Mise à jour

```bash
# 1. Sauvegarder (Paramètres > Télécharger une sauvegarde), ou :
docker compose exec db sh -c 'mariadb-dump -uroot -p"$MYSQL_ROOT_PASSWORD" --single-transaction "$MYSQL_DATABASE"' > avant-mise-a-jour.sql

# 2. Récupérer la nouvelle version, reconstruire et redémarrer
git pull origin main
docker compose up -d --build
```

Les migrations de schéma s'appliquent seules au démarrage : aucune commande à lancer. Lisez la section « À lire avant de mettre à jour » du `CHANGELOG.md`.

### Avec `deploy.sh`

Depuis le poste de développement : `./deploy.sh`. L'hôte et le dossier se changent par variables : `VPS_HOST=user@serveur VPS_PATH=/chemin ./deploy.sh`. Le script :

1. sauvegarde la base de production sur le serveur, dans `backups/backup_predeploy_<date>.sql.gz` (visible aussi dans **Paramètres**), et s'arrête si la sauvegarde est vide ;
2. synchronise les fichiers (`rsync --delete`) sans jamais envoyer, écraser ni supprimer les `.env*`, `uploads/` et `backups/` du serveur ; l'empreinte des `.env*` est vérifiée avant et après ;
3. après confirmation, reconstruit l'image pendant que le site tourne encore, redémarre et attend que l'application réponde ;
4. si la base redémarre vide (passage à MariaDB), réimporte la sauvegarde de l'étape 1 et applique les migrations.

Un déploiement interrompu peut être relancé : le script reprend la dernière vraie sauvegarde d'avant déploiement.

### Passage de MySQL à MariaDB

Depuis la version 2.0, la base est MariaDB (`mariadb:12.3`, LTS) : plus légère que MySQL (~90 Mo contre ~175 Mo au repos) et entièrement communautaire. MariaDB ne lit pas les fichiers de MySQL : la migration passe par une sauvegarde.

Avec `deploy.sh`, tout est automatique. À la main :

1. **Avant la mise à jour**, sur l'ancienne version : **Paramètres > Télécharger une sauvegarde**.
2. **Mettre à jour** : `git pull` puis `docker compose up -d --build`. MariaDB démarre sur un nouveau volume `mariadb_data`, vide ; l'application y crée le schéma et le compte `admin` (mot de passe `ADMIN_DEFAULT_PASSWORD`).
3. **Se connecter avec `admin`**, puis **Paramètres > Restaurer depuis un fichier** avec la sauvegarde de l'étape 1, en tapant `RESTAURER`. L'application importe la base, applique les migrations, puis vous déconnecte : reconnectez-vous avec vos comptes habituels.

Retour arrière : l'ancien volume `mysql_data` n'est ni modifié ni supprimé. Revenir à la version précédente du dépôt suffit pour le retrouver tel quel. Une fois la migration validée, il peut être supprimé : `docker volume rm <projet>_mysql_data`.

Testé sur une sauvegarde de production (MySQL 8.0 vers MariaDB 12.3) : contenu identique table par table, toutes les pages fonctionnelles.

## Dépannage

### Journaux

```bash
docker compose logs -f          # tout
docker compose logs -f web      # application
docker compose logs -f db       # base de données
docker compose ps               # état et santé des conteneurs
```

### Problèmes courants

| Symptôme | Piste |
|----------|-------|
| Erreur 403 sur toutes les pages | Le nom d'hôte utilisé n'est pas dans `ALLOWED_HOSTS` |
| Impossible de se connecter, sans message d'erreur | `SESSION_COOKIE_SECURE=true` alors que le site est en HTTP |
| Tout le monde est déconnecté à chaque redémarrage | `SECRET_KEY` absente du `.env` |
| `web` ne démarre pas, erreur de base | `DATABASE_URL` et les variables `MYSQL_*` ne concordent pas ; vérifier `docker compose logs db` |
| Réponses ouvertes toutes « à corriger » | Clé API absente ou invalide (**Paramètres > Tester et lister les modèles**), quota de l'établissement atteint ou abonnement expiré |
| Correction lancée mais la page n'avance pas | `docker compose logs worker` : le worker tourne-t-il, reçoit-il la tâche ? Sinon, le reverse proxy ne transmet pas les WebSockets (`/socket.io`) |
| Emails ou récapitulatifs jamais envoyés | `docker compose logs worker` (les emails partent du worker) et variables `MAIL_*` |
| Emails non reçus | Variables `MAIL_*` ; regarder `docker compose logs web` au moment de l'envoi |
| Restauration refusée dès l'envoi | `client_max_body_size` du proxy, ou `BACKUP_MAX_UPLOAD_MB` |
| Site injoignable sur `http://<serveur>:5006` | Normal : le port n'écoute que sur `127.0.0.1`. Passer par le reverse proxy, ou `APP_BIND=0.0.0.0` |
| 502 Bad Gateway | L'application ne tourne pas ou redémarre : `docker compose ps` et `docker compose logs web` |
| Erreur 429 | Trop de tentatives de connexion ou d'inscription depuis la même adresse ; attendre une minute |
