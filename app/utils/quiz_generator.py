"""Quiz Generator - Generate quizzes from course content using Claude AI."""

import anthropic
from flask import current_app
from typing import Dict
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

    def __init__(self, api_key: str = None, model: str = None):
        self.api_key = api_key or current_app.config.get('ANTHROPIC_API_KEY')
        self.model = model or current_app.config.get('CLAUDE_MODEL', 'claude-sonnet-4-20250514')
        self.client = anthropic.Anthropic(api_key=self.api_key)

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
**INSTRUCTIONS SPECIFIQUES DE L'ENSEIGNANT:**
{instructions}
"""

        prompt = prompt_template.format(
            quiz_format=quiz_format,
            title=title,
            num_mcq=num_mcq,
            num_open=num_open,
            difficulty_text=difficulty_text,
            custom_instructions=custom_instructions,
            content=content
        )

        try:
            message = self.client.messages.create(
                model=self.model,
                max_tokens=4096,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            response_text = message.content[0].text.strip()

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

        except anthropic.APIError as e:
            current_app.logger.error(f"Claude API error during quiz generation: {str(e)}")
            return {
                'success': False,
                'markdown': '',
                'error': f"Erreur API Claude: {str(e)}"
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
