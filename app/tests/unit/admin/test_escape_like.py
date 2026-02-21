from app.utils.search import escape_like


def test_escape_like_basic():
    assert escape_like("hello") == "hello"


def test_escape_like_percent():
    assert escape_like("100%") == "100\\%"


def test_escape_like_underscore():
    assert escape_like("a_b") == "a\\_b"


def test_escape_like_both():
    assert escape_like("%_test_%") == "\\%\\_test\\_\\%"


def test_escape_like_backslash():
    assert escape_like("a\\b") == "a\\\\b"


def test_escape_like_empty():
    assert escape_like("") == ""
