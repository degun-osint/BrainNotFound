"""
Claude Interviewer - Handle interview conversations and evaluations.
"""

import anthropic
import json
import re
from flask import current_app
from typing import Dict, List, Optional
from .prompt_loader import get_interview_prompts


class ClaudeInterviewer:
    """Handle interview conversations and evaluations with Claude."""

    # End signal marker
    END_SIGNAL = '[INTERVIEW_COMPLETE]'

    def __init__(self, api_key: str = None, model: str = None, lang: str = None):
        self.api_key = api_key or current_app.config.get('ANTHROPIC_API_KEY')
        self.model = model or current_app.config.get('CLAUDE_MODEL', 'claude-sonnet-4-20250514')
        self.client = anthropic.Anthropic(api_key=self.api_key)
        self.lang = lang or 'fr'
        self.prompts = get_interview_prompts(lang=self.lang)

    def generate_system_prompt(self, wizard_data: dict) -> str:
        """
        Generate a system prompt from wizard inputs.

        Args:
            wizard_data: Dictionary containing persona configuration from wizard

        Returns:
            Generated system prompt string
        """
        template = self.prompts['PROMPT_GENERATOR_TEMPLATE']

        # Format criteria list for the prompt
        criteria_list = ""
        if wizard_data.get('criteria'):
            for c in wizard_data['criteria']:
                criteria_list += f"- {c['name']}: {c.get('description', '')} ({c.get('max_points', 5)} points)\n"

        prompt = template.format(
            persona_name=wizard_data.get('persona_name', ''),
            persona_role=wizard_data.get('persona_role', ''),
            persona_context=wizard_data.get('persona_context', ''),
            persona_personality=wizard_data.get('persona_personality', ''),
            persona_knowledge=wizard_data.get('persona_knowledge', ''),
            persona_objectives=wizard_data.get('persona_objectives', ''),
            persona_triggers=wizard_data.get('persona_triggers', ''),
            student_context=wizard_data.get('student_context', ''),
            student_objective=wizard_data.get('student_objective', ''),
            criteria_list=criteria_list or '(Non definis)'
        )

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text.strip()

        except Exception as e:
            current_app.logger.error(f"System prompt generation error: {str(e)}")
            raise

    def generate_opening_message(self, system_prompt: str) -> str:
        """
        Generate the first message from the AI persona.

        Args:
            system_prompt: The persona's system prompt

        Returns:
            Opening message string
        """
        template = self.prompts['OPENING_MESSAGE_TEMPLATE']
        prompt = template.format(system_prompt=system_prompt)

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=500,
                messages=[{"role": "user", "content": prompt}]
            )
            return message.content[0].text.strip()

        except Exception as e:
            current_app.logger.error(f"Opening message generation error: {str(e)}")
            raise

    def get_response(self, session, user_message: str) -> dict:
        """
        Get AI response for a conversation turn.

        Args:
            session: InterviewSession object with interview and messages
            user_message: The new message from the user

        Returns:
            dict: {
                'content': str (response without end signal),
                'end_signal': bool (True if conversation should end),
                'token_count': int (estimated tokens in response)
            }
        """
        interview = session.interview

        # Build the base system prompt
        base_system_prompt = interview.system_prompt

        # Inject file content if available
        if session.uploaded_file_content:
            # Use custom injection template or fall back to language-specific default
            default_injection = self.prompts.get('FILE_INJECTION_TEMPLATE', '')
            injection_template = interview.file_upload_prompt_injection or default_injection
            file_injection = injection_template.replace(
                '{file_content}', session.uploaded_file_content
            ).replace('{file_name}', session.uploaded_file_name or ('fichier' if self.lang == 'fr' else 'file'))
            base_system_prompt = f"{base_system_prompt}\n\n{file_injection}"

        # Build the conversation wrapper
        wrapper = self.prompts['CONVERSATION_WRAPPER']
        system_prompt = wrapper.format(system_prompt=base_system_prompt)

        # Build messages array from session history
        messages = self._build_conversation_context(session, user_message)

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=1024,
                system=system_prompt,
                messages=messages
            )

            response_text = response.content[0].text.strip()

            # Check for end signal
            end_signal = self.END_SIGNAL in response_text

            # Remove end signal from content
            content = response_text.replace(self.END_SIGNAL, '').strip()

            # Estimate token count (rough: ~4 chars per token)
            token_count = len(response_text) // 4

            return {
                'content': content,
                'end_signal': end_signal,
                'token_count': token_count
            }

        except Exception as e:
            current_app.logger.error(f"Interview response error: {str(e)}")
            error_messages = self.prompts.get('ERROR_MESSAGES', {})
            error_msg = error_messages.get('technical_error', "*Une erreur technique s'est produite. Veuillez reessayer.*")
            return {
                'content': error_msg,
                'end_signal': False,
                'token_count': 0
            }

    def evaluate_session(self, session) -> dict:
        """
        Evaluate a completed interview session against all criteria.

        Args:
            session: InterviewSession object with full conversation

        Returns:
            dict: {
                'scores': [{'criterion_id': int, 'score': float, 'max_score': float, 'feedback': str}, ...],
                'summary': str,
                'total_score': float,
                'max_total': float
            }
        """
        interview = session.interview
        template = self.prompts['EVALUATION_TEMPLATE']

        # Build conversation transcript
        transcript = self._format_transcript(session)

        # Build criteria JSON
        criteria_json = json.dumps([
            {
                'id': c.id,
                'name': c.name,
                'description': c.description or '',
                'max_points': c.max_points,
                'hints': c.evaluation_hints or ''
            }
            for c in interview.criteria
        ], ensure_ascii=False, indent=2)

        # Add file content context if available
        file_context = ''
        if session.uploaded_file_content:
            file_context = f"\n\nDocument fourni par l'etudiant ({session.uploaded_file_name or 'fichier'}):\n{session.uploaded_file_content[:2000]}{'...' if len(session.uploaded_file_content) > 2000 else ''}"

        prompt = template.format(
            interview_title=interview.title,
            interview_description=interview.description or '',
            student_objective=interview.student_objective or '',
            persona_name=interview.persona_name or 'Le personnage',
            persona_role=interview.persona_role or '',
            conversation_transcript=transcript + file_context,
            criteria_json=criteria_json
        )

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=2048,
                messages=[{"role": "user", "content": prompt}]
            )

            response_text = message.content[0].text.strip()

            # Parse JSON response
            result = self._parse_json_response(response_text)

            # Validate and sanitize scores
            scores = []
            for score_data in result.get('scores', []):
                criterion_id = score_data.get('criterion_id')
                # Find matching criterion
                criterion = next((c for c in interview.criteria if c.id == criterion_id), None)
                if criterion:
                    score = max(0, min(criterion.max_points, float(score_data.get('score', 0))))
                    scores.append({
                        'criterion_id': criterion_id,
                        'criterion_name': criterion.name,
                        'score': score,
                        'max_score': criterion.max_points,
                        'feedback': score_data.get('feedback', '')
                    })

            total_score = sum(s['score'] for s in scores)
            max_total = sum(s['max_score'] for s in scores)

            return {
                'scores': scores,
                'summary': result.get('summary', 'Evaluation terminee.'),
                'total_score': total_score,
                'max_total': max_total
            }

        except Exception as e:
            current_app.logger.error(f"Interview evaluation error: {str(e)}")
            # Return default scores on error
            max_total = sum(c.max_points for c in interview.criteria)
            error_messages = self.prompts.get('ERROR_MESSAGES', {})
            error_msg = error_messages.get('evaluation_error', "Erreur lors de l'evaluation automatique.")
            return {
                'scores': [
                    {
                        'criterion_id': c.id,
                        'criterion_name': c.name,
                        'score': 0,
                        'max_score': c.max_points,
                        'feedback': error_msg
                    }
                    for c in interview.criteria
                ],
                'summary': f'{error_msg}: {str(e)}',
                'total_score': 0,
                'max_total': max_total
            }

    def _build_conversation_context(self, session, new_user_message: str,
                                     max_context_tokens: int = 8000) -> List[dict]:
        """
        Build messages array with intelligent truncation for long conversations.

        Args:
            session: InterviewSession with existing messages
            new_user_message: The new message to add
            max_context_tokens: Maximum tokens for context

        Returns:
            List of message dicts for Claude API
        """
        messages = []

        # Get existing messages
        existing = list(session.messages)

        # Estimate tokens for system prompt (already sent separately)
        # We have ~max_context_tokens for conversation

        # Build from existing messages
        current_tokens = 0
        kept_messages = []

        for msg in existing:
            if msg.role == 'system':
                continue  # Skip system messages

            msg_tokens = msg.token_count or (len(msg.content) // 4)
            if current_tokens + msg_tokens > max_context_tokens - 500:  # Leave room for new message
                break
            kept_messages.append(msg)
            current_tokens += msg_tokens

        # Convert to API format
        for msg in kept_messages:
            messages.append({
                'role': msg.role,
                'content': msg.content
            })

        # Add new user message
        messages.append({
            'role': 'user',
            'content': new_user_message
        })

        return messages

    def _format_transcript(self, session) -> str:
        """Format conversation as readable transcript."""
        lines = []
        persona_name = session.interview.persona_name or 'Personnage'

        for msg in session.messages:
            if msg.role == 'user':
                lines.append(f"[Etudiant]: {msg.content}")
            elif msg.role == 'assistant':
                lines.append(f"[{persona_name}]: {msg.content}")
            # Skip system messages

        return "\n\n".join(lines)

    def _parse_json_response(self, response_text: str) -> dict:
        """Parse JSON from Claude response, handling markdown code blocks."""
        text = response_text.strip()

        # Remove markdown code blocks if present
        if text.startswith('```'):
            # Find the content between ```
            match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', text)
            if match:
                text = match.group(1)

        # Try to find JSON object
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON from text
            match = re.search(r'\{[\s\S]*\}', text)
            if match:
                try:
                    return json.loads(match.group())
                except json.JSONDecodeError:
                    pass

        # Return empty dict on failure
        current_app.logger.error(f"Failed to parse JSON response: {text[:500]}")
        return {}


def get_criteria_templates(lang: str = None) -> dict:
    """Get predefined criteria templates for common interview types."""
    prompts = get_interview_prompts(lang=lang)
    return prompts.get('CRITERIA_TEMPLATES', {})
