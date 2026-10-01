"""
Quiz generation prompts - Standard prompts for AI quiz generation.
Copy to /private/prompts/generator.py and customize as needed.

Supports multilingual prompts: 'fr' (French) and 'en' (English).
"""

QUIZ_FORMAT = {
    'fr': """
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
""",
    'en': """
# Quiz Title

Optional quiz description.

## MCQ - Question text [X points]
- [ ] Incorrect option
- [x] Correct option
- [ ] Incorrect option
- [ ] Incorrect option

## OPEN - Question text [X points]
### Expected answer
Model answer text here...
"""
}

DIFFICULTY_INSTRUCTIONS = {
    'fr': {
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
    },
    'en': {
        'facile': """EASY Questions:
- Test basic understanding
- Answers obvious to anyone who read the course
- MCQ: 1-2 points, Open questions: 2-3 points""",
        'modere': """MODERATE Questions:
- Test understanding and application
- Require some thought
- MCQ: 2 points, Open questions: 3-4 points""",
        'difficile': """DIFFICULT Questions:
- Test analysis and synthesis
- Require deep mastery
- MCQ: 2-3 points, Open questions: 4-6 points"""
    }
}

GENERATION_PROMPT_TEMPLATE = {
    'fr': """Tu es un expert en creation de quiz pedagogiques. Genere un quiz au format Markdown.

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

**GENERE LE QUIZ:**""",

    'en': """You are an expert in creating pedagogical quizzes. Generate a quiz in Markdown format.

**FORMAT:**
{quiz_format}

**RULES:**
1. The quiz starts with "# {title}"
2. Generate {num_mcq} MCQ questions (starting with "## MCQ - ")
3. Generate {num_open} open questions (starting with "## OPEN - ")
4. Each question has its points in brackets: [X points]
5. MCQ: 4 options, only one correct [x]
6. Open questions: include "### Expected answer"
7. Write in English

**DIFFICULTY:**
{difficulty_text}
{custom_instructions}
**CONTENT:**

{content}

**GENERATE THE QUIZ:**"""
}

# Regenerating chosen questions of a generated quiz (the instructor keeps the others)
REGENERATION_PROMPT_TEMPLATE = {
    'fr': """Tu es un expert en creation de quiz pedagogiques. Un intervenant relit le quiz "{title}", genere a partir du support de cours ci-dessous, et veut remplacer certaines questions.

**FORMAT:**
{quiz_format}

**QUESTIONS CONSERVEES (ne pas les repeter ni les reformuler):**
{kept}

**QUESTIONS REJETEES PAR L'INTERVENANT (ne pas les reproposer, ni une variante proche):**
{rejected}

**A GENERER:** exactement {count} nouvelle(s) question(s), dans cet ordre :
{requested}

**REGLES:**
1. Chaque question commence par "## QCM - " ou "## OUVERTE - " selon le type demande, avec ses points entre crochets: [X points]
2. QCM: 4 options, une seule correcte [x]
3. Questions ouvertes: inclure "### Reponse attendue"
4. Interroger de preference des notions du support que les questions conservees ne couvrent pas
5. N'ecrire que les questions : pas de titre "# ", pas de commentaire
6. Rediger en francais

**DIFFICULTE:**
{difficulty_text}
{custom_instructions}
**CONTENU:**

{content}

**GENERE LES QUESTIONS:**""",

    'en': """You are an expert in creating pedagogical quizzes. An instructor is reviewing the quiz "{title}", generated from the course material below, and wants to replace some questions.

**FORMAT:**
{quiz_format}

**QUESTIONS KEPT (do not repeat or rephrase them):**
{kept}

**QUESTIONS REJECTED BY THE INSTRUCTOR (do not propose them again, nor a close variant):**
{rejected}

**TO GENERATE:** exactly {count} new question(s), in this order:
{requested}

**RULES:**
1. Each question starts with "## MCQ - " or "## OPEN - " according to the requested type, with its points in brackets: [X points]
2. MCQ: 4 options, only one correct [x]
3. Open questions: include "### Expected answer"
4. Prefer topics of the course that the kept questions do not cover
5. Write only the questions: no "# " title, no comment
6. Write in English

**DIFFICULTY:**
{difficulty_text}
{custom_instructions}
**CONTENT:**

{content}

**GENERATE THE QUESTIONS:**"""
}
