# Groupes et Organisations

BrainNotFound propose une architecture multi-organisations pour gérer plusieurs entités sur une seule instance.

## Concepts

### Organisation

Une **organisation** représente une entité indépendante :
- Une école
- Une entreprise
- Un département
- Une formation

Chaque organisation a ses propres :
- Groupes
- Utilisateurs
- Quiz (via les groupes)

### Groupe

Un **groupe** rassemble des utilisateurs au sein d'une organisation :
- Une classe
- Une promotion
- Un projet
- Une équipe

Les quiz sont assignés à des groupes pour contrôler l'accès.

## Hiérarchie

```
Instance BrainNotFound
├── Organisation A (École Alpha)
│   ├── Groupe L1 Info
│   │   ├── Étudiant 1
│   │   └── Étudiant 2
│   ├── Groupe L2 Info
│   └── Groupe L3 Info
├── Organisation B (Entreprise Beta)
│   ├── Groupe Formation Sécurité
│   └── Groupe Formation Dev
└── (Sans organisation)
    └── Groupe Test
```

## Gestion des organisations

> Réservé aux **super-administrateurs**

### Créer une organisation

1. Menu **Organisations** > **Nouveau**
2. Remplissez :
   - **Nom** : identifiant de l'organisation
   - **Description** : optionnel
3. Cliquez sur **Créer**

### Assigner un admin d'organisation

1. **Utilisateurs** > Modifier l'utilisateur
2. Cochez **Administrateur d'organisation**
3. Sélectionnez les organisations à administrer
4. Sauvegardez

L'admin d'organisation pourra :
- Gérer les groupes de ses organisations
- Gérer les utilisateurs de ses organisations
- Créer des quiz pour ses organisations

## Gestion des groupes

### Créer un groupe

1. Menu **Groupes** > **Nouveau**
2. Remplissez :
   - **Nom** : nom du groupe
   - **Description** : optionnel
   - **Organisation** : sélectionnez l'organisation parente
   - **Code d'accès** : généré ou personnalisé
3. Cliquez sur **Créer**

### Code d'accès

Le code permet aux utilisateurs de rejoindre un groupe :
- Lors de l'inscription
- Depuis leur profil

Format recommandé : 6-8 caractères alphanumériques majuscules.

### Admin de groupe

Un utilisateur peut être **admin d'un groupe** sans être admin de toute l'organisation :
1. Modifiez l'utilisateur
2. Cochez **Administrateur de groupe**
3. Sélectionnez les groupes à administrer

## Filtrage par contexte

### Sélecteur d'organisation (navbar)

Les admins multi-organisations voient un sélecteur dans la barre de navigation :
- **Toutes les organisations** : Vue globale
- **Organisation X** : Filtre sur cette organisation uniquement

Ce filtre s'applique à :
- La liste des quiz
- La liste des utilisateurs
- La liste des groupes

### Filtres dans les listes

Chaque liste propose des filtres :
- Par organisation
- Par groupe
- Par recherche texte

## Bonnes pratiques

### Organisation

1. **Une organisation par entité** : École, entreprise, département
2. **Un groupe par cohorte** : Classe, promotion, projet
3. **Nommage cohérent** : `L3-Info-2024`, `Formation-Cyber-Q1`

### Permissions

1. **Principe du moindre privilège** :
   - Super-admin uniquement pour la gestion globale
   - Admin d'organisation pour la gestion quotidienne
   - Admin groupe pour les enseignants

2. **Séparation des données** :
   - Les utilisateurs d'une organisation ne voient pas les autres organisations
   - Les quiz sont isolés par groupe

### Migration

Pour déplacer des utilisateurs entre groupes :
1. Modifiez chaque utilisateur
2. Changez les groupes assignés
3. Ou utilisez l'import CSV avec les nouveaux groupes

## Quotas et limites

> Réservé aux **super-administrateurs**

### Limites configurables

Chaque organisation peut avoir des limites :

| Limite | Description |
|--------|-------------|
| **Max utilisateurs** | Nombre maximum d'utilisateurs dans l'organisation |
| **Max quiz** | Nombre maximum de quiz actifs |
| **Max groupes** | Nombre maximum de groupes |
| **Corrections IA / mois** | Nombre de corrections de questions ouvertes |
| **Générations quiz / mois** | Nombre de quiz générés par IA |
| **Analyses classe / mois** | Nombre d'analyses de classe IA |
| **Entretiens IA / mois** | Nombre d'entretiens conversationnels |

Une valeur de **0** signifie **illimité**.

### Alertes quota

Activez les alertes pour être prévenu quand un quota est presque atteint :

1. **Organisations** > Modifier l'organisation
2. Section **Alertes quota**
3. Cochez **Activer les alertes quota**
4. Définissez le **seuil** (défaut : 10%)
5. Assurez-vous qu'une **adresse de contact** est configurée

Quand un quota atteint le seuil configuré :
- Un email est envoyé à l'adresse de contact
- L'email liste tous les quotas critiques
- Une seule alerte est envoyée par mois

### Abonnement

Vous pouvez définir une **date d'expiration** pour l'organisation :
- Après expiration, les utilisateurs ne peuvent plus accéder aux quiz
- Les admins reçoivent un avertissement dans l'interface
- Laisser vide pour un abonnement sans expiration
