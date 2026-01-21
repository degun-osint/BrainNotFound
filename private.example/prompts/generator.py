"""
Quiz generation prompts - Standard prompts for AI quiz generation.
Copy to /private/prompts/generator.py and customize as needed.
"""

QUIZ_FORMAT = """
# Titre du Quiz

Description optionnelle du quiz.

## QCM - Texte de la question [X points]
- [ ] Option incorrecte
- [x] Option correcte
- [ ] Option incorrecte
- [ ] Option incorrecte

## OUVERTE - Texte de la question [X points]
### Reponse attendue
Texte de la reponse modele ici...
"""

DIFFICULTY_INSTRUCTIONS = {
    'facile': """Questions FACILES:
- Testent la comprehension de base
- Reponses evidentes pour qui a lu le cours
- QCM: 1-2 points, Questions ouvertes: 2-3 points""",
    'modere': """Questions MODEREES:
- Testent la comprehension et l'application
- Requierent une reflexion
- QCM: 2 points, Questions ouvertes: 3-4 points""",
    'difficile': """Questions DIFFICILES:
- Testent l'analyse et la synthese
- Requierent une maitrise approfondie
- QCM: 2-3 points, Questions ouvertes: 4-6 points"""
}

GENERATION_PROMPT_TEMPLATE = """Tu es un expert en creation de quiz pedagogiques. Genere un quiz au format Markdown.

**FORMAT:**
{quiz_format}

**REGLES:**
1. Le quiz commence par "# {title}"
2. Genere {num_mcq} questions QCM (commencant par "## QCM - ")
3. Genere {num_open} questions ouvertes (commencant par "## OUVERTE - ")
4. Chaque question a ses points entre crochets: [X points]
5. QCM: 4 options, une seule correcte [x]
6. Questions ouvertes: inclure "### Reponse attendue"
7. Rediger en francais

**DIFFICULTE:**
{difficulty_text}
{custom_instructions}
**CONTENU:**

{content}

**GENERE LE QUIZ:**"""
