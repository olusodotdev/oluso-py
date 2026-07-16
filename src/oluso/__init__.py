"""Oluso: AI-powered error monitoring for Python applications."""

from .client import Oluso
from .context import add_breadcrumb, scope, set_custom_context, set_user
from .options import Options
from .types import (
    Breadcrumb,
    BreadcrumbLevel,
    ErrorContext,
    ErrorReport,
    RequestContext,
    ServerContext,
    Severity,
    UserContext,
)

__version__ = "1.1.0"

__all__ = [
    "Oluso",
    "Options",
    "scope",
    "add_breadcrumb",
    "set_user",
    "set_custom_context",
    "Breadcrumb",
    "BreadcrumbLevel",
    "ErrorContext",
    "ErrorReport",
    "RequestContext",
    "ServerContext",
    "Severity",
    "UserContext",
]
