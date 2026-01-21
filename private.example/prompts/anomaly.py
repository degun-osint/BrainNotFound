"""
Anomaly detection and pedagogical analysis prompts.
Copy to /private/prompts/anomaly.py and customize as needed.
"""

INDIVIDUAL_ANALYSIS_PROMPT_TEMPLATE = """Analyse ce quiz pour un bilan pedagogique.

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
}}"""

CLASS_ANALYSIS_PROMPT_TEMPLATE = """Analyse ces resultats de classe pour aider l'enseignant.

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
}}"""
