"""Minimal example of wiring Oluso into a Django app, as a single
standalone script (using django.conf.settings.configure() rather than a
full manage.py project layout, purely for a self-contained example).

    pip install "oluso[django]"
    OLUSO_API_KEY=your-api-key python examples/django_app.py
"""

import os

import django
from django.conf import settings

from oluso import Oluso, Options, add_breadcrumb

client = Oluso(Options(api_key=os.environ.get("OLUSO_API_KEY", ""), environment="development"))

settings.configure(
    DEBUG=False,
    ALLOWED_HOSTS=["*"],
    SECRET_KEY="example-secret-key",
    ROOT_URLCONF=__name__,
    MIDDLEWARE=["oluso.integrations.django.OlusoMiddleware"],
    OLUSO_CLIENT=client,
)
django.setup()

from django.http import HttpResponse  # noqa: E402
from django.urls import path  # noqa: E402


def index(request):
    add_breadcrumb("handling root request")
    return HttpResponse("ok")


def boom(request):
    # Middleware auto-reports both raised exceptions and 5xx responses, so
    # a deliberately failing view needs no manual capture at all.
    raise RuntimeError("something went wrong")


def manual(request):
    try:
        do_work()
    except Exception as err:
        client.capture_exception(err, {"step": "manual example"})
        return HttpResponse("internal error", status=500)
    return HttpResponse("ok")


def do_work():
    raise ValueError("work failed")


urlpatterns = [
    path("", index),
    path("boom", boom),
    path("manual", manual),
]

if __name__ == "__main__":
    from django.core.management import execute_from_command_line

    execute_from_command_line(["manage.py", "runserver", "8080"])
