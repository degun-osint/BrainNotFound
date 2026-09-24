# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BrainNotFound is a Flask-based web application for creating and evaluating quizzes with AI-powered grading. Teachers create quizzes in Markdown format, MCQ questions are graded automatically, and open-ended questions are graded by Claude AI with feedback.

**Tech Stack**: Python 3.13, Flask 3.1, SQLAlchemy, MySQL 8.4 LTS, Anthropic Claude API, Docker

## Commands

### Development
```bash
# Docker startup (recommended)
./start.sh

# Manual Docker commands
docker-compose up -d           # Start services
docker-compose down            # Stop services
docker-compose logs -f web     # View Flask logs
docker-compose exec db mysql -u quizuser -pquizpassword quizdb  # Access database

# Local development (no Docker)
pip install -r requirements.txt
export FLASK_APP=wsgi.py
flask run
```

### Tests
```bash
pip install -r requirements-dev.txt
pytest tests          # SQLite in memory, no MySQL/API key needed
```

### Configuration Verification
```bash
./test_setup.sh
```

### Default Credentials
- Admin: `admin` / `admin123`
- Demo Group join code: `DEMO2024`

## Architecture

### Flask Factory Pattern
The app uses the factory pattern in `app/__init__.py`. Key components:
- **Blueprints**: `auth_bp` (login/register), `admin_bp` (/admin routes), `quiz_bp` (/quiz routes)
- **Models**: User, Group, Quiz, Question, QuizResponse, Answer
- **Utils**: `markdown_parser.py` (quiz parsing), `claude_grader.py` (AI grading)

### Data Flow for Quiz Taking
1. Admin creates quiz via Markdown in admin panel
2. `QuizParser.parse()` extracts questions with types (mcq/open), points, options
3. Student takes quiz → MCQ graded automatically (all-or-nothing)
4. Open questions sent to Claude API → returns `{score, feedback}` JSON
5. Results stored in QuizResponse and Answer models

### Markdown Quiz Format
```markdown
# Quiz Title

## QCM - Question text [X points]
- [ ] Wrong option
- [x] Correct option

## OUVERTE - Question text [X points]
### Réponse attendue
Expected answer for AI comparison
```

### Key Database Relations
```
User → [1:N] → QuizResponse → [1:N] → Answer
User → [N:1] → Group
Quiz → [1:N] → Question
Question → [1:N] → Answer
```

## LLM Integration

All LLM calls go through `app/utils/ai_client.py` (`complete()`):
- Providers: `anthropic` (default, recommended, keeps prompt caching) or `openai_compatible` (any Chat Completions server: OpenAI, Mistral, Gemini, OpenRouter, Ollama...)
- Provider, base URL, model and API key are editable in Admin > Settings and read on every call (no restart); env vars are the fallback
- Prompts are tuned for Claude; `parse_json()` tolerates chatty models
- Grading prompt compares student answer to expected answer and returns `{score, feedback}` in French

## Environment Variables

Required in `.env`:
- `SECRET_KEY` - Flask secret key
- `ANTHROPIC_API_KEY` - For AI grading
- `DATABASE_URL` - MySQL connection string
- `CLAUDE_MODEL` - Claude model to use (default: `claude-opus-5-5`)
- `AI_PROVIDER`, `AI_BASE_URL`, `AI_API_KEY`, `AI_MODEL` - optional non-Anthropic provider

## Internationalization (i18n)

The app supports French (default) and English via Flask-Babel.

### UI vocabulary
The app serves schools and corporate e-learning: say **Etablissement / Groupe / Intervenant / Apprenant** (EN: Organization / Group / Instructor / Learner). Never "classe", "professeur", "etudiant" or "tenant" in the UI. In code: tenant = etablissement, group admin (`user_groups.role == 'admin'`) = intervenant, member = apprenant.

### Key files
- `babel.cfg` - Extraction configuration
- `translations/` - Translation catalogs (.po/.mo files)
- `private.example/prompts/*.py` - AI prompts with language-keyed dicts

### Translation workflow
```bash
# Extract new strings
pybabel extract -F babel.cfg -k _l -k _ -o messages.pot .

# Update catalogs
pybabel update -i messages.pot -d translations

# Compile (automatic on Docker startup)
pybabel compile -d translations
```

### Code patterns
- Routes: `from flask_babel import lazy_gettext as _l` → `flash(_l('Message'), 'error')`
- Templates: `{{ _('Text to translate') }}`
- AI prompts: `{'fr': "...", 'en': "..."}`

### Language selection priority
1. User preference (stored in `User.language_preference`)
2. Session value
3. Browser Accept-Language header
4. Default: French
