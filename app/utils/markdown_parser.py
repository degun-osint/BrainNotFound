import re
from typing import List, Dict, Any

class QuizParser:
    """
    Parse quiz questions from Markdown format.

    Format:
    # Quiz Title

    ## QCM - Question text here [X points]
    - [ ] Option 1
    - [x] Option 2 (correct)
    - [ ] Option 3

    ## OUVERTE - Question text here [X points]
    Question text can be multiline

    ### Réponse attendue (or ### Reponse attendue)
    Expected answer text here
    """

    def __init__(self, markdown_content: str):
        self.content = markdown_content
        self.title = ""
        self.description = ""
        self.questions = []

    def parse(self) -> Dict[str, Any]:
        """Parse the markdown content and extract quiz data."""
        lines = self.content.split('\n')

        # Extract title (first h1)
        title_match = re.search(r'^#\s+(.+)$', self.content, re.MULTILINE)
        if title_match:
            self.title = title_match.group(1).strip()

        # Parse questions
        self._parse_questions(lines)

        return {
            'title': self.title,
            'description': self.description,
            'questions': self.questions
        }

    def _parse_questions(self, lines: List[str]):
        """Parse questions from markdown lines."""
        i = 0
        question_order = 0

        while i < len(lines):
            line = lines[i].strip()

            # Look for question headers (## QCM or ## OUVERTE)
            if line.startswith('## '):
                question_type, question_data, next_i = self._parse_question_block(lines, i)
                if question_data:
                    question_data['order'] = question_order
                    self.questions.append(question_data)
                    question_order += 1
                i = next_i
            else:
                i += 1

    def _parse_question_block(self, lines: List[str], start_idx: int) -> tuple:
        """Parse a single question block starting at the given index."""
        header = lines[start_idx].strip()

        # Parse header: ## TYPE - Question text [X points]
        mcq_match = re.match(r'^##\s+QCM\s*-?\s*(.+?)(?:\[(\d+(?:\.\d+)?)\s*points?\])?$', header, re.IGNORECASE)
        open_match = re.match(r'^##\s+OUVERTE?\s*-?\s*(.+?)(?:\[(\d+(?:\.\d+)?)\s*points?\])?$', header, re.IGNORECASE)

        if mcq_match:
            return self._parse_mcq_question(lines, start_idx, mcq_match)
        elif open_match:
            return self._parse_open_question(lines, start_idx, open_match)
        else:
            return None, None, start_idx + 1

    def _parse_mcq_question(self, lines: List[str], start_idx: int, match) -> tuple:
        """Parse an MCQ question."""
        question_text = match.group(1).strip()
        points = float(match.group(2)) if match.group(2) else 1.0

        options = []
        correct_answers = []
        i = start_idx + 1

        # Collect question text until we hit options or next section
        question_lines = []
        while i < len(lines):
            line = lines[i].strip()
            if line.startswith('- ['):
                break
            if line.startswith('##'):
                break
            if line:
                question_lines.append(line)
            i += 1

        if question_lines:
            question_text = question_text + '\n' + '\n'.join(question_lines)

        # Parse options
        option_idx = 0
        while i < len(lines):
            line = lines[i].strip()

            # Check for option line
            option_match = re.match(r'^-\s*\[(x| )\]\s*(.+)$', line, re.IGNORECASE)
            if option_match:
                is_correct = option_match.group(1).lower() == 'x'
                option_text = option_match.group(2).strip()
                options.append(option_text)

                if is_correct:
                    correct_answers.append(option_idx)

                option_idx += 1
                i += 1
            elif line.startswith('##'):
                # Next question
                break
            else:
                i += 1
                if not line:
                    # Empty line might mean end of options
                    if options:
                        break

        question_data = {
            'question_type': 'mcq',
            'question_text': question_text.strip(),
            'points': points,
            'options': options,
            'correct_answers': correct_answers,
            'allow_multiple': len(correct_answers) > 1  # Checkbox if multiple correct answers
        }

        return 'mcq', question_data, i

    def _parse_open_question(self, lines: List[str], start_idx: int, match) -> tuple:
        """Parse an open question."""
        question_text = match.group(1).strip()
        points = float(match.group(2)) if match.group(2) else 1.0

        i = start_idx + 1
        question_lines = []
        expected_answer = ""

        # Collect question text
        while i < len(lines):
            line = lines[i].strip()

            # Check for expected answer section (accept both "Réponse" and "Reponse")
            if line.startswith('### ') and ('réponse' in line.lower() or 'reponse' in line.lower()):
                i += 1
                # Collect expected answer
                answer_lines = []
                while i < len(lines):
                    line = lines[i].strip()
                    if line.startswith('##'):
                        break
                    if line:
                        answer_lines.append(line)
                    i += 1
                expected_answer = '\n'.join(answer_lines).strip()
                break

            if line.startswith('##'):
                break

            if line:
                question_lines.append(line)
            i += 1

        if question_lines:
            question_text = question_text + '\n' + '\n'.join(question_lines)

        question_data = {
            'question_type': 'open',
            'question_text': question_text.strip(),
            'points': points,
            'expected_answer': expected_answer
        }

        return 'open', question_data, i


def parse_quiz_markdown(markdown_content: str) -> Dict[str, Any]:
    """Helper function to parse quiz markdown."""
    parser = QuizParser(markdown_content)
    return parser.parse()


def validate_quiz_data(quiz_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Validate parsed quiz data and return warnings/errors.

    Returns:
        {
            'valid': bool,
            'errors': list of critical errors,
            'warnings': list of non-critical warnings
        }
    """
    errors = []
    warnings = []

    if not quiz_data.get('title'):
        warnings.append("Le quiz n'a pas de titre (sera 'Sans titre')")

    questions = quiz_data.get('questions', [])

    if not questions:
        errors.append("Aucune question trouvee dans le quiz")
        return {'valid': False, 'errors': errors, 'warnings': warnings}

    for i, q in enumerate(questions, 1):
        q_type = q.get('question_type')
        q_text = q.get('question_text', '')[:50]

        if q_type == 'mcq':
            options = q.get('options', [])
            correct = q.get('correct_answers', [])

            if not options:
                errors.append(f"Question {i} (QCM): aucune option definie")
            elif not correct:
                errors.append(f"Question {i} (QCM): aucune reponse correcte marquee [x]")
            elif len(options) < 2:
                warnings.append(f"Question {i} (QCM): seulement {len(options)} option(s)")

        elif q_type == 'open':
            expected = q.get('expected_answer', '')

            if not expected:
                warnings.append(f"Question {i} (OUVERTE): pas de reponse attendue - '{q_text}...'")

    return {
        'valid': len(errors) == 0,
        'errors': errors,
        'warnings': warnings
    }
