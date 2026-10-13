"""Local sessions resist cross-origin writes and DNS rebinding; never trust owner headers."""

import hmac
import ipaddress
import re
from typing import Annotated
from urllib.parse import urlsplit
from uuid import UUID

from fastapi import Header, Request, Security
from fastapi.security import APIKeyCookie

from app.domain.errors import DomainError

COOKIE = "openfea_local_session"
session_cookie_scheme = APIKeyCookie(name=COOKIE, scheme_name="LocalSession", auto_error=False)


def check_boundary(request: Request) -> None:
    try:
        peer = ipaddress.ip_address(request.client.host if request.client else "")
        host = urlsplit("//" + request.headers.get("host", ""))
        # Access is restricted even if someone starts Uvicorn outside our supervisor.
        if not peer.is_loopback or host.hostname not in ("localhost", "127.0.0.1", "::1"):
            raise ValueError
        if (
            host.username
            or host.password
            or not host.netloc
            or host.path
            or host.query
            or host.fragment
        ):
            raise ValueError
        _ = host.port
        origin = request.headers.get("origin")
        if origin is not None:
            parsed = urlsplit(origin)
            if (
                parsed.scheme not in ("http", "https")
                or parsed.netloc.lower() != host.netloc.lower()
                or parsed.path
                or parsed.query
                or parsed.fragment
            ):
                raise ValueError
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise ValueError
    except ValueError:
        raise DomainError(
            403, "local_access_only", "Local access requires a loopback origin"
        ) from None


def same_token(received: str | None, expected: str) -> bool:
    return received is not None and hmac.compare_digest(received.encode(), expected.encode())


def current_owner(
    request: Request,
    session_cookie: Annotated[str | None, Security(session_cookie_scheme)],
    csrf_token: Annotated[
        str | None,
        Header(
            alias="X-CSRF-Token",
            description="Required for mutations; obtain from GET /api/v1/session",
        ),
    ] = None,
) -> UUID:
    if not same_token(session_cookie, request.app.state.session_token):
        raise DomainError(
            401, "local_session_required", "Open a local session before accessing projects"
        )
    if request.method not in ("GET", "HEAD", "OPTIONS") and not same_token(
        csrf_token, request.app.state.csrf_token
    ):
        raise DomainError(403, "csrf_failed", "A valid local CSRF token is required")
    return UUID(str(request.app.state.owner))


def expected_revision(if_match: str | None = Header(default=None)) -> int:
    if if_match is None:
        raise DomainError(428, "revision_required", "Send the current ETag in If-Match")
    if not re.fullmatch(r'"[1-9][0-9]{0,17}"', if_match):
        raise DomainError(422, "invalid_revision", "If-Match must be a quoted positive revision")
    return int(if_match[1:-1])
