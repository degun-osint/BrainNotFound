# Guide de creation d'entretien - Assistant IA

Ce guide explique comment remplir le formulaire de creation d'entretien pour generer un personnage coherent et pedagogiquement efficace.

---

## Modes de creation

### Mode Direct
- **Usage** : Quand on a deja un prompt systeme pret
- **Etapes** : Informations de base → Criteres → Prompt
- **Ideal pour** : Dupliquer un entretien existant, importer un prompt externe

### Mode Assiste (Wizard)
- **Usage** : Creation guidee etape par etape
- **Etapes** : Informations → Identite → Scenario → Psychologie → Criteres → Prompt
- **Ideal pour** : Creer un nouveau personnage de zero

---

## Etape 1 : Informations de base

| Champ | Description | Exemple |
|-------|-------------|---------|
| **Titre** * | Nom affiche aux etudiants | "Entretien RPS - Collegue en difficulte" |
| **Description** | Contexte visible avant de commencer | "Simulation d'un echange avec un collegue montrant des signes de souffrance au travail" |
| **Slug** | URL personnalisee (auto-generee si vide) | `rps-collegue-burnout` |
| **Organisation** | Tenant associe (optionnel) | "Master RH 2024" |
| **Groupes** | Restreindre l'acces (vide = tous) | Cocher les groupes concernes |
| **Disponibilite** | Periode d'ouverture | Du 15/01 au 30/01 |

---

## Etape 2 : Identite du personnage

### Nom du personnage
Le prenom et nom du personnage que l'etudiant va rencontrer.
- **Conseil** : Utiliser un nom realiste et neutre
- **Exemple** : "Marie Dupont", "Thomas Martin"

### Role / Fonction
Le poste ou la relation avec l'etudiant dans le scenario.
- **Exemples** :
  - "Collegue developpeur senior"
  - "Candidat au poste de chef de projet"
  - "Patient presentant des symptomes d'anxiete"
  - "Client mecontent du service"

### Contexte professionnel
L'historique et la situation professionnelle du personnage.
- **A inclure** :
  - Anciennete dans l'entreprise/le poste
  - Reputation ou image aupres des collegues
  - Evenements recents pertinents
- **Exemple** :
  > "Travaille dans le meme service depuis 3 ans. Connue pour etre tres impliquee et performante. A recemment pris en charge un projet difficile en plus de ses responsabilites habituelles."

---

## Etape 3 : Situation et scenario

### Ce que l'etudiant sait au depart
Les informations dont dispose l'etudiant AVANT de commencer l'entretien.
- **A inclure** :
  - Observations visibles
  - Rumeurs ou informations de contexte
  - La raison de l'entretien
- **Exemple** :
  > "Vous remarquez que votre collegue Marie semble fatiguee et distante depuis quelques semaines. Elle qui etait toujours souriante arrive maintenant en retard et evite les pauses cafe. Votre manager vous a demande de prendre de ses nouvelles."

### Objectif de l'etudiant
Ce que l'etudiant doit accomplir pendant l'entretien.
- **Formuler clairement** l'objectif pedagogique
- **Exemple** :
  > "Engager une conversation bienveillante pour comprendre la situation de Marie et evaluer si elle a besoin d'aide, tout en respectant ses limites."

---

## Etape 4 : Psychologie du personnage

### Traits de personnalite
Comment le personnage se comporte naturellement.
- **A inclure** :
  - Traits dominants (reserve, extraverti, anxieux...)
  - Mecanismes de defense
  - Evolution possible selon l'approche
- **Exemple** :
  > "Reservee et perfectionniste. A tendance a minimiser ses problemes et a refuser l'aide par fierte. S'ouvre progressivement si elle se sent vraiment ecoutee et non jugee. Peut devenir defensive si elle se sent pressee."

### Ce que le personnage sait / pense
Les informations internes que le personnage possede mais ne revele pas immediatement.
- **A inclure** :
  - La "vraie" situation
  - Les pensees et craintes internes
  - Les informations cachees
- **Exemple** :
  > "Elle sait qu'elle est en situation de burnout mais refuse de l'admettre. Elle a peur de passer pour faible ou incompetente. Elle n'a parle a personne de sa surcharge de travail car elle pense que demander de l'aide serait un aveu d'echec."

### Objectifs caches du personnage
Ce que le personnage espere obtenir de l'echange (consciemment ou non).
- **Exemple** :
  > "Elle aimerait pouvoir en parler mais attend qu'on lui tende la main de maniere bienveillante. Elle cherche une validation que ce qu'elle ressent est legitime, pas des solutions toutes faites."

### Comportements declencheurs
Comment le personnage reagit a differentes approches de l'etudiant.
- **Format recommande** : Trigger → Reaction
- **Exemples** :
  > - "Se braque si on lui donne des conseils non sollicites ou si on minimise ses difficultes"
  > - "S'ouvre si on reformule ses emotions avec empathie"
  > - "Devient defensive si on evoque directement le burnout trop tot"
  > - "Apprecie les questions ouvertes qui lui laissent le controle"
  > - "Se ferme si on insiste trop ou si on fait reference a ce que 'les autres pensent'"

---

## Etape 5 : Criteres d'evaluation

### Templates disponibles

| Template | Usage | Criteres types |
|----------|-------|----------------|
| **RPS** | Risques psychosociaux | Ecoute active, Reformulation, Non-jugement, Orientation |
| **Recrutement** | Entretien d'embauche | Questions pertinentes, Ecoute, Structure, Conclusion |
| **Vente** | Negociation commerciale | Decouverte besoins, Argumentation, Traitement objections |
| **Medical** | Consultation patient | Anamnese, Empathie, Explication, Suivi |

### Structure d'un critere

| Champ | Description |
|-------|-------------|
| **Nom** | Intitule court du critere |
| **Description** | Ce qui est evalue |
| **Points max** | Note maximale (1-20, par pas de 0.5) |
| **Indices** | Elements que l'IA doit chercher dans la conversation |

### Exemple de critere bien defini

```
Nom: Ecoute active
Description: Capacite a ecouter sans interrompre et a montrer qu'on a compris
Points max: 5
Indices: Reformulations, silences respectueux, questions de clarification,
         absence d'interruptions, references aux propos du personnage
```

---

## Etape 6 : Parametres et generation

### Parametres de session

| Parametre | Defaut | Description |
|-----------|--------|-------------|
| **Max interactions** | 30 | Nombre max d'echanges (etudiant + IA) |
| **Duree max** | 30 min | Temps limite de la session |
| **Statut actif** | Oui | L'entretien est-il accessible |
| **L'etudiant peut terminer** | Oui | Bouton "Terminer" disponible |
| **L'IA peut terminer** | Oui | L'IA peut mettre fin si pertinent |

### Qui commence la conversation ?

- **Le personnage (bot)** : Utilise le message d'ouverture - ideal pour initier un contexte
- **L'etudiant** : L'etudiant doit faire le premier pas - teste la prise d'initiative

### Upload de fichier (optionnel)

Permet de demander un document a l'etudiant avant l'entretien (ex: CV pour simulation de recrutement).

| Champ | Exemple |
|-------|---------|
| **Label** | "Votre CV" |
| **Instructions** | "Telechargez votre CV au format PDF. Il servira de base pour l'entretien." |
| **Injection prompt** | `Voici le CV du candidat:\n\n{file_content}\n\nBase tes questions sur ce CV.` |

### Message d'ouverture

Premier message du personnage si c'est lui qui commence.
- **Conseil** : Coherent avec la personnalite et le contexte
- **Exemple** :
  > "*soupir* Ah, salut... Tu voulais me voir ? Desole, je suis un peu debordee la..."

### Prompt systeme

Le prompt complet qui definit le comportement de l'IA. En mode assiste, il est genere automatiquement a partir des informations saisies.

**Structure type du prompt genere** :
1. Role et identite du personnage
2. Contexte de la situation
3. Personnalite et comportements
4. Regles de conversation
5. Objectifs caches
6. Instructions de fin de conversation

---

## Bonnes pratiques

### Pour un personnage realiste

1. **Coherence interne** : La personnalite, les reactions et les objectifs doivent s'aligner
2. **Nuances** : Eviter les personnages trop binaires (tout gentil / tout mechant)
3. **Evolution** : Prevoir comment le personnage change selon l'approche de l'etudiant
4. **Details concrets** : Les petits details rendent le personnage credible

### Pour une evaluation juste

1. **Criteres mesurables** : Des indices concrets pour chaque critere
2. **Equilibre** : Repartir les points selon l'importance pedagogique
3. **Faisabilite** : S'assurer que tous les criteres sont atteignables dans le temps imparti

### Erreurs courantes a eviter

- Personnage trop rigide qui ne reagit pas aux efforts de l'etudiant
- Objectifs contradictoires ou trop nombreux
- Criteres vagues sans indices d'evaluation
- Scenario trop complexe pour le temps imparti
- Message d'ouverture qui revele trop d'informations

---

## Exemples de scenarios types

### RPS - Collegue en burnout
- **Personnage** : Collegue performant qui s'epuise
- **Objectif etudiant** : Detecter les signaux et orienter vers l'aide
- **Difficulte** : Le personnage minimise et refuse l'aide initialement

### Recrutement - Candidat atypique
- **Personnage** : Candidat avec parcours non lineaire
- **Objectif etudiant** : Explorer les competences au-dela du CV
- **Difficulte** : Eviter les biais, poser des questions pertinentes

### Vente - Client hesitant
- **Personnage** : Client interesse mais avec objections
- **Objectif etudiant** : Comprendre les freins et adapter l'argumentaire
- **Difficulte** : Ne pas etre trop pushy, ecouter avant de convaincre

### Medical - Patient anxieux
- **Personnage** : Patient avec symptomes vagues et inquietude
- **Objectif etudiant** : Rassurer tout en faisant une anamnese complete
- **Difficulte** : Equilibrer empathie et rigueur medicale
