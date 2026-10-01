"""Quiz Generator - Generate quizzes from course content using Claude AI."""

from .ai_client import complete, wrap_untrusted, data_notice
import re
from flask import current_app
from typing import Dict, List, Optional, Tuple
from io import BytesIO
from pypdf import PdfReader
from docx import Document
from .prompt_loader import get_generator_prompts


class ContentExtractor:
    """Extract text content from various file formats."""

    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'md', 'txt'}
    MAX_CONTENT_LENGTH = 50000  # Characters limit for Claude context

    @staticmethod
    def allowed_file(filename: str) -> bool:
        """Check if file extension is allowed."""
        if not filename or '.' not in filename:
            return False
        return filename.rsplit('.', 1)[1].lower() in ContentExtractor.ALLOWED_EXTENSIONS

    @staticmethod
    def extract_from_pdf(file_stream: BytesIO) -> str:
        """Extract text from PDF file."""
        try:
            reader = PdfReader(file_stream)
            text_parts = []
            for page in reader.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
            return '\n\n'.join(text_parts)
        except Exception as e:
            raise ValueError(f"Erreur lors de la lecture du PDF: {str(e)}")

    @staticmethod
    def extract_from_docx(file_stream: BytesIO) -> str:
        """Extract text from DOCX file."""
        try:
            doc = Document(file_stream)
            text_parts = []
            for para in doc.paragraphs:
                if para.text.strip():
                    text_parts.append(para.text)
            return '\n\n'.join(text_parts)
        except Exception as e:
            raise ValueError(f"Erreur lors de la lecture du DOCX: {str(e)}")

    @staticmethod
    def extract_from_text(file_stream: BytesIO) -> str:
        """Extract text from Markdown/text file."""
        try:
            content = file_stream.read()
            # Try UTF-8 first, then fallback to latin-1
            try:
                return content.decode('utf-8')
            except UnicodeDecodeError:
                return content.decode('latin-1')
        except Exception as e:
            raise ValueError(f"Erreur lors de la lecture du fichier: {str(e)}")

    @classmethod
    def extract(cls, file_stream: BytesIO, filename: str) -> str:
        """Extract text based on file extension."""
        if not cls.allowed_file(filename):
            raise ValueError(f"Format de fichier non supporte: {filename}")

        ext = filename.rsplit('.', 1)[1].lower()

        if ext == 'pdf':
            return cls.extract_from_pdf(file_stream)
        elif ext == 'docx':
            return cls.extract_from_docx(file_stream)
        elif ext in ('md', 'txt'):
            return cls.extract_from_text(file_stream)
        else:
            raise ValueError(f"Format non supporte: {ext}")


class QuizGenerator:
    """Generate quiz questions from course content using Claude AI."""

    def __init__(self, model: str = None):
        self.model = model  # None = model configured in the admin settings

    def generate_quiz(
        self,
        content: str,
        title: str,
        num_mcq: int = 5,
        num_open: int = 2,
        difficulty: str = 'modere',
        instructions: str = ''
    ) -> Dict:
        """
        Generate a quiz from course content.

        Args:
            content: The course material text
            title: Quiz title
            num_mcq: Number of MCQ questions to generate
            num_open: Number of open questions to generate
            difficulty: 'facile', 'modere', or 'difficile'
            instructions: Additional instructions from the user

        Returns:
            dict: {
                'success': bool,
                'markdown': str (the generated quiz),
                'error': str (if failed)
            }
        """

        # Truncate content if too long
        if len(content) > ContentExtractor.MAX_CONTENT_LENGTH:
            content = content[:ContentExtractor.MAX_CONTENT_LENGTH] + "\n\n[... Contenu tronque pour respecter la limite ...]"

        # Load prompts from private/ or private.example/
        prompts = get_generator_prompts()
        quiz_format = prompts['QUIZ_FORMAT']
        difficulty_instructions = prompts['DIFFICULTY_INSTRUCTIONS']
        prompt_template = prompts['GENERATION_PROMPT_TEMPLATE']

        difficulty_text = difficulty_instructions.get(difficulty, difficulty_instructions.get('modere', ''))

        # Build custom instructions section if provided
        custom_instructions = ""
        if instructions:
            custom_instructions = f"""
**INSTRUCTIONS SPECIFIQUES DE L'INTERVENANT:**
{instructions}
"""

        prompt = prompt_template.format(
            quiz_format=quiz_format,
            title=title,
            num_mcq=num_mcq,
            num_open=num_open,
            difficulty_text=difficulty_text,
            custom_instructions=custom_instructions,
            content=wrap_untrusted(content, 'support_de_cours')
        )

        try:
            response_text = complete([{"role": "user", "content": prompt}],
                                     system=data_notice('support_de_cours', assessed=False),
                                     model=self.model, effort='medium')

            # Clean up response if it contains markdown code blocks
            if response_text.startswith('```'):
                lines = response_text.split('\n')
                # Remove first line if it's a code block marker
                if lines[0].startswith('```'):
                    lines = lines[1:]
                # Remove last line if it's a code block marker
                if lines and lines[-1].strip() == '```':
                    lines = lines[:-1]
                response_text = '\n'.join(lines)

            return {
                'success': True,
                'markdown': response_text
            }

        except Exception as e:
            current_app.logger.error(f"Quiz generation error: {str(e)}")
            return {
                'success': False,
                'markdown': '',
                'error': str(e)
            }


def generate_quiz_from_content(
    content: str,
    title: str,
    num_mcq: int = 5,
    num_open: int = 2,
    difficulty: str = 'modere',
    instructions: str = ''
) -> Dict:
    """Helper function to generate quiz from content."""
    generator = QuizGenerator()
    return generator.generate_quiz(content, title, num_mcq, num_open, difficulty, instructions)


# ==================== Regenerating chosen questions ====================

QUESTION_HEADER = re.compile(r'^## (?!#)')
POINTS = re.compile(r'\[\s*\d+(?:\.\d+)?\s*(?:points?|pts?)\s*\]\s*$', re.IGNORECASE)


def split_blocks(markdown: str) -> Tuple[str, List[str]]:
    """(preamble, question blocks): each block starts at a '## ' line, up to the next one."""
    preamble, blocks, current = [], [], None
    for line in markdown.replace('\r\n', '\n').split('\n'):
        if QUESTION_HEADER.match(line):
            if current is not None:
                blocks.append('\n'.join(current).strip('\n'))
            current = [line]
        elif current is None:
            preamble.append(line)
        else:
            current.append(line)
    if current is not None:
        blocks.append('\n'.join(current).strip('\n'))
    return '\n'.join(preamble).strip('\n'), blocks


def join_blocks(preamble: str, blocks: List[str]) -> str:
    parts = ([preamble] if preamble else []) + [b.strip('\n') for b in blocks]
    return '\n\n'.join(parts) + '\n'


def describe_block(block: str) -> Optional[Dict]:
    """The question a block defines (type, text, points, options...), or None if unreadable."""
    from app.utils.markdown_parser import QuizParser
    questions = QuizParser('# x\n\n' + block).parse()['questions']
    return questions[0] if questions else None


def _with_points(block: str, points: float) -> str:
    """Keep the original scale: the regenerated question gets the points of the one it replaces."""
    lines = block.split('\n')
    value = f'{points:g}'
    label = 'point' if points == 1 else 'points'
    header = POINTS.sub('', lines[0]).rstrip()
    lines[0] = f'{header} [{value} {label}]'
    return '\n'.join(lines)


def _strip_code_fence(text: str) -> str:
    lines = text.strip().split('\n')
    if lines and lines[0].startswith('```'):
        lines = lines[1:]
    if lines and lines[-1].strip() == '```':
        lines = lines[:-1]
    return '\n'.join(lines)


def regenerate_questions(content: str, title: str, kept: List[str], rejected: List[str],
                         specs: List[Tuple[str, float]], difficulty: str = 'modere',
                         instructions: str = '', guidance: str = '', lang: str = None) -> Dict:
    """New questions replacing the rejected ones, one per spec ('mcq' or 'open', points), in order.

    The AI sees the course, the questions kept (no duplicates) and the rejected
    ones (not to be proposed again). Returns {'success', 'blocks'} or {'success': False, 'error'}.
    """
    if len(content) > ContentExtractor.MAX_CONTENT_LENGTH:
        content = content[:ContentExtractor.MAX_CONTENT_LENGTH] + "\n\n[... Contenu tronque pour respecter la limite ...]"
    prompts = get_generator_prompts(lang)
    english = (lang or 'fr') == 'en'
    names = {'mcq': 'MCQ' if english else 'QCM', 'open': 'OPEN' if english else 'OUVERTE'}
    none = '(none)' if english else '(aucune)'
    requested = '\n'.join(f'{i}. {names[kind]} ({points:g} points)' for i, (kind, points) in enumerate(specs, 1))
    difficulty_instructions = prompts['DIFFICULTY_INSTRUCTIONS']
    labels = ("INSTRUCTOR INSTRUCTIONS", "FOR THIS REGENERATION") if english else \
        ("INSTRUCTIONS SPECIFIQUES DE L'INTERVENANT", "POUR CETTE REGENERATION")
    custom = f"\n**{labels[0]}:**\n{instructions}\n" if instructions else ''
    if guidance:
        custom += f"\n**{labels[1]}:**\n{guidance}\n"

    prompt = prompts['REGENERATION_PROMPT_TEMPLATE'].format(
        quiz_format=prompts['QUIZ_FORMAT'],
        title=title,
        kept='\n\n'.join(kept) or none,
        rejected='\n\n'.join(rejected) or none,
        count=len(specs),
        requested=requested,
        difficulty_text=difficulty_instructions.get(difficulty, difficulty_instructions.get('modere', '')),
        custom_instructions=custom,
        content=wrap_untrusted(content, 'support_de_cours'),
    )
    try:
        text = complete([{"role": "user", "content": prompt}],
                        system=data_notice('support_de_cours', assessed=False), effort='medium')
    except Exception as e:
        current_app.logger.error(f"Question regeneration error: {e}")
        return {'success': False, 'error': str(e)}

    _, blocks = split_blocks(_strip_code_fence(text))
    described = [describe_block(b) for b in blocks]
    if len(blocks) != len(specs) or any(d is None for d in described):
        return {'success': False, 'error': f'{len(blocks)} question(s) lisible(s) recue(s) pour {len(specs)} demandee(s)'}
    if [d['question_type'] for d in described] != [kind for kind, _ in specs]:
        return {'success': False, 'error': 'types de questions differents de ceux demandes'}
    return {'success': True, 'blocks': [_with_points(b, points) for b, (_, points) in zip(blocks, specs)]}
