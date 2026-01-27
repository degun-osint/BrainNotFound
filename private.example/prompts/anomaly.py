"""
Anomaly detection and pedagogical analysis prompts.
Copy to /private/prompts/anomaly.py and customize as needed.

Supports multilingual prompts: 'fr' (French) and 'en' (English).
"""

INDIVIDUAL_ANALYSIS_PROMPT_TEMPLATE = {
    'fr': """Analyse ce quiz pour un bilan pedagogique.

DONNEES:
{context}

Analyse:
1. POINTS FORTS: ce que l'etudiant maitrise bien
2. LACUNES: concepts a travailler (avec suggestions)
3. OBSERVATIONS: temps/comportement inhabituels (sans accuser, juste factuel)

Reponds UNIQUEMENT en JSON valide (pas de texte avant/apres):
{{
  "attention_level": "none|low|moderate|high",
  "confidence": 0.0-1.0,
  "strengths": ["point fort 1", "point fort 2"],
  "learning_gaps": [
    {{
      "topic": "concept",
      "questions_concerned": [1, 2],
      "difficulty_observed": "description",
      "suggestion": "conseil"
    }}
  ],
  "behavioral_indicators": [
    {{
      "type": "type",
      "question_number": 1,
      "description": "observation factuelle",
      "level": "info|attention|review"
    }}
  ],
  "summary": "Resume en 2-3 phrases"
}}""",

    'en': """Analyze this quiz for a pedagogical assessment.

DATA:
{context}

Analysis:
1. STRENGTHS: what the student masters well
2. GAPS: concepts to work on (with suggestions)
3. OBSERVATIONS: unusual timing/behavior (without accusations, just factual)

Respond ONLY in valid JSON (no text before/after):
{{
  "attention_level": "none|low|moderate|high",
  "confidence": 0.0-1.0,
  "strengths": ["strength 1", "strength 2"],
  "learning_gaps": [
    {{
      "topic": "concept",
      "questions_concerned": [1, 2],
      "difficulty_observed": "description",
      "suggestion": "advice"
    }}
  ],
  "behavioral_indicators": [
    {{
      "type": "type",
      "question_number": 1,
      "description": "factual observation",
      "level": "info|attention|review"
    }}
  ],
  "summary": "Summary in 2-3 sentences"
}}"""
}

CLASS_ANALYSIS_PROMPT_TEMPLATE = {
    'fr': """Analyse ces resultats de classe pour aider l'enseignant.

DONNEES:
{context}

Analyse:
1. NOTIONS A REVOIR: concepts avec faible taux de reussite
2. POINTS FORTS: ce que la classe maitrise
3. ETUDIANTS A ACCOMPAGNER: ceux en difficulte
4. OBSERVATIONS: patterns inhabituels (factuels, sans accuser)

Reponds UNIQUEMENT en JSON valide (pas de texte avant/apres):
{{
  "pedagogical_summary": "Resume en 3-4 phrases",
  "concepts_to_review": [
    {{
      "topic": "concept",
      "questions_concerned": [1],
      "success_rate": 45,
      "common_errors": ["erreur 1"],
      "teaching_suggestion": "conseil"
    }}
  ],
  "class_strengths": [
    {{
      "topic": "concept maitrise",
      "success_rate": 85
    }}
  ],
  "students_needing_support": [
    {{
      "name": "Nom",
      "gaps": ["lacune 1"],
      "suggested_focus": "axe de travail"
    }}
  ],
  "behavioral_observations": [
    {{
      "type": "observation",
      "students_concerned": ["Nom1"],
      "description": "description factuelle",
      "possible_explanations": ["explication 1"],
      "level": "info|attention"
    }}
  ],
  "recommendations": [
    {{
      "priority": "high|medium|low",
      "action": "action",
      "rationale": "pourquoi"
    }}
  ]
}}""",

    'en': """Analyze these class results to help the teacher.

DATA:
{context}

Analysis:
1. CONCEPTS TO REVIEW: concepts with low success rate
2. STRENGTHS: what the class masters
3. STUDENTS NEEDING SUPPORT: those struggling
4. OBSERVATIONS: unusual patterns (factual, no accusations)

Respond ONLY in valid JSON (no text before/after):
{{
  "pedagogical_summary": "Summary in 3-4 sentences",
  "concepts_to_review": [
    {{
      "topic": "concept",
      "questions_concerned": [1],
      "success_rate": 45,
      "common_errors": ["error 1"],
      "teaching_suggestion": "advice"
    }}
  ],
  "class_strengths": [
    {{
      "topic": "mastered concept",
      "success_rate": 85
    }}
  ],
  "students_needing_support": [
    {{
      "name": "Name",
      "gaps": ["gap 1"],
      "suggested_focus": "focus area"
    }}
  ],
  "behavioral_observations": [
    {{
      "type": "observation",
      "students_concerned": ["Name1"],
      "description": "factual description",
      "possible_explanations": ["explanation 1"],
      "level": "info|attention"
    }}
  ],
  "recommendations": [
    {{
      "priority": "high|medium|low",
      "action": "action",
      "rationale": "why"
    }}
  ]
}}"""
}
