"""OpenAI embedding client with batch support.

Two entry points:

    embed_text(text, client=None, sleep_after=True)
        Single-input call. Used by code paths that have one text at a
        time (e.g. the MCP server's search query embed).

    embed_batch(texts, client=None, batch_size=100)
        Multi-input call. Splits `texts` into chunks of `batch_size`
        and sends each as a single OpenAI request. Returns list of
        embeddings in the same order as `texts`. Used by the indexer
        to reduce round-trips from N to ceil(N / batch_size).

OpenAI's text-embedding-3-small accepts up to 2048 inputs per call.
We default batch_size=100, well under the limit and well under the
per-call token budget. Larger batches reduce round-trips but increase
the blast radius of a single failed call.
"""
import os
import time

from openai import OpenAI

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIMENSIONS = 1536
EMBED_DELAY_SECONDS = 0.1
DEFAULT_BATCH_SIZE = 100

_DEFAULT_CLIENT: OpenAI | None = None


def get_client() -> OpenAI:
    global _DEFAULT_CLIENT
    if _DEFAULT_CLIENT is None:
        _DEFAULT_CLIENT = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _DEFAULT_CLIENT


def embed_text(text: str, client: OpenAI | None = None,
               sleep_after: bool = True) -> list[float]:
    """Single-input embed. Sleeps EMBED_DELAY_SECONDS after by default."""
    if client is None:
        client = get_client()

    response = client.embeddings.create(
        model=EMBEDDING_MODEL,
        input=text,
        dimensions=EMBEDDING_DIMENSIONS,
    )
    embedding = response.data[0].embedding

    if sleep_after:
        time.sleep(EMBED_DELAY_SECONDS)

    return embedding


def embed_batch(texts: list[str], client: OpenAI | None = None,
                batch_size: int = DEFAULT_BATCH_SIZE,
                sleep_between_batches: bool = True) -> list[list[float]]:
    """Multi-input embed.

    Splits `texts` into chunks of `batch_size` and sends each chunk as
    a single OpenAI request. Returns embeddings in the same order as
    `texts`.

    Throughput: ~50× fewer round-trips at batch_size=100. The token
    cost is unchanged, same number of tokens, just bundled.
    """
    if not texts:
        return []
    if client is None:
        client = get_client()

    out: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        chunk = texts[i:i + batch_size]
        response = client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=chunk,
            dimensions=EMBEDDING_DIMENSIONS,
        )
        # response.data is ordered by request index per OpenAI docs.
        out.extend(item.embedding for item in response.data)
        if sleep_between_batches and i + batch_size < len(texts):
            time.sleep(EMBED_DELAY_SECONDS)

    return out


def to_pgvector(embedding: list[float]) -> str:
    """Format a list of floats as a pgvector literal: `[v1,v2,...]`."""
    return "[" + ",".join(str(x) for x in embedding) + "]"
