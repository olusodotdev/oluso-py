# oluso-py

AI-powered error monitoring for Python applications: automatic error reporting, breadcrumb tracking, and intelligent error grouping.

## Installation

```bash
pip install oluso

# With a framework integration
pip install "oluso[flask]"
pip install "oluso[django]"
pip install "oluso[fastapi]"
```

## Usage with Flask

```python
from flask import Flask
from oluso import Oluso, Options
from oluso.integrations.flask import init_app

app = Flask(__name__)

client = Oluso(Options(api_key="your-api-key", environment="production"))
init_app(app, client)

@app.route("/")
def index():
    raise RuntimeError("something went wrong")  # captured and reported automatically
```

`init_app` wraps `app.wsgi_app`, so it works with any WSGI application, not just Flask. It scopes breadcrumbs to each request, auto-reports unhandled exceptions and 5xx responses, then re-raises so Flask/Werkzeug's own error handling still runs — Oluso only observes and reports, it never changes how your app responds to errors.

## Usage with Django

```python
# settings.py
from oluso import Oluso, Options

OLUSO_CLIENT = Oluso(Options(api_key="your-api-key", environment="production"))

MIDDLEWARE = [
    "oluso.integrations.django.OlusoMiddleware",
    # ... your other middleware
]
```

```python
# views.py
def index(request):
    raise RuntimeError("something went wrong")  # captured and reported automatically
```

The middleware scopes breadcrumbs to each request and auto-reports unhandled exceptions (via Django's `process_exception` hook, which fires with the real exception before Django generates its error response) and 5xx responses.

## Usage with FastAPI

```python
from fastapi import FastAPI
from oluso import Oluso, Options
from oluso.integrations.fastapi import OlusoMiddleware

client = Oluso(Options(api_key="your-api-key", environment="production"))

app = FastAPI()
app.add_middleware(OlusoMiddleware, client=client)

@app.get("/")
def index():
    raise RuntimeError("something went wrong")  # captured and reported automatically
```

This is plain ASGI middleware, so it works with any ASGI app, not just FastAPI — Starlette apps work identically. Breadcrumbs are scoped per request the same way as the other integrations; `HTTPException`s with a 4xx status aren't reported (only 5xx and unhandled exceptions are).

## Breadcrumbs & User Context

Breadcrumbs and user context are scoped per request using `contextvars` — Python's idiomatic equivalent of the `AsyncLocalStorage`-based scoping the Node SDK uses (and Go's `context.Context`), correctly isolated per thread *and* per asyncio task:

```python
from oluso import add_breadcrumb, set_user

@app.route("/checkout")
def checkout():
    add_breadcrumb("user started checkout", category="action")
    set_user(UserContext(id="user_456"))

    try:
        do_checkout()
    except Exception as err:
        client.capture_exception(err, {"cartId": "cart_123"})
```

For non-request work (a background job, a CLI command) where you still want a scope, open one yourself:

```python
from oluso import scope, add_breadcrumb

with scope():
    add_breadcrumb("job started")
    client.capture_exception(err)
```

## Manual Reporting

```python
client.capture_exception(err, {"customMeta": "extra-info"})
```

## Advanced Configuration

```python
from oluso import Oluso, Options, Severity

client = Oluso(Options(
    api_key="your-api-key",
    endpoint="https://api.oluso.dev/api/v1/error/report",  # override for self-hosting
    environment="staging",
    default_severity=Severity.MEDIUM,
    max_breadcrumbs=50,
    max_errors_per_minute=100,
    sensitive_keys=["ssn", "internal_id"],
    should_report=lambda err: "expected" not in str(err),
))
```

Call `client.flush(timeout=5)` before your process exits so a capture right before shutdown isn't lost.

## Error Report Structure

Reports sent to the API include:

- **Metadata**: Title, message, stack trace, severity, tags.
- **Context**: Request details (URL, method, headers, etc.), server details (hostname, Python version, memory, thread count).
- **History**: Breadcrumbs leading up to the error.
- **Identification**: Fingerprint for deduplication and user ID.

## License

MIT
