"""Bearer token authentication for the MCP server."""

import os
import secrets

from fastapi import Request
from fastapi.responses import JSONResponse


def _load_valid_tokens() -> list[str]:
    """Load bearer tokens from environment variables.

    Tokens are loaded from MCP_TOKEN_1, MCP_TOKEN_2, etc.
    Add as many as you need for your team members.
    """
    tokens = []
    for i in range(1, 10):
        val = os.getenv(f"MCP_TOKEN_{i}")
        if val:
            tokens.append(val)
    return tokens


def verify_token(request: Request) -> str | None:
    """Return the bearer token if valid, or None."""
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[len("Bearer "):]
    for valid in _load_valid_tokens():
        if secrets.compare_digest(token, valid):
            return token
    return None


async def require_auth(request: Request) -> JSONResponse | None:
    """Return a 401 JSONResponse if auth fails, otherwise None."""
    if verify_token(request) is None:
        return JSONResponse(status_code=401, content={"detail": "Invalid or missing token"})
    return None
