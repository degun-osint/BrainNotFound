from flask import current_app
from typing import Dict
from .prompt_loader import get_grading_prompts
from .ai_client import complete, parse_json, wrap_untrusted, data_notice

class ClaudeGrader:
    """Grade open-ended questions using Claude API."""

    def __init__(self, model: str = None, lang: str = None):
        self.model = model  # None = model configured in the admin settings
        self.lang = lang or 'fr'

    def grade_answer(self, question: str, expected_answer: str, student_answer: str, max_points: float, severity: str = 'modere', mood: list = None, lang: str = None) -> Dict:
        """
        Grade a student's answer using Claude.

        Args:
            question: The question text
            expected_answer: The model answer
            student_answer: The student's answer
            max_points: Maximum points for this question
            severity: Grading severity - 'gentil', 'modere', or 'severe'
            mood: List of moods for feedback tone - 'neutre', 'jovial', 'taquin', 'encourageant', 'sarcastique', 'professoral'

        Returns:
            dict: {
                'score': float,
                'feedback': str
            }
        """
        if mood is None:
            mood = []

        # Use provided lang or fall back to instance lang
        current_lang = lang or self.lang

        # Load prompts from private/ or private.example/ with language
        prompts = get_grading_prompts(lang=current_lang)
        severity_instructions = prompts['SEVERITY_INSTRUCTIONS']
        mood_descriptions = prompts['MOOD_DESCRIPTIONS']
        prompt_template = prompts['GRADING_PROMPT_TEMPLATE']
        mood_header = prompts.get('MOOD_HEADER', '**TON DU FEEDBACK:**')

        severity_text = severity_instructions.get(severity, severity_instructions.get('modere', ''))

        # Build mood instructions
        mood_text = ""
        if mood:
            mood_parts = [mood_descriptions.get(m, "") for m in mood if m in mood_descriptions]
            if mood_parts:
                mood_text = f"""

{mood_header}
{' '.join(mood_parts)}"""

        prompt = prompt_template.format(
            severity_text=severity_text,
            mood_text=mood_text,
            question=question,
            expected_answer=expected_answer,
            student_answer=wrap_untrusted(student_answer, 'reponse_apprenant'),
            max_points=max_points
        )

        try:
            response_text = complete([{"role": "user", "content": prompt}],
                                     system=data_notice('reponse_apprenant', current_lang),
                                     model=self.model, effort='medium')

            # Bare JSON, fenced in ``` or wrapped in prose (depends on the model)
            result = parse_json(response_text)

            # Ensure score is within bounds
            score = max(0, min(max_points, float(result.get('score', 0))))
            feedback = result.get('feedback', 'Évaluation effectuée.')

            return {
                'score': score,
                'feedback': feedback
            }

        except Exception as e:
            # Fallback in case of error
            # Refusal, API error, unparsable answer: never a silent 0, the instructor grades it
            current_app.logger.error(f"AI grading error: {str(e)}")
            return {
                'score': 0.0,
                'feedback': "Correction automatique impossible : cette reponse sera corrigee par l'intervenant.",
                'needs_review': True
            }


def grade_open_question(question_text: str, expected_answer: str, student_answer: str, max_points: float, severity: str = 'modere', mood: list = None, lang: str = None) -> Dict:
    """Helper function to grade an open question."""
    grader = ClaudeGrader(lang=lang)
    return grader.grade_answer(question_text, expected_answer, student_answer, max_points, severity, mood, lang=lang)
