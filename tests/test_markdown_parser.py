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
