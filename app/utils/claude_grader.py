import anthropic
from flask import current_app
from typing import Dict
from .prompt_loader import get_grading_prompts

class ClaudeGrader:
    """Grade open-ended questions using Claude API."""

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or current_app.config.get('ANTHROPIC_API_KEY')
        self.model = model or current_app.config.get('CLAUDE_MODEL', 'claude-sonnet-4-20250514')
        self.client = anthropic.Anthropic(api_key=self.api_key)

    def grade_answer(self, question: str, expected_answer: str, student_answer: str, max_points: float, severity: str = 'modere', mood: list = None) -> Dict:
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

        # Load prompts from private/ or private.example/
        prompts = get_grading_prompts()
        severity_instructions = prompts['SEVERITY_INSTRUCTIONS']
        mood_descriptions = prompts['MOOD_DESCRIPTIONS']
        prompt_template = prompts['GRADING_PROMPT_TEMPLATE']

        severity_text = severity_instructions.get(severity, severity_instructions.get('modere', ''))

        # Build mood instructions
        mood_text = ""
        if mood:
            mood_parts = [mood_descriptions.get(m, "") for m in mood if m in mood_descriptions]
            if mood_parts:
                mood_text = f"""

**TON DU FEEDBACK:**
{' '.join(mood_parts)}"""

        prompt = prompt_template.format(
            severity_text=severity_text,
            mood_text=mood_text,
            question=question,
            expected_answer=expected_answer,
            student_answer=student_answer,
            max_points=max_points
        )

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            response_text = message.content[0].text.strip()

            # Parse JSON response
            import json
            # Remove markdown code blocks if present
            if response_text.startswith('```'):
                response_text = response_text.split('```')[1]
                if response_text.startswith('json'):
                    response_text = response_text[4:]
                response_text = response_text.strip()

            result = json.loads(response_text)

            # Ensure score is within bounds
            score = max(0, min(max_points, float(result.get('score', 0))))
            feedback = result.get('feedback', 'Évaluation effectuée.')

            return {
                'score': score,
                'feedback': feedback
            }

        except Exception as e:
            # Fallback in case of error
            current_app.logger.error(f"Claude grading error: {str(e)}")
            return {
                'score': 0.0,
                'feedback': f"Erreur lors de l'évaluation automatique: {str(e)}"
            }


def grade_open_question(question_text: str, expected_answer: str, student_answer: str, max_points: float, severity: str = 'modere', mood: list = None) -> Dict:
    """Helper function to grade an open question."""
    grader = ClaudeGrader()
    return grader.grade_answer(question_text, expected_answer, student_answer, max_points, severity, mood)
