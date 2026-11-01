import pytest

from engine.models.fake import DEMO_SCRIPT
from engine.runner.validate import validate
from engine.sdk import SDK_NAMES


def test_demo_script_is_valid():
    assert validate(DEMO_SCRIPT, SDK_NAMES) == []


@pytest.mark.parametrize(
    "src, fragment",
    [
        ("import os", "imports"),
        ("from os import system", "imports"),
        ("exec('1')", "exec"),
        ("eval('1')", "eval"),
        ("open('/etc/passwd')", "open"),
        ("x = click.__globals__", "'_'"),
        ("x = ''.__class__", "'_'"),
        ("'{0.__class__}'.format(1)", ".format"),
        ("try:\n    click('a')\nexcept Exception:\n    pass", "try/except"),
        ("os.system('ls')", "unknown name 'os'"),
        ("getattr(progress, '_db')", "getattr"),
        ("click = 3", "overwrite"),
        ("class A:\n    pass", "classes"),
        ("x = progress._db", "'_'"),
        ("def f(_x):\n    return 1", "'_'"),
        ("with open('f') as fh:\n    pass", "with-blocks"),
    ],
)
def test_rejects_unsafe(src, fragment):
    problems = validate(src, SDK_NAMES)
    assert problems, src
    assert any(fragment in p for p in problems), problems


def test_continuation_may_use_existing_variables():
    cont = 'for row in progress.pending(rows):\n    click("Save button")\n    progress.done(row)'
    assert validate(cont, SDK_NAMES) != []
    assert validate(cont, SDK_NAMES, extra_names={"rows"}) == []


def test_syntax_error_reported():
    assert "syntax error" in validate("click(", SDK_NAMES)[0]
