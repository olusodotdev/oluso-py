import pytest

from oluso.transport import MAX_PAYLOAD_BYTES, TransportError, send_error_report


def test_total_payload_limit_matches_contract_and_prevents_network(monkeypatch):
    assert MAX_PAYLOAD_BYTES == 512 * 1024
    called = False

    def unexpected_request(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("network must not be called for an oversized report")

    monkeypatch.setattr("urllib.request.urlopen", unexpected_request)
    with pytest.raises(TransportError, match="maximum"):
        send_error_report(
            "https://api.oluso.dev/api/v1/error/report",
            {"message": "x" * (MAX_PAYLOAD_BYTES + 1)},
            "test-key",
            1,
        )
    assert called is False
