import pytest

from oluso import Oluso, Options, add_breadcrumb, scope, set_user
from oluso.types import UserContext

from .conftest import wait_for


def make_client(server, **overrides):
    options = Options(api_key="test-api-key", endpoint=server.url, **overrides)
    return Oluso(options)


def test_requires_api_key():
    with pytest.raises(ValueError):
        Oluso(Options(api_key=""))


def test_capture_exception_sends_report(recording_server, tmp_path):
    client = make_client(recording_server, queue_dir=str(tmp_path))

    client.capture_exception(ValueError("boom"))

    wait_for(lambda: recording_server.count() == 1)
    report = recording_server.last()
    headers = recording_server.headers[-1]

    assert report["message"] == "boom"
    assert headers.get("x-oluso-signature") == "test-api-key"


def test_capture_exception_queues_on_failure(recording_server, tmp_path):
    recording_server.set_fail(True)
    client = make_client(recording_server, queue_dir=str(tmp_path))

    client.capture_exception(ValueError("boom"))

    wait_for(lambda: recording_server.count() == 1)
    wait_for(lambda: client._offline_queue.size() == 1)


def test_should_report_skips_filtered_errors(recording_server, tmp_path):
    client = make_client(
        recording_server,
        queue_dir=str(tmp_path),
        should_report=lambda err: str(err) != "ignore me",
    )

    client.capture_exception(ValueError("ignore me"))
    client.capture_exception(ValueError("report me"))

    wait_for(lambda: recording_server.count() == 1)
    assert recording_server.count() == 1


def test_rate_limiter_blocks_excess_sends(recording_server, tmp_path):
    client = make_client(recording_server, queue_dir=str(tmp_path), max_errors_per_minute=1)

    client.capture_exception(ValueError("first"))
    client.capture_exception(ValueError("second"))

    wait_for(lambda: recording_server.count() == 1)
    import time

    time.sleep(0.1)
    assert recording_server.count() == 1


def test_capture_exception_includes_scoped_breadcrumbs_and_user(recording_server, tmp_path):
    client = make_client(recording_server, queue_dir=str(tmp_path))

    with scope():
        add_breadcrumb("user clicked checkout")
        set_user(UserContext(id="user-123"))
        client.capture_exception(ValueError("checkout failed"))

    wait_for(lambda: recording_server.count() == 1)
    report = recording_server.last()

    assert report["context"]["breadcrumbs"][0]["message"] == "user clicked checkout"
    assert report["context"]["user"]["id"] == "user-123"


def test_flush_waits_for_in_flight_send(recording_server, tmp_path):
    client = make_client(recording_server, queue_dir=str(tmp_path))

    client.capture_exception(ValueError("boom"))
    assert client.flush(timeout=2)
    assert recording_server.count() == 1
