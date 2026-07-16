"""Minimal example of wiring Oluso into a Flask app.

    pip install "oluso[flask]"
    OLUSO_API_KEY=your-api-key python examples/flask_app.py
"""

import atexit
import os

from flask import Flask

from oluso import Oluso, Options, add_breadcrumb
from oluso.integrations.flask import init_app

client = Oluso(Options(api_key=os.environ.get("OLUSO_API_KEY", ""), environment="development"))
atexit.register(lambda: client.flush(timeout=5))

app = Flask(__name__)
init_app(app, client)


@app.route("/")
def index():
    add_breadcrumb("handling root request")
    return "ok"


@app.route("/boom")
def boom():
    # Middleware auto-reports both raised exceptions and 5xx responses, so
    # a deliberately failing view needs no manual capture at all.
    raise RuntimeError("something went wrong")


@app.route("/manual")
def manual():
    try:
        do_work()
    except Exception as err:
        client.capture_exception(err, {"step": "manual example"})
        return "internal error", 500
    return "ok"


def do_work():
    raise ValueError("work failed")


if __name__ == "__main__":
    app.run(port=8080)
