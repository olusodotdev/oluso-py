"""Minimal example of wiring Oluso into a FastAPI app.

    pip install "oluso[fastapi]" uvicorn
    OLUSO_API_KEY=your-api-key uvicorn examples.fastapi_app:app --port 8080
"""

import os

from fastapi import FastAPI

from oluso import Oluso, Options, add_breadcrumb
from oluso.integrations.fastapi import OlusoMiddleware

client = Oluso(Options(api_key=os.environ.get("OLUSO_API_KEY", ""), environment="development"))

app = FastAPI(on_shutdown=[lambda: client.flush(timeout=5)])
app.add_middleware(OlusoMiddleware, client=client)


@app.get("/")
def index():
    add_breadcrumb("handling root request")
    return {"status": "ok"}


@app.get("/boom")
def boom():
    # Middleware auto-reports both raised exceptions and 5xx responses, so
    # a deliberately failing endpoint needs no manual capture at all.
    raise RuntimeError("something went wrong")


@app.get("/manual")
def manual():
    try:
        do_work()
    except Exception as err:
        client.capture_exception(err, {"step": "manual example"})
        return {"error": "internal error"}, 500
    return {"status": "ok"}


def do_work():
    raise ValueError("work failed")
