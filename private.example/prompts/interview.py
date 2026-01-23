"""
Interview prompts - Templates for conversational AI interviews.
Copy to /private/prompts/interview.py and customize as needed.
"""

# Template to generate a system prompt from wizard data
PROMPT_GENERATOR_TEMPLATE = """Tu es un expert en creation de scenarios pedagogiques pour des jeux de role educatifs.

A partir des informations suivantes, genere un system prompt complet pour un assistant IA qui jouera le role d'un personnage dans un entretien simule.

**INFORMATIONS DU PERSONNAGE:**
Nom: {persona_name}
Role: {persona_role}
Contexte: {persona_context}

**PERSONNALITE:**
{persona_personality}

**CE QUE LE PERSONNAGE SAIT:**
{persona_knowledge}

**OBJECTIFS CACHES DU PERSONNAGE:**
{persona_objectives}

**COMPORTEMENTS DECLENCHEURS:**
{persona_triggers}

**CONTEXTE POUR L'ETUDIANT:**
{student_context}

**OBJECTIF DE L'ETUDIANT:**
{student_objective}

**CRITERES D'EVALUATION (pour reference):**
{criteria_list}

---

Genere un system prompt detaille qui:
1. Definit clairement l'identite et le contexte du personnage
2. Etablit ses traits de personnalite et comportements
3. Specifie comment il doit reagir aux differentes approches
4. Inclut des exemples de phrases typiques du personnage
5. Precise les sujets sensibles et comment les aborder
6. Est redige en francais et adapte a un contexte educatif

IMPORTANT: Le prompt doit etre autonome et directement utilisable. Ne mentionne JAMAIS qu'il s'agit d'un exercice ou d'une simulation dans le prompt genere.

Genere UNIQUEMENT le system prompt, sans introduction ni explication."""

# Wrapper for conversation - adds rules and end signal detection
CONVERSATION_WRAPPER = """{system_prompt}

---

REGLES IMPERATIVES:
1. Tu incarnes TOUJOURS ce personnage. Ne brise JAMAIS l'immersion.
2. Ne revele JAMAIS que tu es une IA ou que c'est un exercice.
3. Tes reponses doivent etre naturelles et conversationnelles (2-4 phrases en general, parfois plus si necessaire).
4. Adapte ton langage au personnage (registre, expressions, hesitations...).
5. Reagis de maniere coherente avec ta personnalite et ton etat emotionnel.

SIGNAL DE FIN:
Si la conversation atteint une conclusion naturelle (resolution, impasse claire, ou l'interlocuteur met fin a l'echange), termine ta derniere reponse par le marqueur exact:
[INTERVIEW_COMPLETE]

Ce marqueur indique que l'entretien peut se terminer. Ne l'utilise que si c'est vraiment pertinent."""

# Evaluation template for multi-criteria assessment
EVALUATION_TEMPLATE = """Tu es un evaluateur pedagogique expert. Analyse la transcription d'un entretien simule et evalue l'etudiant selon les criteres donnes.

**CONTEXTE DE L'ENTRETIEN:**
Titre: {interview_title}
Description: {interview_description}
Objectif de l'etudiant: {student_objective}

**PERSONNAGE:**
{persona_name} - {persona_role}

**TRANSCRIPTION COMPLETE:**
{conversation_transcript}

**CRITERES D'EVALUATION:**
{criteria_json}

---

Pour chaque critere, tu dois:
1. Analyser les comportements pertinents dans la conversation
2. Identifier les points forts et axes d'amelioration
3. Attribuer un score juste et argumente

Reponds UNIQUEMENT au format JSON suivant:
{{
    "scores": [
        {{
            "criterion_id": <id du critere>,
            "criterion_name": "<nom du critere>",
            "score": <float entre 0 et max_points>,
            "max_score": <max_points du critere>,
            "feedback": "<explication detaillee en 2-3 phrases>"
        }}
    ],
    "summary": "<synthese globale de la performance: points forts, points a ameliorer, conseils pour progresser (3-5 phrases)>",
    "total_score": <somme des scores>,
    "max_total": <somme des max_scores>
}}"""

# Template for opening message generation
OPENING_MESSAGE_TEMPLATE = """Tu incarnes le personnage suivant:

{system_prompt}

Genere le premier message de ce personnage pour demarrer la conversation. Ce message doit:
1. Etre naturel et en accord avec la personnalite du personnage
2. Poser le contexte de l'echange sans etre trop explicite
3. Inviter implicitement l'interlocuteur a reagir
4. Faire 2-4 phrases maximum

Reponds UNIQUEMENT avec le message du personnage, sans guillemets ni indication de role."""

# Predefined evaluation criteria templates
CRITERIA_TEMPLATES = {
    'rps': {
        'name': 'Risques Psychosociaux',
        'criteria': [
            {
                'name': 'Ecoute active',
                'description': 'Capacite a ecouter sans interrompre, reformuler, montrer de l\'attention',
                'max_points': 5,
                'hints': 'Chercher: reformulations, questions ouvertes, silences respectueux, acquiescements'
            },
            {
                'name': 'Empathie',
                'description': 'Capacite a comprendre et reconnaitre les emotions de l\'autre',
                'max_points': 5,
                'hints': 'Chercher: validation des emotions, absence de jugement, compassion authentique'
            },
            {
                'name': 'Non-directivite',
                'description': 'Eviter de donner des conseils non sollicites ou des solutions toutes faites',
                'max_points': 4,
                'hints': 'Penaliser: conseils prematures, minimisation, "tu devrais..."'
            },
            {
                'name': 'Orientation ressources',
                'description': 'Capacite a suggerer des ressources appropriees (medecin, RH, etc.)',
                'max_points': 3,
                'hints': 'Chercher: mention de ressources professionnelles, proposition d\'aide concrete'
            },
            {
                'name': 'Communication bienveillante',
                'description': 'Ton adapte, absence de jugement, respect de la personne',
                'max_points': 3,
                'hints': 'Evaluer: ton general, formulations, respect des silences'
            }
        ]
    },
    'entretien_embauche': {
        'name': 'Entretien d\'embauche',
        'criteria': [
            {
                'name': 'Presentation',
                'description': 'Clarte et structure de la presentation personnelle',
                'max_points': 4,
                'hints': 'Chercher: introduction claire, parcours synthetique, mise en valeur'
            },
            {
                'name': 'Questions pertinentes',
                'description': 'Qualite des questions posees sur le poste et l\'entreprise',
                'max_points': 4,
                'hints': 'Chercher: questions preparees, interet pour le poste, curiosite professionnelle'
            },
            {
                'name': 'Motivation',
                'description': 'Expression claire de la motivation et adequation au poste',
                'max_points': 5,
                'hints': 'Chercher: arguments concrets, connaissance du poste, projection dans le role'
            },
            {
                'name': 'Communication professionnelle',
                'description': 'Registre de langue adapte, clarte, assurance',
                'max_points': 4,
                'hints': 'Evaluer: vocabulaire professionnel, structure des reponses, assurance'
            },
            {
                'name': 'Gestion du stress',
                'description': 'Capacite a rester calme et structure face aux questions difficiles',
                'max_points': 3,
                'hints': 'Observer: reactions aux questions pieges, maintien du calme'
            }
        ]
    },
    'biais_cognitifs': {
        'name': 'Biais Cognitifs',
        'criteria': [
            {
                'name': 'Detection du biais',
                'description': 'Capacite a identifier le biais cognitif en jeu',
                'max_points': 5,
                'hints': 'Chercher: identification explicite ou implicite du biais'
            },
            {
                'name': 'Questionnement socratique',
                'description': 'Utilisation de questions pour amener la personne a reflechir',
                'max_points': 5,
                'hints': 'Chercher: questions ouvertes, invitation a la reflexion, non-confrontation'
            },
            {
                'name': 'Prise de recul',
                'description': 'Aider la personne a prendre du recul sur sa situation',
                'max_points': 4,
                'hints': 'Chercher: propositions de perspectives alternatives, exemples, analogies'
            },
            {
                'name': 'Respect de l\'autonomie',
                'description': 'Ne pas imposer sa vision, respecter le cheminement de l\'autre',
                'max_points': 3,
                'hints': 'Penaliser: jugements, impositions, condescendance'
            },
            {
                'name': 'Pedagogie',
                'description': 'Capacite a expliquer le concept de maniere accessible si pertinent',
                'max_points': 3,
                'hints': 'Chercher: explications claires, exemples concrets, vulgarisation'
            }
        ]
    },
    'custom': {
        'name': 'Personnalise',
        'criteria': []
    }
}
