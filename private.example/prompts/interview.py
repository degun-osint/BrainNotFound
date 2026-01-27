"""
Interview prompts - Templates for conversational AI interviews.
Copy to /private/prompts/interview.py and customize as needed.

Supports multilingual prompts: 'fr' (French) and 'en' (English).
"""

# Template to generate a system prompt from wizard data
PROMPT_GENERATOR_TEMPLATE = {
    'fr': """Tu es un expert en creation de scenarios pedagogiques pour des jeux de role educatifs.

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

Genere UNIQUEMENT le system prompt, sans introduction ni explication.""",

    'en': """You are an expert in creating pedagogical scenarios for educational role-playing games.

Using the following information, generate a complete system prompt for an AI assistant that will play the role of a character in a simulated interview.

**CHARACTER INFORMATION:**
Name: {persona_name}
Role: {persona_role}
Context: {persona_context}

**PERSONALITY:**
{persona_personality}

**WHAT THE CHARACTER KNOWS:**
{persona_knowledge}

**CHARACTER'S HIDDEN OBJECTIVES:**
{persona_objectives}

**TRIGGER BEHAVIORS:**
{persona_triggers}

**CONTEXT FOR THE STUDENT:**
{student_context}

**STUDENT'S OBJECTIVE:**
{student_objective}

**EVALUATION CRITERIA (for reference):**
{criteria_list}

---

Generate a detailed system prompt that:
1. Clearly defines the character's identity and context
2. Establishes their personality traits and behaviors
3. Specifies how they should react to different approaches
4. Includes examples of typical phrases from the character
5. Specifies sensitive topics and how to address them
6. Is written in English and adapted to an educational context

IMPORTANT: The prompt must be standalone and directly usable. NEVER mention that it is an exercise or simulation in the generated prompt.

Generate ONLY the system prompt, without introduction or explanation."""
}

# Wrapper for conversation - adds rules and end signal detection
CONVERSATION_WRAPPER = {
    'fr': """{system_prompt}

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

Ce marqueur indique que l'entretien peut se terminer. Ne l'utilise que si c'est vraiment pertinent.""",

    'en': """{system_prompt}

---

IMPERATIVE RULES:
1. You ALWAYS embody this character. NEVER break the immersion.
2. NEVER reveal that you are an AI or that this is an exercise.
3. Your responses should be natural and conversational (2-4 sentences generally, sometimes more if necessary).
4. Adapt your language to the character (register, expressions, hesitations...).
5. React consistently with your personality and emotional state.

END SIGNAL:
If the conversation reaches a natural conclusion (resolution, clear impasse, or the interlocutor ends the exchange), end your last response with the exact marker:
[INTERVIEW_COMPLETE]

This marker indicates that the interview can end. Only use it if truly appropriate."""
}

# Evaluation template for multi-criteria assessment
EVALUATION_TEMPLATE = {
    'fr': """Tu es un evaluateur pedagogique expert. Analyse la transcription d'un entretien simule et evalue l'etudiant selon les criteres donnes.

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
}}""",

    'en': """You are an expert pedagogical evaluator. Analyze the transcript of a simulated interview and evaluate the student according to the given criteria.

**INTERVIEW CONTEXT:**
Title: {interview_title}
Description: {interview_description}
Student's objective: {student_objective}

**CHARACTER:**
{persona_name} - {persona_role}

**FULL TRANSCRIPT:**
{conversation_transcript}

**EVALUATION CRITERIA:**
{criteria_json}

---

For each criterion, you must:
1. Analyze relevant behaviors in the conversation
2. Identify strengths and areas for improvement
3. Assign a fair and reasoned score

Respond ONLY in the following JSON format:
{{
    "scores": [
        {{
            "criterion_id": <criterion id>,
            "criterion_name": "<criterion name>",
            "score": <float between 0 and max_points>,
            "max_score": <criterion's max_points>,
            "feedback": "<detailed explanation in 2-3 sentences>"
        }}
    ],
    "summary": "<overall performance summary: strengths, areas to improve, advice for progress (3-5 sentences)>",
    "total_score": <sum of scores>,
    "max_total": <sum of max_scores>
}}"""
}

# Template for opening message generation
OPENING_MESSAGE_TEMPLATE = {
    'fr': """Tu incarnes le personnage suivant:

{system_prompt}

Genere le premier message de ce personnage pour demarrer la conversation. Ce message doit:
1. Etre naturel et en accord avec la personnalite du personnage
2. Poser le contexte de l'echange sans etre trop explicite
3. Inviter implicitement l'interlocuteur a reagir
4. Faire 2-4 phrases maximum

Reponds UNIQUEMENT avec le message du personnage, sans guillemets ni indication de role.""",

    'en': """You embody the following character:

{system_prompt}

Generate the first message from this character to start the conversation. This message must:
1. Be natural and consistent with the character's personality
2. Set the context of the exchange without being too explicit
3. Implicitly invite the interlocutor to react
4. Be 2-4 sentences maximum

Respond ONLY with the character's message, without quotes or role indication."""
}

# Predefined evaluation criteria templates
CRITERIA_TEMPLATES = {
    'fr': {
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
    },
    'en': {
        'rps': {
            'name': 'Psychosocial Risks',
            'criteria': [
                {
                    'name': 'Active Listening',
                    'description': 'Ability to listen without interrupting, rephrase, show attention',
                    'max_points': 5,
                    'hints': 'Look for: rephrasing, open questions, respectful silences, acknowledgments'
                },
                {
                    'name': 'Empathy',
                    'description': 'Ability to understand and acknowledge the other\'s emotions',
                    'max_points': 5,
                    'hints': 'Look for: emotion validation, absence of judgment, authentic compassion'
                },
                {
                    'name': 'Non-directiveness',
                    'description': 'Avoid giving unsolicited advice or ready-made solutions',
                    'max_points': 4,
                    'hints': 'Penalize: premature advice, minimization, "you should..."'
                },
                {
                    'name': 'Resource Orientation',
                    'description': 'Ability to suggest appropriate resources (doctor, HR, etc.)',
                    'max_points': 3,
                    'hints': 'Look for: mention of professional resources, concrete help proposals'
                },
                {
                    'name': 'Benevolent Communication',
                    'description': 'Appropriate tone, absence of judgment, respect for the person',
                    'max_points': 3,
                    'hints': 'Evaluate: general tone, wording, respect for silences'
                }
            ]
        },
        'entretien_embauche': {
            'name': 'Job Interview',
            'criteria': [
                {
                    'name': 'Presentation',
                    'description': 'Clarity and structure of personal presentation',
                    'max_points': 4,
                    'hints': 'Look for: clear introduction, synthetic background, self-promotion'
                },
                {
                    'name': 'Relevant Questions',
                    'description': 'Quality of questions asked about the position and company',
                    'max_points': 4,
                    'hints': 'Look for: prepared questions, interest in the position, professional curiosity'
                },
                {
                    'name': 'Motivation',
                    'description': 'Clear expression of motivation and fit for the position',
                    'max_points': 5,
                    'hints': 'Look for: concrete arguments, knowledge of the position, role projection'
                },
                {
                    'name': 'Professional Communication',
                    'description': 'Appropriate language register, clarity, confidence',
                    'max_points': 4,
                    'hints': 'Evaluate: professional vocabulary, answer structure, confidence'
                },
                {
                    'name': 'Stress Management',
                    'description': 'Ability to stay calm and structured when facing difficult questions',
                    'max_points': 3,
                    'hints': 'Observe: reactions to tricky questions, maintaining composure'
                }
            ]
        },
        'biais_cognitifs': {
            'name': 'Cognitive Biases',
            'criteria': [
                {
                    'name': 'Bias Detection',
                    'description': 'Ability to identify the cognitive bias at play',
                    'max_points': 5,
                    'hints': 'Look for: explicit or implicit identification of the bias'
                },
                {
                    'name': 'Socratic Questioning',
                    'description': 'Use of questions to lead the person to reflect',
                    'max_points': 5,
                    'hints': 'Look for: open questions, invitation to reflection, non-confrontation'
                },
                {
                    'name': 'Perspective Taking',
                    'description': 'Helping the person step back from their situation',
                    'max_points': 4,
                    'hints': 'Look for: alternative perspective proposals, examples, analogies'
                },
                {
                    'name': 'Respect for Autonomy',
                    'description': 'Not imposing one\'s view, respecting the other\'s journey',
                    'max_points': 3,
                    'hints': 'Penalize: judgments, impositions, condescension'
                },
                {
                    'name': 'Pedagogy',
                    'description': 'Ability to explain the concept in an accessible way if relevant',
                    'max_points': 3,
                    'hints': 'Look for: clear explanations, concrete examples, popularization'
                }
            ]
        },
        'custom': {
            'name': 'Custom',
            'criteria': []
        }
    }
}

# Error messages for interview by language
ERROR_MESSAGES = {
    'fr': {
        'technical_error': "*Une erreur technique s'est produite. Veuillez reessayer.*",
        'evaluation_error': "Erreur lors de l'evaluation automatique."
    },
    'en': {
        'technical_error': "*A technical error occurred. Please try again.*",
        'evaluation_error': "Error during automatic evaluation."
    }
}

# Document injection template
FILE_INJECTION_TEMPLATE = {
    'fr': """Voici le document fourni par l'etudiant ({file_name}):

{file_content}

Utilise ces informations dans tes reponses et questions.""",
    'en': """Here is the document provided by the student ({file_name}):

{file_content}

Use this information in your responses and questions."""
}
