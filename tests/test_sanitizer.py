from oluso.sanitizer import REDACTED, Sanitizer, truncate_string


def test_sanitize_headers_redacts_auth_and_cookie():
    s = Sanitizer()
    headers = {
        "Authorization": "Bearer secret-token",
        "Cookie": "session=abc123",
        "X-Request-Id": "req-1",
    }

    got = s.sanitize_headers(headers)

    assert got["Authorization"] == REDACTED
    assert got["Cookie"] == REDACTED
    assert got["X-Request-Id"] == "req-1"


def test_sanitize_value_redacts_sensitive_keys():
    s = Sanitizer(["internal_id"])

    data = {
        "username": "alice",
        "password": "hunter2",
        "internal_id": "42",
        "nested": {"api_key": "xyz", "note": "hello"},
    }

    got = s.sanitize_value(data)

    assert got["username"] == "alice"
    assert got["password"] == REDACTED
    assert got["internal_id"] == REDACTED
    assert got["nested"]["api_key"] == REDACTED
    assert got["nested"]["note"] == "hello"


def test_sanitize_value_handles_lists():
    s = Sanitizer()
    data = [{"token": "abc"}, "plain string"]

    got = s.sanitize_value(data)

    assert got[0]["token"] == REDACTED
    assert got[1] == "plain string"


def test_sanitize_value_max_depth():
    s = Sanitizer()
    nested = {"a": {"b": {"c": {"d": "too deep"}}}}
    got = s.sanitize_value(nested, max_depth=2)
    assert got["a"]["b"] == "[Max Depth Reached]"


def test_truncate_string():
    assert truncate_string("short", 100) == "short"
    assert truncate_string("0123456789", 5) == "01234... [truncated]"
