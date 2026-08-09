import io
import json
import urllib.error

import pytest

from oluso import AssertionOptions, HeartbeatOptions, Oluso, Options
from oluso.monitors import MonitorClient, MonitorRequestError


class FakeResponse:
    status = 200

    def __init__(self, body=b'{"accepted":true}'):
        self._body = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self):
        return self._body.read()


def test_assertion_sends_signature_and_redacts_context(recording_server, tmp_path):
    client = Oluso(
        Options(
            api_key="project-key",
            monitor_endpoint=recording_server.url,
            monitor_retries=0,
            queue_dir=str(tmp_path),
        )
    )

    receipt = client.assert_outcome(
        AssertionOptions(
            monitor="checkout-total",
            passed=False,
            expected=200,
            actual=500,
            context={"authorization": "Bearer secret", "order": "ord_1"},
        )
    )

    assert receipt.accepted is True
    assert recording_server.headers[-1]["x-oluso-signature"] == "project-key"
    assert recording_server.last()["context"] == {
        "authorization": "[REDACTED]",
        "order": "ord_1",
    }


def test_heartbeat_never_leaks_project_signature(monkeypatch):
    seen = {}

    def fake_open(request, timeout):
        seen["headers"] = {key.lower(): value for key, value in request.header_items()}
        seen["timeout"] = timeout
        seen["body"] = json.loads(request.data)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", fake_open)
    client = MonitorClient("project-key", "https://example.test/events", retries=0)
    client.heartbeat(
        "https://api.oluso.dev/api/v1/monitors/heartbeat/secret",
        HeartbeatOptions(message="alive", context={"job": "backup"}),
    )

    assert "x-oluso-signature" not in seen["headers"]
    assert seen["body"]["evidence"] == {"job": "backup"}
    assert isinstance(seen["body"]["timestamp"], int)


def test_failed_assertion_defaults_to_supported_wrong_kind(recording_server, tmp_path):
    client = Oluso(
        Options(
            api_key="project-key",
            monitor_endpoint=recording_server.url,
            monitor_retries=0,
            queue_dir=str(tmp_path),
        )
    )
    client.assert_outcome(AssertionOptions(monitor="total", passed=False))
    assert recording_server.last()["kind"] == "wrong"
    assert isinstance(recording_server.last()["timestamp"], int)


def test_heartbeat_rejects_insecure_url():
    client = MonitorClient("key", "https://example.test/events")
    with pytest.raises(ValueError, match="HTTPS"):
        client.heartbeat("http://example.test/heartbeat")


def test_workflow_complete_reuses_last_checkpoint(recording_server):
    workflow = MonitorClient("key", recording_server.url, retries=0).workflow(
        {"monitor_id": "monitor-1"}, "deploy-42"
    )

    workflow.checkpoint("built", context={"commit_sha": "abc"})
    workflow.complete(context={"release": "2026.08.07"})

    assert recording_server.requests[0]["state"] == "built"
    assert recording_server.requests[1]["state"] == "built"
    assert recording_server.requests[1]["status"] == "completed"


def test_retries_transient_failures_but_not_permanent_4xx(monkeypatch):
    attempts = {"count": 0}

    def transient_then_ok(_request, timeout):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise urllib.error.HTTPError("url", 503, "unavailable", {}, None)
        return FakeResponse()

    monkeypatch.setattr("urllib.request.urlopen", transient_then_ok)
    MonitorClient("key", "https://example.test/events", retries=1).assert_outcome(
        AssertionOptions(monitor="payment", passed=True)
    )
    assert attempts["count"] == 2

    attempts["count"] = 0

    def permanent(_request, timeout):
        attempts["count"] += 1
        raise urllib.error.HTTPError("url", 400, "bad request", {}, None)

    monkeypatch.setattr("urllib.request.urlopen", permanent)
    with pytest.raises(MonitorRequestError) as caught:
        MonitorClient("key", "https://example.test/events", retries=2).assert_outcome(
            AssertionOptions(monitor="payment", passed=True)
        )
    assert caught.value.status_code == 400
    assert caught.value.retryable is False
    assert attempts["count"] == 1
