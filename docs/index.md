# BrainNotFound

Bienvenue dans la documentation de **BrainNotFound**, la plateforme d'évaluation avec correction par IA, pour les écoles comme pour la formation en entreprise.

## Qu'est-ce que BrainNotFound ?

BrainNotFound est une application web open source qui permet aux intervenants de :

- **créer des quiz en Markdown**, un format simple et lisible, ou de les faire générer par l'IA à partir d'un support de cours ;
- **corriger automatiquement** : les QCM sont notés immédiatement, les questions ouvertes sont évaluées par l'IA avec un retour personnalisé ;
- **faire passer des entretiens simulés** avec un personnage joué par l'IA, évalués sur une grille de critères ;
- **suivre les résultats** d'un groupe et repérer les notions mal comprises ;
- **gérer plusieurs établissements** (écoles, entreprises, services) sur une seule instance.

## Vocabulaire

| Terme | Sens |
|-------|------|
| **Établissement** | Une entité indépendante : école, entreprise, service, organisme de formation. |
| **Groupe** | Une classe, une promotion, une session de formation, une équipe. Il appartient à un établissement. |
| **Intervenant** | Enseignant, formateur ou tuteur : il gère les groupes où il a ce rôle. |
| **Apprenant** | Élève, étudiant ou stagiaire : il passe les quiz et entretiens de ses groupes. |

## Fonctionnalités principales

| Fonctionnalité | Description |
|----------------|-------------|
| Quiz Markdown | Création de quiz avec une syntaxe simple |
| Générateur IA | Quiz générés à partir d'un PDF, d'un document Word ou d'un texte |
| Correction IA | Questions ouvertes évaluées avec un retour personnalisé, copies « à corriger » si l'IA ne peut pas noter |
| Entretiens IA | Conversations avec un personnage IA pour évaluer les compétences relationnelles |
| Établissements et groupes | Plusieurs établissements par instance, rôles attribués groupe par groupe |
| Quotas | Limites par établissement (utilisateurs, groupes, quiz, usage de l'IA, abonnement) |
| Planification | Limite de temps, période de disponibilité, mode examen |
| Fournisseur d'IA au choix | Claude par défaut, ou tout service compatible OpenAI, réglable sans redémarrage |
| Sauvegardes | Téléchargement, envoi FTP planifié, restauration depuis l'interface |
| Multilingue | Interface et retours de l'IA en français et en anglais |

## Versions disponibles

### Community (gratuite)

- Auto-hébergement sur votre infrastructure
- Code source ouvert (GPL v3)
- Toutes les fonctionnalités
- Correction IA sans limite, avec votre propre clé API
- Support communautaire via GitHub

### SaaS (sur devis)

- Hébergement et maintenance inclus
- Correction IA incluse, sans clé API à fournir
- Support prioritaire
- Mises à jour automatiques

## Par où commencer

1. [Premiers pas](getting-started) : créer un établissement, un groupe et un premier quiz
2. [Syntaxe des quiz](quiz-syntax) : écrire un quiz en Markdown
3. [Administration](admin-guide) : utilisateurs, quiz, entretiens, paramètres
4. [Établissements et groupes](groups-tenants) : rôles, invitations, quotas
5. [Auto-hébergement](self-hosting) : installer et mettre à jour l'application

## Besoin d'aide ?

- **GitHub** : [signaler un bug ou proposer une amélioration](https://github.com/degun-osint/brainnotfound)
- **Contact** : pour la version SaaS, contactez-nous
