# Private Configuration (Community Edition)

Ce dossier contient les configurations par defaut pour la version community de BrainNotFound.

## Structure

```
private.example/
├── landing.html       # Page d'accueil marketing
├── prompts/           # Prompts IA standards
│   ├── grading.py     # Prompts de correction
│   ├── generator.py   # Prompts de generation de quiz
│   └── anomaly.py     # Prompts de detection d'anomalies
└── seed_data/         # Pages par defaut
    ├── a-propos.md    # Page "A propos"
    └── mentions-legales.md  # Mentions legales & confidentialite
```

## Personnalisation

Pour personnaliser les prompts et pages :

1. **Copiez ce dossier vers `private/`**
   ```bash
   cp -r private.example private
   ```

2. **Modifiez les fichiers selon vos besoins**
   - Les prompts dans `private/prompts/` controlent le comportement de l'IA
   - Les pages dans `private/seed_data/` sont utilisees lors de l'initialisation

3. **Redemarrez l'application**
   - L'application utilisera automatiquement les fichiers de `private/`

## Priorite de chargement

L'application charge les templates dans cet ordre :
1. `private/` (prioritaire, non commite)
2. `app/templates/` (fallback par defaut)

Les prompts IA sont charges depuis :
1. `private/prompts/` (prioritaire)
2. `private.example/prompts/` (fallback)

## Page d'accueil (landing.html)

La page d'accueil marketing peut etre personnalisee en modifiant `private/landing.html`.
Elle inclut :
- Hero section avec description du produit
- Grille des fonctionnalites
- Comparaison Community vs SaaS
- Calculateur de prix SaaS interactif
- Liens vers GitHub, documentation, etc.

## Avertissement admin

Si le dossier `private/` n'existe pas, les superadmins verront un avertissement
dans le dashboard les invitant a creer leur configuration personnalisee.

## Fichiers de prompts

### grading.py
- `SEVERITY_INSTRUCTIONS` : Niveaux de severite (gentil, modere, severe)
- `MOOD_DESCRIPTIONS` : Tons du feedback (neutre, jovial, etc.)
- `GRADING_PROMPT_TEMPLATE` : Template principal de correction

### generator.py
- `QUIZ_FORMAT` : Format Markdown attendu pour les quiz
- `DIFFICULTY_INSTRUCTIONS` : Niveaux de difficulte
- `GENERATION_PROMPT_TEMPLATE` : Template de generation

### anomaly.py
- `INDIVIDUAL_ANALYSIS_PROMPT_TEMPLATE` : Analyse individuelle
- `CLASS_ANALYSIS_PROMPT_TEMPLATE` : Analyse de classe
