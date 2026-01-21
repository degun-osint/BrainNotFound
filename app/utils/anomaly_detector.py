"""
Anomaly detector for quiz responses using Claude AI.
Analyzes timing data and focus events to detect potential cheating.
"""

import json
import os
from anthropic import Anthropic
from app.models.quiz import QuizResponse, Answer
from app import db
from .prompt_loader import get_anomaly_prompts


def analyze_quiz_response(response_id):
    """
    Analyze a quiz response for potential cheating indicators.

    Args:
        response_id: The QuizResponse ID to analyze

    Returns:
        dict: Analysis result with risk_level, confidence, anomalies, and summary
    """
    response = QuizResponse.query.get(response_id)
    if not response:
        return {'error': 'Response not found'}

    answers = Answer.query.filter_by(quiz_response_id=response_id).all()

    # Build context for Claude
    total_time = 0
    if response.started_at and response.submitted_at:
        total_time = (response.submitted_at - response.started_at).total_seconds() / 60

    context = {
        'quiz_title': response.quiz.title,
        'total_time_minutes': round(total_time, 2),
        'total_focus_lost': response.total_focus_lost or 0,
        'focus_events': response.focus_events or [],
        'questions': []
    }

    # Build question details
    for answer in answers:
        question = answer.question
        q_data = {
            'question_number': question.order + 1,
            'question_text': question.question_text[:200],  # Truncate for token efficiency
            'question_type': question.question_type,
            'points': question.points,
            'time_spent_seconds': answer.time_spent_seconds,
            'focus_lost_count': answer.focus_lost_count or 0,
            'score': answer.score,
            'max_score': answer.max_score
        }

        # Add answer details
        if question.question_type == 'mcq':
            q_data['answer_correct'] = answer.score == answer.max_score
        else:
            q_data['answer_length'] = len(answer.answer_text) if answer.answer_text else 0

        context['questions'].append(q_data)

    # Calculate statistics for context
    times = [q['time_spent_seconds'] for q in context['questions'] if q['time_spent_seconds']]
    if times:
        context['avg_time_per_question'] = round(sum(times) / len(times), 1)
        context['min_time'] = min(times)
        context['max_time'] = max(times)
    else:
        context['avg_time_per_question'] = None
        context['min_time'] = None
        context['max_time'] = None

    # Call Claude for analysis
    try:
        client = Anthropic()

        # Load prompts from private/ or private.example/
        prompts = get_anomaly_prompts()
        prompt_template = prompts['INDIVIDUAL_ANALYSIS_PROMPT_TEMPLATE']

        prompt = prompt_template.format(
            context=json.dumps(context, indent=2, ensure_ascii=False)
        )

        message = client.messages.create(
            model=os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-20250514'),
            max_tokens=1000,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse response
        response_text = message.content[0].text.strip()

        # Try to extract JSON if wrapped in markdown code blocks
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        result = json.loads(response_text)

        # Validate result structure
        if 'risk_level' not in result:
            result['risk_level'] = 'low'
        if 'confidence' not in result:
            result['confidence'] = 0.5
        if 'anomalies' not in result:
            result['anomalies'] = []
        if 'summary' not in result:
            result['summary'] = 'Analyse completee sans anomalies detectees.'

        return result

    except json.JSONDecodeError as e:
        return {
            'error': f'Failed to parse AI response: {str(e)}',
            'risk_level': 'unknown',
            'confidence': 0,
            'anomalies': [],
            'summary': 'Erreur lors de l\'analyse IA'
        }
    except Exception as e:
        return {
            'error': str(e),
            'risk_level': 'unknown',
            'confidence': 0,
            'anomalies': [],
            'summary': f'Erreur: {str(e)}'
        }


def get_response_stats(response_id):
    """
    Get detailed statistics for a quiz response.

    Args:
        response_id: The QuizResponse ID

    Returns:
        dict: Statistics including time breakdown, averages, and comparisons
    """
    response = QuizResponse.query.get(response_id)
    if not response:
        return None

    answers = Answer.query.filter_by(quiz_response_id=response_id)\
        .join(Answer.question)\
        .order_by(Answer.question.property.mapper.class_.order)\
        .all()

    # Calculate total duration
    total_duration = 0
    if response.started_at and response.submitted_at:
        total_duration = (response.submitted_at - response.started_at).total_seconds()

    # Per-question stats
    question_stats = []
    total_time_tracked = 0

    for answer in answers:
        time_spent = answer.time_spent_seconds or 0
        total_time_tracked += time_spent

        stat = {
            'question_id': answer.question_id,
            'question_number': answer.question.order + 1,
            'question_type': answer.question.question_type,
            'question_text': answer.question.question_text[:100] + '...' if len(answer.question.question_text) > 100 else answer.question.question_text,
            'time_spent_seconds': time_spent,
            'focus_lost_count': answer.focus_lost_count or 0,
            'score': answer.score,
            'max_score': answer.max_score,
            'points': answer.question.points
        }

        # Add answer preview for open questions
        if answer.question.question_type == 'open' and answer.answer_text:
            stat['answer_preview'] = answer.answer_text[:100] + '...' if len(answer.answer_text) > 100 else answer.answer_text
            stat['answer_length'] = len(answer.answer_text)

        question_stats.append(stat)

    # Calculate averages
    times = [s['time_spent_seconds'] for s in question_stats if s['time_spent_seconds'] > 0]
    avg_time = sum(times) / len(times) if times else 0

    # Get class averages for comparison
    class_avg = get_class_average_times(response.quiz_id)

    return {
        'response': {
            'id': response.id,
            'quiz_id': response.quiz_id,
            'user_name': response.user.full_name,
            'quiz_title': response.quiz.title,
            'total_duration_seconds': total_duration,
            'total_duration_minutes': round(total_duration / 60, 2),
            'total_time_tracked': total_time_tracked,
            'total_focus_lost': response.total_focus_lost or 0,
            'focus_events': response.focus_events or [],
            'total_score': response.total_score,
            'max_score': response.max_score,
            'is_late': response.is_late,
            'ai_analysis_status': response.ai_analysis_status,
            'ai_analysis_result': response.ai_analysis_result
        },
        'questions': question_stats,
        'averages': {
            'avg_time_per_question': round(avg_time, 1),
            'min_time': min(times) if times else 0,
            'max_time': max(times) if times else 0
        },
        'class_averages': class_avg
    }


def get_class_average_times(quiz_id):
    """
    Calculate average time per question across all responses for a quiz.

    Args:
        quiz_id: The Quiz ID

    Returns:
        dict: Average times per question for comparison
    """
    from sqlalchemy import func

    # Get all responses for this quiz
    responses = QuizResponse.query.filter_by(quiz_id=quiz_id).all()

    if not responses:
        return {}

    # Calculate per-question averages
    question_avgs = {}

    for response in responses:
        for answer in response.answers:
            q_id = answer.question_id
            if q_id not in question_avgs:
                question_avgs[q_id] = {'times': [], 'scores': []}

            if answer.time_spent_seconds:
                question_avgs[q_id]['times'].append(answer.time_spent_seconds)
            question_avgs[q_id]['scores'].append(answer.score)

    # Calculate averages
    result = {}
    for q_id, data in question_avgs.items():
        result[q_id] = {
            'avg_time': round(sum(data['times']) / len(data['times']), 1) if data['times'] else None,
            'avg_score': round(sum(data['scores']) / len(data['scores']), 2) if data['scores'] else 0,
            'response_count': len(data['times'])
        }

    return result


def get_class_stats(quiz_id):
    """
    Get comprehensive class statistics for a quiz.

    Args:
        quiz_id: The Quiz ID

    Returns:
        dict: Class-wide statistics for analysis
    """
    from app.models.quiz import Quiz, Question

    quiz = Quiz.query.get(quiz_id)
    if not quiz:
        return None

    responses = QuizResponse.query.filter_by(quiz_id=quiz_id).all()
    if not responses:
        return {'error': 'No responses yet'}

    # Get questions with content
    questions = Question.query.filter_by(quiz_id=quiz_id).order_by(Question.order).all()

    # Build question data with content
    question_data = []
    for q in questions:
        q_info = {
            'id': q.id,
            'number': q.order + 1,
            'type': q.question_type,
            'text': q.question_text,
            'points': q.points,
            'expected_answer': q.expected_answer if q.question_type == 'open' else None,
            'correct_answers': q.correct_answers if q.question_type == 'mcq' else None,
            'options': q.options if q.question_type == 'mcq' else None
        }
        question_data.append(q_info)

    # Build student data
    students = []
    for response in responses:
        student_data = {
            'id': response.id,
            'name': response.user.full_name,
            'username': response.user.username,
            'total_score': response.total_score,
            'max_score': response.max_score,
            'percentage': round((response.total_score / response.max_score * 100), 1) if response.max_score > 0 else 0,
            'total_focus_lost': response.total_focus_lost or 0,
            'total_duration': 0,
            'answers': []
        }

        if response.started_at and response.submitted_at:
            student_data['total_duration'] = round((response.submitted_at - response.started_at).total_seconds())

        # Get answers per question
        for answer in response.answers:
            ans_data = {
                'question_id': answer.question_id,
                'question_number': answer.question.order + 1,
                'time_spent': answer.time_spent_seconds or 0,
                'focus_lost': answer.focus_lost_count or 0,
                'score': answer.score,
                'max_score': answer.max_score
            }
            if answer.question.question_type == 'open':
                ans_data['answer_length'] = len(answer.answer_text) if answer.answer_text else 0
            student_data['answers'].append(ans_data)

        students.append(student_data)

    # Calculate class averages per question
    question_stats = {}
    for q in questions:
        q_id = q.id
        times = []
        scores = []
        focus_counts = []

        for response in responses:
            for answer in response.answers:
                if answer.question_id == q_id:
                    if answer.time_spent_seconds:
                        times.append(answer.time_spent_seconds)
                    scores.append(answer.score)
                    focus_counts.append(answer.focus_lost_count or 0)

        question_stats[q_id] = {
            'avg_time': round(sum(times) / len(times), 1) if times else 0,
            'min_time': min(times) if times else 0,
            'max_time': max(times) if times else 0,
            'std_time': round((sum((t - (sum(times)/len(times)))**2 for t in times) / len(times))**0.5, 1) if len(times) > 1 else 0,
            'avg_score': round(sum(scores) / len(scores), 2) if scores else 0,
            'total_focus_lost': sum(focus_counts)
        }

    # Global stats
    total_times = [s['total_duration'] for s in students if s['total_duration'] > 0]
    total_scores = [s['percentage'] for s in students]
    total_focus = [s['total_focus_lost'] for s in students]

    global_stats = {
        'student_count': len(students),
        'avg_duration': round(sum(total_times) / len(total_times) / 60, 1) if total_times else 0,
        'avg_score': round(sum(total_scores) / len(total_scores), 1) if total_scores else 0,
        'total_focus_events': sum(total_focus),
        'students_with_focus_issues': len([f for f in total_focus if f > 0])
    }

    return {
        'quiz': {
            'id': quiz.id,
            'title': quiz.title,
            'description': quiz.description
        },
        'questions': question_data,
        'question_stats': question_stats,
        'students': students,
        'global_stats': global_stats
    }


def analyze_class(quiz_id):
    """
    Run AI analysis on all responses for a quiz.

    Args:
        quiz_id: The Quiz ID

    Returns:
        dict: Class-wide analysis with suspicious patterns
    """
    stats = get_class_stats(quiz_id)
    if not stats or 'error' in stats:
        return stats

    # Build context for Claude
    context = {
        'quiz_title': stats['quiz']['title'],
        'student_count': stats['global_stats']['student_count'],
        'avg_class_duration_minutes': stats['global_stats']['avg_duration'],
        'avg_class_score_percent': stats['global_stats']['avg_score'],
        'total_focus_events': stats['global_stats']['total_focus_events'],
        'questions': [],
        'students': []
    }

    # Add question content and stats
    for q in stats['questions']:
        q_stat = stats['question_stats'].get(q['id'], {})
        q_info = {
            'number': q['number'],
            'type': q['type'],
            'text': q['text'][:300],  # Truncate
            'points': q['points'],
            'class_avg_time': q_stat.get('avg_time', 0),
            'class_std_time': q_stat.get('std_time', 0),
            'class_avg_score': q_stat.get('avg_score', 0),
            'focus_events': q_stat.get('total_focus_lost', 0)
        }
        if q['type'] == 'open' and q['expected_answer']:
            q_info['expected_answer'] = q['expected_answer'][:200]
        context['questions'].append(q_info)

    # Add student data
    for student in stats['students']:
        s_info = {
            'name': student['name'],
            'total_duration_seconds': student['total_duration'],
            'score_percent': student['percentage'],
            'focus_lost': student['total_focus_lost'],
            'per_question': []
        }
        for ans in student['answers']:
            q_stat = stats['question_stats'].get(ans['question_id'], {})
            avg_time = q_stat.get('avg_time', 0)
            s_info['per_question'].append({
                'q': ans['question_number'],
                'time': ans['time_spent'],
                'deviation': round((ans['time_spent'] - avg_time) / avg_time * 100, 0) if avg_time > 0 else 0,
                'focus': ans['focus_lost'],
                'score': f"{ans['score']}/{ans['max_score']}"
            })
        context['students'].append(s_info)

    # Call Claude for analysis
    try:
        client = Anthropic()

        # Load prompts from private/ or private.example/
        prompts = get_anomaly_prompts()
        prompt_template = prompts['CLASS_ANALYSIS_PROMPT_TEMPLATE']

        prompt = prompt_template.format(
            context=json.dumps(context, indent=2, ensure_ascii=False)
        )

        message = client.messages.create(
            model=os.getenv('CLAUDE_MODEL', 'claude-sonnet-4-20250514'),
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = message.content[0].text.strip()

        # Extract JSON
        if '```json' in response_text:
            response_text = response_text.split('```json')[1].split('```')[0].strip()
        elif '```' in response_text:
            response_text = response_text.split('```')[1].split('```')[0].strip()

        result = json.loads(response_text)

        # Validate structure
        if 'class_risk_level' not in result:
            result['class_risk_level'] = 'low'
        if 'suspicious_students' not in result:
            result['suspicious_students'] = []
        if 'question_concerns' not in result:
            result['question_concerns'] = []
        if 'recommendations' not in result:
            result['recommendations'] = []

        return result

    except json.JSONDecodeError as e:
        return {
            'error': f'Failed to parse AI response: {str(e)}',
            'class_risk_level': 'unknown',
            'summary': 'Erreur lors de l\'analyse',
            'suspicious_students': [],
            'question_concerns': [],
            'recommendations': []
        }
    except Exception as e:
        return {
            'error': str(e),
            'class_risk_level': 'unknown',
            'summary': f'Erreur: {str(e)}',
            'suspicious_students': [],
            'question_concerns': [],
            'recommendations': []
        }
