# Guide d'administration

Ce guide couvre la gestion des utilisateurs, quiz et paramètres de la plateforme.

## Rôles utilisateurs

BrainNotFound propose plusieurs niveaux de permissions :

| Rôle | Permissions |
|------|-------------|
| **Super-Admin** | Accès total : toutes les organisations, groupes, utilisateurs et paramètres |
| **Admin Organisation** | Gère une ou plusieurs organisations et leurs groupes |
| **Admin Groupe** | Gère ses groupes assignés uniquement |
| **Utilisateur** | Passe les quiz, consulte ses résultats |

## Gestion des utilisateurs

### Créer un utilisateur

1. Menu **Utilisateurs** > **Nouveau**
2. Remplissez les informations :
   - Prénom, Nom
   - Identifiant (unique)
   - Email
   - Mot de passe
3. Sélectionnez le rôle
4. Assignez à un ou plusieurs groupes
5. Cliquez sur **Créer**

### Import en masse (CSV)

Pour importer plusieurs utilisateurs :

1. **Utilisateurs** > **Import**
2. Format CSV attendu :
   ```csv
   username,email,password,first_name,last_name
   jean.dupont,jean@example.com,MotDePasse123,Jean,Dupont
   marie.martin,marie@example.com,MotDePasse456,Marie,Martin
   ```
3. Sélectionnez le groupe de destination
4. Lancez l'import

### Vérification email

Si la vérification email est activée :
- Les utilisateurs reçoivent un email de confirmation
- Ils doivent cliquer sur le lien pour activer leur compte
- Un admin peut vérifier manuellement un email depuis la page d'édition

## Gestion des quiz

### États d'un quiz

- **Actif** : Visible et accessible aux étudiants
- **Inactif** : Masqué, en cours d'édition

### Options de quiz

| Option | Description |
|--------|-------------|
| **Limite de temps** | Durée maximale pour compléter le quiz (en minutes) |
| **Disponible du/au** | Période pendant laquelle le quiz est accessible |
| **Groupes autorisés** | Restreint l'accès à certains groupes |
| **Sévérité IA** | Niveau d'exigence pour la correction des questions ouvertes |

### Correction manuelle

Après soumission des réponses :

1. Allez dans **Résultats** du quiz
2. Cliquez sur un étudiant
3. Pour chaque question ouverte :
   - Consultez la réponse et le feedback IA
   - Ajustez la note si nécessaire
   - Ajoutez un commentaire personnalisé
4. Sauvegardez

### Duplication de quiz

Pour réutiliser un quiz :
1. Cliquez sur l'icône **Dupliquer**
2. Un nouveau quiz est créé avec le même contenu
3. Modifiez le titre et les paramètres

## Générateur de quiz par IA

BrainNotFound intègre un générateur automatique de quiz qui utilise Claude pour créer des questions à partir de vos supports de cours.

### Accès au générateur

1. Depuis le dashboard, cliquez sur **Generator** (icône étincelles)
2. Ou allez dans **Nouveau** > **Générer avec l'IA**

### Formats de fichiers supportés

| Format | Extension | Description |
|--------|-----------|-------------|
| PDF | `.pdf` | Documents PDF (texte extrait automatiquement) |
| Word | `.docx` | Documents Microsoft Word |
| Markdown | `.md` | Fichiers Markdown |
| Texte | `.txt` | Fichiers texte brut |

### Configuration de la génération

| Paramètre | Description |
|-----------|-------------|
| **Titre** | Nom du quiz qui sera généré |
| **Nombre de QCM** | Quantité de questions à choix multiples (1-20) |
| **Nombre de questions ouvertes** | Quantité de questions à réponse libre (0-10) |
| **Difficulté** | Facile, Modéré ou Difficile |
| **Instructions** | Consignes spécifiques pour l'IA (thèmes à couvrir, style, etc.) |

### Processus de génération

1. **Upload** : Chargez votre support de cours
2. **Configuration** : Définissez les paramètres du quiz
3. **Génération** : Claude analyse le contenu et crée les questions
4. **Prévisualisation** : Vérifiez et modifiez le markdown généré
5. **Création** : Validez pour créer le quiz final

### Bonnes pratiques

- **Contenu structuré** : Les documents avec des titres et sections clairs donnent de meilleurs résultats
- **Longueur optimale** : 5-50 pages pour un équilibre qualité/pertinence
- **Vérification** : Relisez toujours les questions générées avant de publier
- **Instructions précises** : Utilisez le champ instructions pour guider l'IA (ex: "Focus sur les chapitres 3 et 4", "Questions orientées pratique")

### Limites

- Taille maximale du contenu : ~50 000 caractères
- Les images dans les PDF/DOCX ne sont pas analysées
- La qualité dépend de la clarté du support source

## Correction par IA

### Fonctionnement

1. L'étudiant soumet sa réponse
2. Claude (IA d'Anthropic) compare avec la réponse attendue
3. Une note est attribuée avec un feedback détaillé
4. L'enseignant peut ajuster si nécessaire

### Niveaux de sévérité

- **Gentil** : Valorise la compréhension, tolère les approximations
- **Normal** : Équilibre entre précision et pédagogie
- **Strict** : Exige une réponse précise et complète

### Coût API

Chaque correction de question ouverte consomme des tokens :
- ~500-1000 tokens par question (entrée + sortie)
- Voir les tarifs Anthropic pour estimer vos coûts

## Analytics et exports

### Statistiques disponibles

- **Par quiz** : Moyenne, médiane, distribution des notes
- **Par question** : Taux de réussite, réponses les plus fréquentes
- **Par étudiant** : Progression, points forts/faibles

### Export des données

Depuis la page des résultats :
- Export CSV des notes
- Export détaillé avec toutes les réponses

## Paramètres globaux

Accessibles aux super-admins dans **Paramètres** :

### Général
- Nom du site
- Email de contact
- Logo personnalisé

### Sécurité
- Durée des sessions
- Politique de mots de passe
- Vérification email obligatoire

### Sauvegardes
- Fréquence des backups automatiques
- Rétention des sauvegardes
