"""Semantic search over CGWB's Punjab report.

Covers what the database cannot: water quality (uranium, nitrate, salinity),
methodology, and CGWB's own commentary and recommendations.

Numeric questions must NOT come here. The database answers those exactly, with
a station and a date; retrieving prose about a number is strictly worse. The
Query Understanding agent routes between the two.
"""

from __future__ import annotations

import json
from functools import lru_cache

import httpx
import numpy as np

from app.config import BACKEND_DIR, get_settings

INDEX_DIR = BACKEND_DIR / "data" / "rag"

# Below this cosine similarity the best match is not really about the question,
# and answering from it would be worse than admitting we have nothing.
MIN_SCORE = 0.55


class IndexMissing(Exception):
    """The index has not been built yet."""


@lru_cache
def _load() -> tuple[np.ndarray, list[dict], str]:
    vectors_path = INDEX_DIR / "vectors.npy"
    chunks_path = INDEX_DIR / "chunks.json"
    if not vectors_path.exists() or not chunks_path.exists():
        raise IndexMissing(
            "RAG index not found. Build it with: "
            "python -m app.scripts.build_rag_index"
        )
    payload = json.loads(chunks_path.read_text(encoding="utf-8"))
    return np.load(vectors_path), payload["chunks"], payload["source"]


def _embed_query(text: str) -> np.ndarray:
    settings = get_settings()
    reply = httpx.post(
        f"{settings.ollama_base_url}/api/embed",
        json={"model": settings.embedding_model, "input": [text]},
        timeout=60.0,
    )
    reply.raise_for_status()
    vector = np.array(reply.json()["embeddings"][0], dtype=np.float32)
    return vector / max(float(np.linalg.norm(vector)), 1e-9)


def search(question: str, k: int = 4) -> list[dict]:
    """Return the most relevant passages, best first.

    Vectors are pre-normalised, so cosine similarity is a dot product. At 254
    chunks this is instant and needs no vector database.
    """
    vectors, chunks, source = _load()
    scores = vectors @ _embed_query(question)

    order = np.argsort(scores)[::-1][:k]
    hits = []
    for idx in order:
        score = float(scores[idx])
        if score < MIN_SCORE:
            continue
        chunk = chunks[int(idx)]
        hits.append(
            {
                # The exact string an answer should cite, so the grounding
                # check recognises it verbatim.
                "citation": f"{source}, p. {chunk['page']}",
                "page": chunk["page"],
                "score": round(score, 3),
                "text": chunk["text"],
            }
        )
    return hits


def is_available() -> bool:
    try:
        _load()
        return True
    except IndexMissing:
        return False
