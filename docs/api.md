# API

BrainNotFound n'expose pas d'API REST publique pour le moment. Cette page documente les endpoints internes utilisés par l'interface.

## Authentification

Toutes les requêtes nécessitent une session Flask authentifiée. Les tokens CSRF sont requis pour les requêtes POST/PUT/DELETE.

## Endpoints internes

### Quiz

#### Créer un quiz
```
POST /admin/create
Content-Type: application/x-www-form-urlencoded

title=Mon%20Quiz&content=...&is_active=on
```

#### Modifier un quiz
```
POST /admin/quiz/<id>/edit
Content-Type: application/x-www-form-urlencoded

title=Mon%20Quiz&content=...
```

#### Supprimer un quiz
```
POST /admin/quiz/<id>/delete
```

### Utilisateurs

#### Créer un utilisateur
```
POST /admin/users/create
Content-Type: application/x-www-form-urlencoded

username=jean&email=jean@example.com&password=...
```

#### Import CSV
```
POST /admin/users/import
Content-Type: multipart/form-data

file=@users.csv&group_id=1
```

### Groupes

#### Créer un groupe
```
POST /admin/groups/create
Content-Type: application/x-www-form-urlencoded

name=L3%20Info&tenant_id=1
```

### Images

#### Upload d'image pour quiz
```
POST /admin/upload-image
Content-Type: multipart/form-data

image=@schema.png&quiz_id=1
```

Réponse :
```json
{
  "success": true,
  "filename": "abc123_schema.png",
  "markdown": "![](abc123_schema.png)"
}
```

#### Récupérer une image
```
GET /admin/quiz/<quiz_id>/images/<filename>
```

## WebSocket

BrainNotFound utilise Socket.IO pour les fonctionnalités temps réel.

### Événements serveur → client

| Événement | Description | Payload |
|-----------|-------------|---------|
| `grading_complete` | Correction IA terminée | `{response_id, score, feedback}` |
| `new_submission` | Nouvelle soumission de quiz | `{quiz_id, user_id}` |

### Connexion

```javascript
const socket = io();

socket.on('grading_complete', (data) => {
    console.log('Correction terminée:', data);
});
```

## Intégration externe

### Webhooks (à venir)

Fonctionnalité prévue pour notifier des systèmes externes :
- Nouvelle inscription
- Quiz soumis
- Correction terminée

### API REST (à venir)

Une API REST complète est prévue pour :
- Intégration LMS (Moodle, Canvas...)
- Applications mobiles
- Automatisation

## Export de données

### Export CSV des résultats

```
GET /admin/quiz/<id>/export
```

Retourne un fichier CSV avec :
- Nom de l'utilisateur
- Date de soumission
- Score par question
- Score total

### Export détaillé

```
GET /admin/quiz/<id>/export?detailed=true
```

Inclut également :
- Réponses de l'utilisateur
- Feedback IA
- Temps passé

## Limites de taux

| Endpoint | Limite |
|----------|--------|
| Login | 5 tentatives / minute |
| Register | 3 inscriptions / heure / IP |
| API interne | 200 requêtes / jour |

Les limites sont configurables via Flask-Limiter.

## Codes d'erreur

| Code | Description |
|------|-------------|
| 400 | Requête invalide (paramètres manquants) |
| 401 | Non authentifié |
| 403 | Accès refusé (permissions insuffisantes) |
| 404 | Ressource non trouvée |
| 429 | Trop de requêtes (rate limit) |
| 500 | Erreur serveur |

## CORS

Par défaut, CORS est désactivé (same-origin uniquement). Pour les WebSockets, les origines autorisées sont définies via `ALLOWED_HOSTS`.
