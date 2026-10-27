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
| **Titre** * | Nom affiche aux apprenants | "Entretien RPS - Collegue en difficulte" |
| **Description** | Contexte visible avant de commencer | "Simulation d'un echange avec un collegue montrant des signes de souffrance au travail" |
| **Slug** | URL personnalisee (auto-generee si vide) | `rps-collegue-burnout` |
| **Etablissement** | Etablissement de rattachement (quotas) | "Master RH 2024" |
| **Groupes** | Groupes qui voient l'entretien (vide = visible par personne) | Cocher les groupes concernes |
| **Disponibilite** | Periode d'ouverture | Du 15/01 au 30/01 |

---

## Etape 2 : Identite du personnage

### Nom du personnage
Le prenom et nom du personnage que l'apprenant va rencontrer.
- **Conseil** : Utiliser un nom realiste et neutre
- **Exemple** : "Marie Dupont", "Thomas Martin"

### Role / Fonction
Le poste ou la relation avec l'apprenant dans le scenario.
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

### Ce que l'apprenant sait au depart
Les informations dont dispose l'apprenant AVANT de commencer l'entretien.
- **A inclure** :
  - Observations visibles
  - Rumeurs ou informations de contexte
  - La raison de l'entretien
- **Exemple** :
  > "Vous remarquez que votre collegue Marie semble fatiguee et distante depuis quelques semaines. Elle qui etait toujours souriante arrive maintenant en retard et evite les pauses cafe. Votre manager vous a demande de prendre de ses nouvelles."

### Objectif de l'apprenant
Ce que l'apprenant doit accomplir pendant l'entretien.
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
Comment le personnage reagit a differentes approches de l'apprenant.
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
| **Max interactions** | 30 | Nombre max d'echanges (apprenant + IA) |
| **Duree max** | 30 min | Temps limite de la session |
| **Statut actif** | Oui | L'entretien est-il accessible |
| **L'apprenant peut terminer** | Oui | Bouton "Terminer" disponible |
| **L'IA peut terminer** | Oui | L'IA peut mettre fin si pertinent |

### Qui commence la conversation ?

- **Le personnage (bot)** : Utilise le message d'ouverture - ideal pour initier un contexte
- **L'apprenant** : L'apprenant doit faire le premier pas - teste la prise d'initiative

### Lecture vocale (optionnel)

Les reponses du personnage peuvent etre lues a voix haute. Deux sources possibles, selon ce
qui est configure dans **Parametres du site > Synthese vocale** :

- **Aucun fournisseur (par defaut)** : la synthese se fait dans le navigateur de
  l'apprenant. Rien ne quitte l'installation, rien n'est facture, mais la qualite depend de
  son systeme (tres bonne sur macOS et iOS, plus mecanique sur Windows en francais).
- **Un fournisseur configure** : le texte de la reponse est envoye au fournisseur, qui
  renvoie l'audio. Meme voix pour tous les apprenants, facturee aux caracteres. L'audio est
  mis en cache sur le serveur (par contenu, jamais inclus dans les sauvegardes) et le
  navigateur reprend la main si le fournisseur est indisponible.

| Mode | Effet |
|------|-------|
| **Proposee a l'apprenant** | Un bouton haut-parleur dans l'entretien ; le choix de l'apprenant est retenu pour ses entretiens suivants |
| **Activee par defaut** | La voix demarre activee : a reserver aux entretiens ou l'oral fait partie de l'exercice |
| **Desactivee** | Aucun bouton, aucune lecture |

Quatre reglages, dans cet ordre :

| Reglage | Role |
|---------|------|
| **Lecture** | Proposee a l'apprenant / Activee par defaut / Desactivee |
| **Moteur** | La voix du navigateur de l'apprenant, ou celle du fournisseur configure |
| **Voix** | Liste remplie automatiquement selon le moteur choisi ; « Automatique » convient dans la plupart des cas |
| **Vitesse** | De 0,5 (lent) a 1,5 (rapide) |

Le **moteur** merite une seconde de reflexion. Avec un fournisseur configure, il est choisi
par defaut : meme voix pour tous les apprenants, meilleure qualite, facturee aux caracteres.
Choisir le navigateur garde l'entretien **gratuit**, ce qui est pertinent pour un entretien
a fort volume ou peu sensible a la qualite de la voix.

Les deux moteurs ne parlent pas le meme langage — `Thomas` est une voix installee sur une
machine, `nova` un identifiant chez un fournisseur — mais vous n'avez plus a le savoir : la
liste se remplit toute seule. Votre choix est retenu **pour chaque moteur**, donc basculer
de l'un a l'autre ne perd rien.

Une limite a connaitre pour le moteur navigateur : la liste affiche les voix installees sur
**votre** machine, celle de l'apprenant peut en avoir d'autres. « Automatique » evite le
probleme en prenant la voix de la langue de l'interface.

- Les didascalies entre asterisques (`*elle consulte votre CV*`) ne sont pas lues : elles
  deviennent une pause.
- L'historique n'est jamais lu a l'ouverture de la page ; l'apprenant peut reecouter un
  message avec le bouton de sa bulle.

### Saisie vocale de l'apprenant (optionnel)

Permet a l'apprenant de **dicter** ses reponses au lieu de les taper. Desactive par
defaut : la voix de l'apprenant est envoyee a un service de transcription externe, ce qui
se dit et se consent, pas s'active discretement.

Necessite un fournisseur configure dans **Parametres du site > Saisie vocale des
apprenants** (Whisper chez OpenAI, ou un serveur local type faster-whisper).

Comment ca se passe pour l'apprenant :

1. Un bouton micro apparait a cote du champ de saisie. **Taper reste toujours
   possible** : la dictee est un confort, jamais une obligation.
2. Au premier clic, un encart explique que sa voix sera transmise pour transcription et
   lui demande son accord. S'il refuse, il tape, et on ne lui redemande rien.
3. L'accord est enregistre **une fois par entretien**, avec sa date.
4. Il parle, puis reclique pour arreter (3 minutes maximum par enregistrement).
5. Le texte reconnu **s'affiche dans le champ de saisie** : il le relit, le corrige si la
   transcription a mal entendu, et envoie quand il veut.

Ce que vous voyez, vous : dans la relecture d'une session, les reponses dictees portent la
mention **dictee**. C'est important — une transcription se trompe, et une maladresse
apparente peut venir de la machine et non de l'apprenant.

**L'enregistrement audio n'est jamais conserve**, ni sur le serveur ni ailleurs. Il est
transcrit en memoire puis jete ; seul le texte que l'apprenant choisit d'envoyer est
enregistre, dans son message.

### Upload de fichier (optionnel)

Permet de demander un document a l'apprenant avant l'entretien (ex: CV pour simulation de recrutement).

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
3. **Evolution** : Prevoir comment le personnage change selon l'approche de l'apprenant
4. **Details concrets** : Les petits details rendent le personnage credible

### Pour une evaluation juste

1. **Criteres mesurables** : Des indices concrets pour chaque critere
2. **Equilibre** : Repartir les points selon l'importance pedagogique
3. **Faisabilite** : S'assurer que tous les criteres sont atteignables dans le temps imparti

### Erreurs courantes a eviter

- Personnage trop rigide qui ne reagit pas aux efforts de l'apprenant
- Objectifs contradictoires ou trop nombreux
- Criteres vagues sans indices d'evaluation
- Scenario trop complexe pour le temps imparti
- Message d'ouverture qui revele trop d'informations

---

## Exemples de scenarios types

### RPS - Collegue en burnout
- **Personnage** : Collegue performant qui s'epuise
- **Objectif apprenant** : Detecter les signaux et orienter vers l'aide
- **Difficulte** : Le personnage minimise et refuse l'aide initialement

### Recrutement - Candidat atypique
- **Personnage** : Candidat avec parcours non lineaire
- **Objectif apprenant** : Explorer les competences au-dela du CV
- **Difficulte** : Eviter les biais, poser des questions pertinentes

### Vente - Client hesitant
- **Personnage** : Client interesse mais avec objections
- **Objectif apprenant** : Comprendre les freins et adapter l'argumentaire
- **Difficulte** : Ne pas etre trop pushy, ecouter avant de convaincre

### Medical - Patient anxieux
- **Personnage** : Patient avec symptomes vagues et inquietude
- **Objectif apprenant** : Rassurer tout en faisant une anamnese complete
- **Difficulte** : Equilibrer empathie et rigueur medicale
