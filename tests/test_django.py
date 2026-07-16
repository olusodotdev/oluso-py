import time

import pytest

django = pytest.importorskip("django")

from django.conf import settings  # noqa: E402

from oluso import Oluso, Options  # noqa: E402

from .conftest import wait_for  # noqa: E402

if not settings.configured:
    settings.configure(
        DEBUG=False,
        ALLOWED_HOSTS=["testserver"],
        SECRET_KEY="test-secret-key",
        ROOT_URLCONF=__name__,
        MIDDLEWARE=["oluso.integrations.django.OlusoMiddleware"],
        OLUSO_CLIENT=None,  # each test injects its own client via settings.OLUSO_CLIENT
    )
    django.setup()

from django.http import HttpResponse  # noqa: E402
from django.test import Client as DjangoTestClient  # noqa: E402
from django.urls import path  # noqa: E402


def ok_view(request):
    return HttpResponse("ok")


def explicit_500_view(request):
    return HttpResponse("broken", status=500)


def exploding_view(request):
    raise ValueError("handler exploded")


def breadcrumb_view(request):
    from oluso.context import _snapshot

    breadcrumbs, _, _ = _snapshot()
    return HttpResponse(str(len(breadcrumbs)))


urlpatterns = [
    path("ok/", ok_view),
    path("broken/", explicit_500_view),
    path("exploded/", exploding_view),
    path("breadcrumbs/", breadcrumb_view),
]


def make_django_client(server, tmp_path):
    return Oluso(Options(api_key="test-api-key", endpoint=server.url, queue_dir=str(tmp_path)))


def test_normal_request_not_reported(recording_server, tmp_path):
    settings.OLUSO_CLIENT = make_django_client(recording_server, tmp_path)

    resp = DjangoTestClient().get("/ok/")

    assert resp.status_code == 200
    time.sleep(0.1)
    assert recording_server.count() == 0


def test_explicit_5xx_response_reported(recording_server, tmp_path):
    settings.OLUSO_CLIENT = make_django_client(recording_server, tmp_path)

    resp = DjangoTestClient().get("/broken/")

    assert resp.status_code == 500
    wait_for(lambda: recording_server.count() == 1)
    report = recording_server.last()
    assert report["severity"] == "critical"


def test_unhandled_exception_reports_real_error_once(recording_server, tmp_path):
    settings.OLUSO_CLIENT = make_django_client(recording_server, tmp_path)

    resp = DjangoTestClient(raise_request_exception=False).get("/exploded/")

    assert resp.status_code == 500
    wait_for(lambda: recording_server.count() == 1)

    report = recording_server.last()
    assert report["message"] == "handler exploded"
    time.sleep(0.1)  # give a (would-be incorrect) duplicate report a chance to arrive
    assert recording_server.count() == 1


def test_breadcrumbs_visible_inside_view(recording_server, tmp_path):
    settings.OLUSO_CLIENT = make_django_client(recording_server, tmp_path)

    resp = DjangoTestClient().get("/breadcrumbs/")

    assert resp.content == b"1"  # the incoming-request breadcrumb
