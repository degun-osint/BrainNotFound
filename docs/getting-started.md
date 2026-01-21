# Premiers pas

Ce guide vous accompagne dans la configuration initiale de BrainNotFound.

## Connexion administrateur

Après l'installation, connectez-vous avec les identifiants par défaut :

- **Identifiant** : `admin`
- **Mot de passe** : `admin123`

> **Important** : Changez immédiatement le mot de passe par défaut dans votre profil.

## Créer votre premier groupe

Les groupes permettent d'organiser vos étudiants (par classe, promotion, projet...).

1. Allez dans **Groupes** depuis le menu
2. Cliquez sur **Nouveau groupe**
3. Remplissez :
   - **Nom** : ex. "L3 Informatique 2024"
   - **Description** : optionnel
   - **Code d'accès** : généré automatiquement ou personnalisé
4. Cliquez sur **Créer**

Le **code d'accès** permet aux étudiants de rejoindre le groupe lors de leur inscription.

## Inviter des étudiants

Deux méthodes possibles :

### Option 1 : Code d'accès (recommandé)

Partagez le code d'accès du groupe avec vos étudiants. Ils pourront :
1. S'inscrire sur la plateforme
2. Entrer le code lors de l'inscription
3. Rejoindre automatiquement le groupe

### Option 2 : Import CSV

Pour importer plusieurs utilisateurs :

1. Allez dans **Utilisateurs** > **Import**
2. Préparez un fichier CSV avec les colonnes :
   ```
   username,email,password,first_name,last_name
   ```
3. Sélectionnez le groupe de destination
4. Importez le fichier

## Créer votre premier quiz

### Option 1 : Rédaction manuelle

1. Depuis le **Dashboard**, cliquez sur **Nouveau**
2. Donnez un titre à votre quiz
3. Rédigez vos questions en Markdown (voir [Syntaxe des quiz](quiz-syntax))
4. Configurez les options :
   - **Groupes autorisés** : limitez l'accès à certains groupes
   - **Limite de temps** : optionnel
   - **Période de disponibilité** : optionnel
5. Cliquez sur **Créer**

### Option 2 : Génération par IA

Vous pouvez générer automatiquement un quiz à partir d'un support de cours :

1. Depuis le **Dashboard**, cliquez sur **Generator**
2. Uploadez votre fichier (PDF, Word, Markdown ou texte)
3. Configurez : nombre de QCM, questions ouvertes, difficulté
4. Cliquez sur **Générer**
5. Vérifiez et modifiez le quiz généré
6. Validez pour créer le quiz

> Voir le [Guide d'administration](admin-guide#générateur-de-quiz-par-ia) pour plus de détails sur le générateur.

## Exemple de quiz simple

```markdown
# Quiz d'introduction

## QCM - Quelle est la capitale de la France ? [1 pt]
- [ ] Lyon
- [x] Paris
- [ ] Marseille

## OUVERTE - Décrivez le cycle de l'eau [3 pts]
### Réponse attendue
Le cycle de l'eau comprend l'évaporation, la condensation,
les précipitations et le ruissellement.
```

## Activer le quiz

Par défaut, un nouveau quiz est **inactif**. Pour le rendre disponible :

1. Dans la liste des quiz, cliquez sur l'icône œil
2. Ou modifiez le quiz et cochez "Actif"

## Voir les résultats

Après que les étudiants ont répondu :

1. Cliquez sur l'icône **Résultats** du quiz
2. Consultez les statistiques globales
3. Cliquez sur un étudiant pour voir ses réponses détaillées
4. Ajustez les notes si nécessaire

## Prochaines étapes

- [Syntaxe des quiz](quiz-syntax) : Maîtrisez toutes les possibilités du format Markdown
- [Administration](admin-guide) : Gérez finement les permissions et paramètres
