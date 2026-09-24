# Premiers pas

Ce guide accompagne la configuration initiale de BrainNotFound : un établissement, un groupe, des apprenants et un premier quiz.

## Connexion administrateur

Au premier démarrage, l'application crée un compte super-administrateur :

- **Identifiant** : `admin`
- **Mot de passe** : la valeur de `ADMIN_DEFAULT_PASSWORD` dans le `.env` (`admin123` si la variable est absente)

> Changez ce mot de passe dès la première connexion, depuis **Mon profil**. Tant que la configuration par défaut est détectée, le tableau de bord affiche un avertissement.

## Choisir le fournisseur d'IA

La correction des questions ouvertes, le générateur de quiz et les entretiens ont besoin d'une IA. Si la clé n'est pas dans le `.env`, renseignez-la dans **Paramètres > Intelligence artificielle**, puis cliquez sur **Tester et lister les modèles**. Voir [Configuration](configuration#intelligence-artificielle).

## Créer un établissement

> Réservé aux super-administrateurs.

1. Menu **Établissements** > **Nouveau**
2. Donnez un nom, et éventuellement un contact et des quotas
3. Enregistrez

Sur une petite instance, un seul établissement suffit. Pour confier sa gestion à quelqu'un, nommez un administrateur d'établissement (voir [Établissements et groupes](groups-tenants#roles)).

## Créer un groupe

Un groupe rassemble des apprenants : une classe, une promotion, une session de formation.

1. Menu **Groupes** > **Nouveau** (ou **Nouveau groupe** depuis la fiche d'un établissement)
2. Renseignez le **nom**, l'**établissement** et, si besoin, un nombre maximum de places
3. Enregistrez

Un **code d'accès** de 8 caractères est généré automatiquement. Il s'affiche sur la page du groupe, avec le lien d'invitation correspondant.

## Inviter des apprenants

Tout se fait depuis la page du groupe (**Groupes** > nom du groupe).

### Code d'accès ou lien d'invitation (recommandé)

Partagez le code, ou le lien d'invitation (`/register?code=CODE`) qui le préremplit. L'apprenant :

1. s'inscrit avec ce code (l'inscription sans code n'est pas possible) ;
2. confirme son adresse email via le lien reçu ;
3. se connecte et retrouve directement les contenus du groupe.

Une personne qui a déjà un compte peut rejoindre un autre groupe avec son code depuis **Mon profil**.

Le bouton **Nouveau code** invalide l'ancien code et l'ancien lien, par exemple en fin de session.

### Création manuelle

**Nouvel apprenant** crée le compte directement dans le groupe. Sans mot de passe, la personne reçoit par email un lien pour choisir le sien (valable 72 heures). Pour un compte sans email réel, copiez ce lien et transmettez-le vous-même.

### Import CSV

**Importer (CSV)** crée plusieurs comptes d'un coup. Le fichier utilise le **point-virgule** comme séparateur ; voir le [format détaillé](admin-guide#import-csv).

### Ajouter une personne existante

Le champ **Ajouter une personne existante** recherche un compte déjà présent dans votre périmètre et l'ajoute au groupe.

## Créer un premier quiz

### Rédaction en Markdown

1. **Quiz** > **Nouveau quiz**
2. Rédigez les questions en Markdown (voir [Syntaxe des quiz](quiz-syntax))
3. Cochez les **groupes** qui y ont accès. Un quiz sans groupe n'est visible par aucun apprenant.
4. Réglez si besoin la limite de temps, la période de disponibilité, la sévérité et le ton de la correction
5. **Créer le quiz**

Un quiz créé est **actif** tout de suite. Pour le masquer le temps de le relire, utilisez **Désactiver** dans la liste des quiz. Une copie faite avec **Dupliquer** est au contraire créée inactive.

### Génération par l'IA

1. **Quiz** > **Generator**, ou **Generator IA** depuis le tableau de bord
2. Envoyez un support de cours (PDF, Word, Markdown ou texte)
3. Choisissez le nombre de QCM, de questions ouvertes et la difficulté
4. Relisez et corrigez le Markdown proposé, puis créez le quiz

Voir le [guide d'administration](admin-guide#generateur-de-quiz-par-ia).

## Exemple de quiz

```markdown
# Quiz d'introduction

## QCM - Quelle est la capitale de la France ? [1 point]
- [ ] Lyon
- [x] Paris
- [ ] Marseille

## OUVERTE - Décrivez le cycle de l'eau [3 points]
### Réponse attendue
Le cycle de l'eau comprend l'évaporation, la condensation,
les précipitations et le ruissellement.
```

## Consulter les résultats

1. Dans la liste des quiz, cliquez sur **Résultats**
2. Consultez les statistiques et la liste des copies
3. Ouvrez une copie pour voir les réponses, ajuster une note ou ajouter un commentaire visible par l'apprenant

La page du groupe donne aussi le taux de réponse du groupe pour chaque contenu, et **Exporter les résultats** en CSV.

## Et ensuite

- [Syntaxe des quiz](quiz-syntax) : toutes les possibilités du format
- [Administration](admin-guide) : utilisateurs, correction, entretiens, paramètres
- [Établissements et groupes](groups-tenants) : rôles, quotas, suppression
