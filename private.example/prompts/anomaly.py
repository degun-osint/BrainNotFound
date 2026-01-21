"""
Anomaly detection prompts - Standard prompts for cheating detection.
Copy to /private/prompts/anomaly.py and customize as needed.
"""

INDIVIDUAL_ANALYSIS_PROMPT_TEMPLATE = """Analyse ces donnees de quiz pour detecter des anomalies.

Donnees:
{context}

Indicateurs a verifier:
1. Temps anormalement court pour des questions complexes
2. Correlation entre pertes de focus et bonnes reponses
3. Reponses longues avec temps tres court
4. Patterns suspects

Reponds avec un JSON:
{{
  "risk_level": "low" ou "medium" ou "high",
  "confidence": nombre entre 0.0 et 1.0,
  "anomalies": [
    {{
      "type": "type d'anomalie",
      "question_number": numero ou null,
      "description": "description",
      "severity": "minor" ou "moderate" ou "severe"
    }}
  ],
  "summary": "Resume de l'analyse"
}}"""

CLASS_ANALYSIS_PROMPT_TEMPLATE = """Analyse ces donnees de classe pour detecter des patterns suspects.

DONNEES:
{context}

INDICATEURS:
1. Temps anormalement courts par rapport a la moyenne
2. Correlation entre pertes de focus et bonnes notes
3. Patterns identiques entre etudiants
4. Comportements similaires (collusion)

Reponds avec un JSON:
{{
  "class_risk_level": "low" ou "medium" ou "high",
  "summary": "Resume de l'analyse",
  "suspicious_students": [
    {{
      "name": "nom",
      "risk_level": "low" ou "medium" ou "high",
      "reasons": ["raison"],
      "suspicious_questions": [numeros]
    }}
  ],
  "question_concerns": [
    {{
      "question_number": N,
      "concern": "description"
    }}
  ],
  "recommendations": ["recommandation"]
}}"""
