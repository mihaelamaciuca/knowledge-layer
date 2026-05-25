---
file: 03-spec-search-api
area: 3
area-name: Engineering
type: spec
title: Search API contract
status: draft
date: 2026-05-25
depends-on:
  - 03-dec-tech-stack
feeds-into:
  - area-3-engineering
---

# Search API contract

> **Example document.** Demonstrates a `spec` doc that depends on a `dec`. `get_impact_targets("api-framework")` will return this spec because it depends on `03-dec-tech-stack`. Replace or delete when you write your own specs.

## Overview

Defines the `/search` HTTP surface the MCP server exposes for direct REST callers (in addition to the MCP tool surface). Mirrors the `search_docs` MCP tool's behavior so a human operator running curl gets the same answers an agent does.

## Inputs and outputs

**Request:** `POST /search`, content-type `application/json`, body:

```json
{
  "query": "string",
  "k": 10,
  "status": "complete | in-progress | draft | superseded | needs-review",
  "area": 3,
  "doc_type": "spec | res | str | dec | pol | fwk",
  "include_superseded": false
}
```

**Response:** `200 OK`, JSON object:

```json
{
  "results": [
    {
      "id": "<uuid>",
      "source_file": "<repo>/docs/<filename>.md",
      "section_header": "<heading>",
      "content": "<preamble + body>",
      "status": "complete",
      "git_sha": "<sha>",
      "score": 0.83
    }
  ],
  "count": 1
}
```

On error: `{"error": "<message>", "results": []}` with HTTP 200.

## Architecture

The endpoint is a thin wrapper around `src.search.search_docs`. Auth is handled by `require_auth` (bearer token via `Authorization: Bearer <MCP_TOKEN_N>`). The handler runs in the same process and pool as the MCP tools, so no separate scaling story is needed.

## Constraints

- `k` is clamped server-side to the range 1..20. The MCP tool documentation reflects the same cap.
- Embedding generation uses the model recorded in `03-dec-tech-stack` (`embedding-model` decision).
- Superseded documents are excluded by default. Setting `include_superseded=true` returns them with a `[SUPERSEDED, see <target>]` banner prepended to `content`.

## Error handling

| Condition | Status code | Response shape |
|-----------|-------------|----------------|
| Missing or invalid bearer token | 401 | `{"detail": "Invalid or missing token"}` |
| Validation error (k out of range, etc.) | 422 | FastAPI default validation envelope |
| Embedding API failure | 200 | `{"error": "embedding failed: ...", "results": []}` |
| Postgres failure | 200 | `{"error": "<message>", "results": []}` |

The choice to return 200 with an error key (rather than 5xx) lets MCP clients surface the failure in-band without retries that would compound the problem. The error path still writes a row to `query_log` so DB issues are visible in telemetry.

## Test criteria

- Round-trip a known query and verify the top hit's `source_file` matches the expected slug.
- Submit `k=0` and `k=50`; assert 422 and that the server didn't reach the embedding step in either case.
- Drop the `Authorization` header; assert 401 within 50ms.
- Set `include_superseded=true`; assert the banner is prepended on rows where `status='superseded'`.
