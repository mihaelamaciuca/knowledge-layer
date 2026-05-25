"""FastAPI MCP server for {{PROJECT_NAME}} knowledge infrastructure.

Exposes seven tools over the MCP Streamable HTTP transport for Claude Code /
claude.ai:
    search_docs, hybrid vector+lexical retrieval with filters
    get_decision, settled-decision lookup
    get_impact_targets, impact-target packet (decision → affected docs)
    get_doc_neighborhood, frontmatter graph
    get_doc_outline, section tree for long docs
    get_drift_report, hygiene-loop queue
    check_index_health, operational status

See each tool's docstring below (and the project README) for per-tool guidance.
"""
import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse
from mcp.server.fastmcp import FastMCP
from pydantic import BaseModel, Field

from src.auth import require_auth, verify_token
from src.decisions import get_decision as _get_decision, get_impact_targets as _get_impact_targets
from src.drift import get_drift_report as _get_drift_report
from src.neighborhood import get_doc_neighborhood as _get_doc_neighborhood
from src.outline import get_doc_outline as _get_doc_outline
from src.search import check_index_health as _check_index_health, search_docs as _search_docs

# ---------------------------------------------------------------------------
# MCP server
# ---------------------------------------------------------------------------
mcp = FastMCP("{{PROJECT_NAME}}-docs")


@mcp.tool()
def search_docs(
    query: str,
    k: int = 10,
    status: str | None = None,
    area: int | None = None,
    doc_type: str | None = None,
    include_superseded: bool = False,
) -> list[dict]:
    """Search {{PROJECT_NAME}} project documentation.

    Hybrid lexical+vector retrieval. Exact-phrase queries (decision IDs,
    filenames) and natural-language queries both work. Authority-aware:
    `status='superseded'` rows are excluded by default; with
    `include_superseded=True` they return with a banner.

    Args:
        query: Natural language or exact-phrase search query.
        k: Number of results (1-20, default 10).
        status: Filter, 'draft' | 'in-progress' | 'complete' | 'superseded' | 'needs-review'.
        area: Filter to a single capability area (project-defined).
        doc_type: Filter, 'spec' | 'res' | 'str' | 'dec' | 'pol' | 'fwk'.
        include_superseded: If True, superseded chunks return with a banner.
    """
    results = _search_docs(
        query, k,
        status=status, area=area, doc_type=doc_type,
        include_superseded=include_superseded,
        caller="mcp",
    )
    return results or []


@mcp.tool()
def get_decision(query_or_id) -> dict:
    """Look up a settled decision by id, key, or fuzzy text match.

    Returns the row + a [CURRENT]/[SUPERSEDED]/[DRAFT]/[NOT FOUND] banner
    plus the supersession chain (if applicable) and up to 4 alternative
    fuzzy matches.

    Requires the `decisions` table to be populated by
    `scripts/build_decision_registry.py`. Returns `[NOT FOUND]` if the
    table is empty.
    """
    return _get_decision(query_or_id)


@mcp.tool()
def get_impact_targets(doc_or_decision: str) -> dict:
    """Return every doc affected by a change to the given source.

    Use for pre-change impact analysis: a decision is about to revise →
    surface every doc that would need to update as a consequence.

    Accepts a decision_key (resolves to its source_doc) or a doc filename
    (bare or full). Returns the matching decision row (if any) plus the
    full neighborhood from the frontmatter graph.
    """
    return _get_impact_targets(doc_or_decision)


@mcp.tool()
def get_doc_neighborhood(filename: str, include_superseded: bool = False) -> dict:
    """Return the dependency-graph neighborhood of a doc.

    Reads the authored graph (depends-on, feeds-into, also-touches,
    supersedes) from `doc_relationships`. Returns outgoing edges, inverse
    depended_on_by + feeds_from, the supersedes chain, and a warnings
    list for dangling refs.

    Args:
        filename: Bare (`<filename>`) or full (`<repo>/docs/<filename>.md`).
        include_superseded: Include superseded inverse-edge entries.
    """
    return _get_doc_neighborhood(filename, include_superseded=include_superseded)


@mcp.tool()
def get_doc_outline(filename: str, max_level: int = 3) -> dict:
    """Return the section tree of a doc, `#`/`##`/`###` headers with
    anchors and char ranges.

    Use to navigate long specs without grep-searching the body. Each
    entry's `char_start`/`char_end` slices the doc cleanly.
    """
    return _get_doc_outline(filename, max_level=max_level)


@mcp.tool()
def get_drift_report(top: int = 10,
                     signal: str | None = None,
                     area: int | None = None) -> dict:
    """Return the doc-hygiene drift queue, items flagged for review.

    Four signals (priority order):
        decision-contradict, chunk content disagrees with the registry's current_value
        dangling-ref, frontmatter ref doesn't resolve to a known doc
        stale-string, maintained-pattern sweep (project-defined)
        dep-out-of-date, `depends-on` target was committed AFTER this doc

    Args:
        top: Maximum items (default 10, max 100).
        signal: Filter to one signal name.
        area: Filter to a single area number.
    """
    return _get_drift_report(top=top, signal=signal, area=area)


@mcp.tool()
def check_index_health() -> dict:
    """Check RAG index health: per-file chunk counts, oldest/newest
    timestamps, and any files not updated in the last 24 hours.
    """
    return _check_index_health()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="{{PROJECT_NAME}} MCP Server", lifespan=lifespan)


# ---------------------------------------------------------------------------
# MCP auth middleware, protect /mcp (Streamable HTTP) and the legacy
# /sse + /messages paths so existing SSE clients keep working until they
# migrate.
# ---------------------------------------------------------------------------
_PROTECTED_PATHS = {"/mcp", "/sse", "/messages"}


@app.middleware("http")
async def mcp_auth_middleware(request: Request, call_next):
    # Strip a trailing slash so /mcp and /mcp/ are treated the same.
    # FastMCP's streamable_http_app() in mcp>=1.9 serves under /mcp/.
    if request.url.path.rstrip("/") in _PROTECTED_PATHS:
        if verify_token(request) is None:
            return JSONResponse(
                status_code=401,
                content={"detail": "Invalid or missing token"},
            )
    return await call_next(request)


@app.get("/health")
async def health():
    return {"status": "ok"}


class SearchRequest(BaseModel):
    query: str
    k: int = Field(default=10, ge=1, le=20)
    status: str | None = None
    area: int | None = None
    doc_type: str | None = None
    include_superseded: bool = False


@app.post("/search")
async def search_endpoint(request: Request, body: SearchRequest):
    auth_error = await require_auth(request)
    if auth_error:
        return auth_error
    results = _search_docs(
        body.query, body.k,
        status=body.status, area=body.area, doc_type=body.doc_type,
        include_superseded=body.include_superseded,
        caller="rest",
    )
    return {"results": results, "count": len(results)}


# ---------------------------------------------------------------------------
# OAuth 2.0 endpoints, bridge claude.ai's authorization code flow to the
# existing bearer token auth. The user pastes their bearer token into the
# /authorize form; it flows through as the access_token from /token.
# ---------------------------------------------------------------------------
AUTHORIZE_HTML = """<!DOCTYPE html>
<html>
<head><title>{{PROJECT_NAME}} MCP. Authorize</title></head>
<body style="font-family:sans-serif;max-width:420px;margin:60px auto">
  <h2>{{PROJECT_NAME}} MCP. Authorize</h2>
  <p>Paste your bearer token to connect.</p>
  <form id="f">
    <input id="tok" type="password" placeholder="Bearer token"
           style="width:100%;padding:8px;margin:8px 0" required />
    <button type="submit" style="padding:8px 16px">Authorize</button>
  </form>
  <script>
    var REDIRECT_URI = __REDIRECT_URI__;
    var STATE = __STATE__;
    document.getElementById("f").addEventListener("submit", function(e) {
      e.preventDefault();
      var tok = document.getElementById("tok").value;
      var url = REDIRECT_URI +
                "?code=" + encodeURIComponent(tok) +
                "&state=" + encodeURIComponent(STATE);
      window.location.href = url;
    });
  </script>
</body>
</html>"""


@app.get("/authorize", response_class=HTMLResponse)
async def oauth_authorize(
    response_type: str = "",
    client_id: str = "",
    redirect_uri: str = "",
    state: str = "",
):
    # JSON-encode user-controlled values before injecting into the JS so a
    # crafted redirect_uri/state cannot break out of the string literal.
    import json
    html = AUTHORIZE_HTML.replace("__REDIRECT_URI__", json.dumps(redirect_uri))
    html = html.replace("__STATE__", json.dumps(state))
    return HTMLResponse(content=html)


@app.post("/token")
async def oauth_token(
    grant_type: str = Form(""),
    code: str = Form(""),
    redirect_uri: str = Form(""),
):
    return JSONResponse(content={"access_token": code, "token_type": "bearer"})


# ---------------------------------------------------------------------------
# OAuth discovery endpoints. claude.ai probes these to find the auth and
# token endpoints before initiating the code flow. BASE_URL must be set to
# the public URL of this server (e.g. https://<your-app>.up.railway.app).
# ---------------------------------------------------------------------------
def _base_url() -> str | None:
    base = os.getenv("BASE_URL", "").rstrip("/")
    return base or None


def _base_url_or_503() -> JSONResponse | str:
    base = _base_url()
    if base is None:
        return JSONResponse(
            status_code=503,
            content={
                "detail": (
                    "BASE_URL is not configured. Set BASE_URL to the public "
                    "URL of this server to enable OAuth discovery."
                ),
            },
        )
    return base


@app.get("/.well-known/oauth-protected-resource")
async def oauth_protected_resource():
    base = _base_url_or_503()
    if isinstance(base, JSONResponse):
        return base
    return JSONResponse({
        "resource": base,
        "authorization_servers": [base],
    })


@app.get("/.well-known/oauth-authorization-server")
async def oauth_authorization_server():
    base = _base_url_or_503()
    if isinstance(base, JSONResponse):
        return base
    return JSONResponse({
        "issuer": base,
        "authorization_endpoint": f"{base}/authorize",
        "token_endpoint": f"{base}/token",
        "response_types_supported": ["code"],
        "grant_types_supported": ["authorization_code"],
    })


# Mount the MCP Streamable HTTP transport last, a root mount acts as a
# catch-all and would shadow any routes defined after it.
mcp_app = mcp.streamable_http_app()
app.mount("/", mcp_app)


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run(app, host="0.0.0.0", port=port)
