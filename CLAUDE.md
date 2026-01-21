# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

BrainNotFound is a Flask-based web application for creating and evaluating quizzes with AI-powered grading. Teachers create quizzes in Markdown format, MCQ questions are graded automatically, and open-ended questions are graded by Claude AI with feedback.

**Tech Stack**: Python 3.13, Flask 3.1, SQLAlchemy, MySQL 8.0, Anthropic Claude API, Docker

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

## Claude AI Integration

Located in `app/utils/claude_grader.py`:
- Model configurable via `CLAUDE_MODEL` env var (default: `claude-sonnet-4-20250514`)
- Grading prompt compares student answer to expected answer
- Returns score (0 to max_points) and constructive feedback in French
- Handles API errors gracefully with logging

## Environment Variables

Required in `.env`:
- `SECRET_KEY` - Flask secret key
- `ANTHROPIC_API_KEY` - For AI grading
- `DATABASE_URL` - MySQL connection string
- `CLAUDE_MODEL` - Claude model to use (default: `claude-sonnet-4-20250514`)

## Language

UI and AI prompts are in French (educational platform for French-speaking users).
