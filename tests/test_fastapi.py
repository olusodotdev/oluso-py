import time

import pytest

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from oluso import Oluso, Options  # noqa: E402
from oluso.integrations.fastapi import OlusoMiddleware  # noqa: E402

from .conftest import wait_for  # noqa: E402


def make_app(server, tmp_path):
    client = Oluso(Options(api_key="test-api-key", endpoint=server.url, queue_dir=str(tmp_path)))
    app = FastAPI()
    app.add_middleware(OlusoMiddleware, client=client)
    return app, client


def test_normal_request_not_reported(recording_server, tmp_path):
    app, _ = make_app(recording_server, tmp_path)

    @app.get("/ok")
    def ok():
        return {"status": "ok"}

    resp = TestClient(app).get("/ok")

    assert resp.status_code == 200
    time.sleep(0.1)
    assert recording_server.count() == 0


def test_explicit_5xx_response_reported(recording_server, tmp_path):
    app, _ = make_app(recording_server, tmp_path)

    @app.get("/broken")
    def broken():
        from fastapi import Response

        return Response(content="broken", status_code=500)

    resp = TestClient(app).get("/broken")

    assert resp.status_code == 500
    wait_for(lambda: recording_server.count() == 1)
    report = recording_server.last()
    assert report["severity"] == "critical"


def test_unhandled_exception_reports_real_error_once(recording_server, tmp_path):
    app, _ = make_app(recording_server, tmp_path)

    @app.get("/exploded")
    def exploded():
        raise ValueError("handler exploded")

    resp = TestClient(app, raise_server_exceptions=False).get("/exploded")

    assert resp.status_code == 500
    wait_for(lambda: recording_server.count() == 1)

    report = recording_server.last()
    assert report["message"] == "handler exploded"
    time.sleep(0.1)  # give a (would-be incorrect) duplicate report a chance to arrive
    assert recording_server.count() == 1


def test_breadcrumbs_visible_inside_view(recording_server, tmp_path):
    app, _ = make_app(recording_server, tmp_path)
    seen = {}

    @app.get("/ok")
    def ok():
        from oluso.context import _snapshot

        breadcrumbs, _, _ = _snapshot()
        seen["count"] = len(breadcrumbs)
        return {"status": "ok"}

    TestClient(app).get("/ok")

    assert seen["count"] == 1  # the incoming-request breadcrumb


def test_http_exception_not_reported_as_5xx_when_4xx(recording_server, tmp_path):
    app, _ = make_app(recording_server, tmp_path)

    @app.get("/not-found")
    def not_found():
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="not found")

    resp = TestClient(app).get("/not-found")

    assert resp.status_code == 404
    time.sleep(0.1)
    assert recording_server.count() == 0
