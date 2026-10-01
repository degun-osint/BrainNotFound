import pytest

from app.utils.markdown_parser import QuizParser


@pytest.mark.parametrize('suffix, expected', [
    ('[2 points]', 2.0),
    ('[1 point]', 1.0),
    ('[2 pts]', 2.0),
    ('[1 pt]', 1.0),
    ('[1.5 pts] ', 1.5),
    ('', 1.0),
])
def test_points_syntax(suffix, expected):
    md = f"# Quiz\n\n## QCM - Capitale de la France ? {suffix}\n- [ ] Lyon\n- [x] Paris\n"
    q = QuizParser(md).parse()['questions'][0]
    assert q['points'] == expected
    assert q['question_text'] == 'Capitale de la France ?'


def test_english_keywords():
    md = "# Quiz\n\n## MCQ - Capital of France? [2 points]\n- [ ] Lyon\n- [x] Paris\n\n" \
         "## OPEN - Explain the water cycle [3 points]\n### Expected answer\nEvaporation, condensation.\n"
    qs = QuizParser(md).parse()['questions']
    assert [q['question_type'] for q in qs] == ['mcq', 'open']
    assert qs[1]['expected_answer'] == 'Evaporation, condensation.' and qs[1]['points'] == 3.0
