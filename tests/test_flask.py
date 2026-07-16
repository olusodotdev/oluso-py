import time

import pytest

flask = pytest.importorskip("flask")

from oluso import Oluso, Options  # noqa: E402
from oluso.integrations.flask import init_app  # noqa: E402

from .conftest import wait_for  # noqa: E402


def make_app(server, tmp_path):
    client = Oluso(Options(api_key="test-api-key", endpoint=server.url, queue_dir=str(tmp_path)))
    app = flask.Flask(__name__)
    init_app(app, client)
    return app, client


def test_normal_request_not_reported(recording_server, tmp_path):
    app, _ = make_app(recording_server, tmp_path)

    @app.route("/ok")
    def ok():
        return "ok"

    resp = app.test_client().get("/ok")

    assert resp.status_code == 200
    time.sleep(0.1)
    assert recording_server.count() == 0


def test_explicit_5xx_response_reported(recording_server, tmp_path):
    app, _ = make_app(recording_server, tmp_path)

    @app.route("/broken")
    def broken():
        return "broken", 500

    resp = app.test_client().get("/broken")

    assert resp.status_code == 500
    wait_for(lambda: recording_server.count() == 1)
    report = recording_server.last()
    assert report["severity"] == "critical"


def test_unhandled_exception_reports_real_error_once(recording_server, tmp_path):
    app, _ = make_app(recording_server, tmp_path)

    @app.route("/exploded")
    def exploded():
        raise ValueError("handler exploded")

    # Deliberately not setting TESTING/PROPAGATE_EXCEPTIONS, so Flask
    # converts the exception to a 500 response internally -- the common
    # production case, and the scenario got_request_exception exists for.
    resp = app.test_client().get("/exploded")

    assert resp.status_code == 500
    wait_for(lambda: recording_server.count() == 1)

    report = recording_server.last()
    assert report["message"] == "handler exploded"
    # Give any (incorrect) duplicate report a chance to arrive before asserting.
    time.sleep(0.1)
    assert recording_server.count() == 1


def test_breadcrumbs_visible_inside_view(recording_server, tmp_path):
    app, _ = make_app(recording_server, tmp_path)
    seen = {}

    @app.route("/ok")
    def ok():
        from oluso.context import _snapshot

        breadcrumbs, _, _ = _snapshot()
        seen["count"] = len(breadcrumbs)
        return "ok"

    app.test_client().get("/ok")

    assert seen["count"] == 1  # the incoming-request breadcrumb
