# API

BrainNotFound n'expose pas d'API publique. Cette page décrit les points d'entrée internes utilisés par l'interface, pour qui veut scripter une intégration ou comprendre le fonctionnement. Ils peuvent changer d'une version à l'autre.

## Authentification

Toutes les routes, sauf connexion, inscription et mot de passe oublié, exigent une session ouverte (cookie de session Flask). Les requêtes `POST` exigent un jeton CSRF (`csrf_token` dans le formulaire), que l'interface insère dans chaque page.

Les droits sont vérifiés à chaque requête selon le rôle : une route d'administration renvoie 403 ou redirige si l'objet demandé est hors de votre périmètre.

## Identifiants

Les URL utilisent un identifiant opaque (`uid`) ou, pour les quiz et entretiens, le slug s'il est défini. Les anciens identifiants numériques sont encore acceptés pour les quiz et redirigent vers l'adresse actuelle.

## Principales routes

### Quiz

| Méthode | Route | Rôle |
|---------|-------|------|
| `GET, POST` | `/admin/quiz/create` | Créer un quiz |
| `GET, POST` | `/admin/quiz/<id>/edit` | Modifier |
| `POST` | `/admin/quiz/<id>/toggle` | Activer / désactiver |
| `POST` | `/admin/quiz/<id>/duplicate` | Dupliquer (copie inactive) |
| `POST` | `/admin/quiz/<id>/delete` | Supprimer |
| `POST` | `/admin/quiz/<id>/regrade` | Relancer la correction IA des questions ouvertes |
| `GET` | `/admin/quiz/<id>/export-csv` | Résultats en CSV |
| `GET, POST` | `/admin/quiz/generate` | Générateur IA |
| `POST` | `/admin/quiz/upload-image` | Envoi d'image (voir ci-dessous) |
| `GET, POST` | `/quiz/<id>/take` | Passer un quiz (apprenant) |

### Utilisateurs

| Méthode | Route | Rôle |
|---------|-------|------|
| `GET, POST` | `/admin/user/create` | Créer un compte |
| `GET, POST` | `/admin/user/<id>/edit` | Modifier |
| `POST` | `/admin/user/<id>/delete` | Supprimer |
| `POST` | `/admin/user/<id>/send-reset` | Envoyer le lien de choix du mot de passe |
| `POST` | `/admin/user/<id>/reset-link` | Obtenir ce lien (JSON) sans l'envoyer |
| `GET, POST` | `/admin/users/import` | Import CSV (`csv_file`, `default_group`, `default_password`) |
| `POST` | `/admin/users/bulk-change-group` | Ajout, retrait ou remplacement de groupe en masse |
| `POST` | `/admin/users/bulk-delete` | Suppression en masse |

### Groupes

| Méthode | Route | Rôle |
|---------|-------|------|
| `GET, POST` | `/admin/group/create` | Créer un groupe |
| `GET` | `/admin/group/<id>` | Page du groupe |
| `POST` | `/admin/group/<id>/members/add` | Ajouter une personne existante |
| `POST` | `/admin/group/<id>/members/<user>/role` | Passer intervenant ou apprenant |
| `POST` | `/admin/group/<id>/members/<user>/remove` | Retirer du groupe |
| `POST` | `/admin/group/<id>/regenerate-code` | Nouveau code d'accès |
| `GET` | `/admin/group/<id>/export-results` | Résultats du groupe en CSV |

### Établissements (super-administrateurs)

| Méthode | Route | Rôle |
|---------|-------|------|
| `GET, POST` | `/admin/tenants/create` | Créer |
| `GET, POST` | `/admin/tenants/<id>/edit` | Modifier (quotas, abonnement, alertes) |
| `GET, POST` | `/admin/tenants/<id>/delete` | Supprimer (confirmation par le nom, `confirm_name`) |
| `POST` | `/admin/tenants/<id>/admins/add` | Nommer un administrateur |

### Entretiens

| Méthode | Route | Rôle |
|---------|-------|------|
| `GET, POST` | `/interview/admin/interviews/create` | Créer |
| `GET` | `/interview/admin/interviews/<id>/export` | Résultats en CSV |
| `GET` | `/interview/admin/interviews/<id>/export-json` | Définition de l'entretien en JSON |
| `GET, POST` | `/interview/admin/interviews/import` | Import d'un JSON exporté |
| `GET, POST` | `/interview/<id>/start` | Démarrer une session (apprenant) |

### Paramètres et sauvegardes (super-administrateurs)

| Méthode | Route | Rôle |
|---------|-------|------|
| `GET, POST` | `/admin/settings` | Paramètres du site |
| `POST` | `/admin/settings/ai-models` | Tester la clé et lister les modèles (JSON) |
| `POST` | `/admin/settings/backups/download-now` | Générer et télécharger une sauvegarde |
| `POST` | `/admin/settings/run-backup` | Lancer une sauvegarde (FTP ou serveur) |
| `POST` | `/admin/settings/restore-upload` | Restaurer une archive envoyée (`confirm=RESTAURER`) |

### Données personnelles

| Méthode | Route | Rôle |
|---------|-------|------|
| `GET` | `/profile/export-data` | Export des données du compte connecté |
| `POST` | `/profile/delete-account` | Suppression de son propre compte |

## Envoi d'image

```
POST /admin/quiz/upload-image
Content-Type: multipart/form-data

image=@schema.png
quiz_id=<id du quiz>    (ou "temp" pendant la création)
```

Formats acceptés : PNG, JPG, GIF, WEBP, vérifiés sur le contenu du fichier. Le quota de stockage de l'établissement s'applique. La réponse JSON contient le nom du fichier et le code Markdown à insérer ; en cas d'erreur, un champ `error` et un code 400, 403 ou 413.

Les images sont servies par `/admin/uploads/quiz-<id>/<fichier>`, après contrôle d'accès.

## WebSocket (Socket.IO)

La correction et les entretiens passent par Socket.IO, sur `/socket.io`. À la connexion, un utilisateur authentifié rejoint son salon privé (`user_<id>`) ; les événements lui sont envoyés là.

```javascript
const socket = io();
socket.on('grading_completed', (data) => {
    console.log(data.total_score, '/', data.max_score);
});
```

### Correction d'un quiz

| Événement | Contenu |
|-----------|---------|
| `connected` | `room`, `user_id` |
| `grading_started` | `response_id`, `total` (nombre de questions ouvertes) |
| `grading_progress` | `response_id`, `progress`, `total`, `question_text`, `score`, `max_score` |
| `grading_completed` | `response_id`, `total_score`, `max_score`, `percentage`, `needs_review` |
| `grading_error` | `response_id`, `error` |

`needs_review` vaut `true` quand au moins une réponse est restée « à corriger ».

### Entretiens

Émis par le client :

| Événement | Contenu |
|-----------|---------|
| `join_interview` | `session_id` (session de l'utilisateur connecté uniquement) |
| `send_message` | `session_id`, `content` |
| `leave_interview` | `session_id` |

Émis par le serveur :

| Événement | Contenu |
|-----------|---------|
| `joined_interview` | `session_id` |
| `typing_indicator` | `typing` |
| `message_received` | `session_id`, `content`, `interaction_count`, `max_interactions` |
| `interview_ended` | `session_id`, `reason`, `message` |
| `evaluation_started` | `session_id`, `total_criteria` |
| `evaluation_progress` | `session_id`, `progress`, `total`, `criterion_name`, `score`, `max_score` |
| `evaluation_completed` | `session_id`, `total_score`, `max_score`, `percentage` |
| `evaluation_error` | `session_id`, `error` |
| `error` | `message` |

Les origines autorisées pour les WebSockets sont celles de `ALLOWED_HOSTS` (même origine si vide).

## Limites de débit

Appliquées par adresse IP, sur les requêtes `POST` uniquement :

| Route | Limite |
|-------|--------|
| `/login` | 10 par minute |
| `/register` | 5 par minute |
| `/reset-password/<jeton>` | 5 par minute |
| `/forgot-password` | 3 par minute |
| `/resend-verification` | 3 par minute |

Au-delà, la réponse est un code 429. Il n'y a pas de limite globale : un établissement entier derrière une seule adresse IP n'est pas bloqué.

## Codes d'erreur

| Code | Signification |
|------|---------------|
| 400 | Requête invalide (paramètre manquant, jeton CSRF absent ou expiré) |
| 403 | Hors de votre périmètre, ou hôte absent de `ALLOWED_HOSTS` |
| 404 | Ressource introuvable |
| 413 | Fichier trop volumineux ou quota de stockage atteint |
| 429 | Trop de tentatives (voir ci-dessus) |
| 500 | Erreur serveur (détail dans `docker compose logs web`) |

Une page non authentifiée redirige vers `/login` plutôt que de renvoyer 401.
