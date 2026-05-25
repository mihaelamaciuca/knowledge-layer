"""Bearer token authentication for the MCP server."""

import logging
import os
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse

log = logging.getLogger(__name__)


def load_valid_tokens() -> list[str]:
    """Load bearer tokens from environment variables.

    Tokens are loaded from MCP_TOKEN_1, MCP_TOKEN_2, etc. (1 through 9).
    Add as many as you need for your team members.

    Returns an empty list if none are configured. The server fails closed
    in that case (every request 401s), and a warning is emitted at import
    so the misconfiguration is visible at startup, not on the first call.
    """
    tokens = []
    for i in range(1, 10):
        val = os.getenv(f"MCP_TOKEN_{i}")
        if val:
            tokens.append(val)
    return tokens


if not load_valid_tokens():
    log.warning(
        "No MCP_TOKEN_1..9 environment variables configured. "
        "All authenticated requests will return 401. Set at least "
        "MCP_TOKEN_1 to a random string (e.g. `openssl rand -base64 32`)."
    )


def verify_token(request: Request) -> str | None:
    """Return the bearer token if valid, or None."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):]
    for valid in load_valid_tokens():
        if secrets.compare_digest(token, valid):
            return token
    return None


async def require_auth(request: Request) -> JSONResponse | None:
    """Return a 401 JSONResponse if auth fails, otherwise None."""
    if verify_token(request) is None:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing token"})
    return None
