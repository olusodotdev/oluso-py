import re

from oluso.fingerprint import generate_fingerprint


def test_same_fingerprint_for_dynamic_value_differences():
    a = ValueError("user 123 not found")
    b = ValueError("user 456 not found")
    assert generate_fingerprint(a) == generate_fingerprint(b)


def test_different_fingerprint_for_different_error_types():
    a = ValueError("boom")
    b = TypeError("boom")
    assert generate_fingerprint(a) != generate_fingerprint(b)


def test_different_fingerprint_for_different_messages():
    a = ValueError("boom")
    b = ValueError("bang")
    assert generate_fingerprint(a) != generate_fingerprint(b)


def test_stable_hex_output():
    fp = generate_fingerprint(ValueError("boom"))
    assert re.fullmatch(r"[0-9a-f]{8}", fp)
