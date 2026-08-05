"""Semantic search over CGWB's Punjab report.

Covers what the database cannot: water quality (uranium, nitrate, salinity),
methodology, and CGWB's own commentary and recommendations.

Numeric questions must NOT come here. The database answers those exactly, with
a station and a date; retrieving prose about a number is strictly worse. The
Query Understanding agent routes between the two.

RETRIEVAL IS TWO-STAGE
----------------------
Similarity picks the candidates; a deterministic pass reorders them using what
each chunk declares about itself. A passage that names only Amritsar is a poor
answer to a question about Bathinda however close the two read in embedding
space, and that exact confusion - a Punjab-wide salinity figure attributed to
Bathinda - is the failure this stage exists to prevent.
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

# How many candidates similarity puts forward before reranking. Wide enough
# that a passage about the right district can climb from below the cut, narrow
# enough that the reranker is not inventing relevance out of noise.
CANDIDATES = 12

# A passage naming the district asked about is worth more than one that does
# not. A district-scoped passage naming only *other* districts is worth much
# less: it is about somewhere else, and quoting it is how a figure ends up
# attributed to the wrong place. Statewide passages are left alone - they are
# legitimate answers, as long as the answer does not claim they are local.
DISTRICT_MATCH_BONUS = 0.06
WRONG_DISTRICT_PENALTY = 0.12


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


def rerank(hits: list[dict], district: str | None) -> list[dict]:
    """Reorder candidates by what each chunk says it is about.

    Deterministic and separate from the search so it can be tested without a
    model or an index.
    """
    if not district:
        return sorted(hits, key=lambda h: -h["score"])

    for hit in hits:
        named = hit.get("districts") or []
        adjustment = 0.0
        # Only passages the index calls district-scoped are moved. One that
        # names seventeen districts is a survey of the state and is left where
        # similarity put it, however many times the asked-for name appears.
        if hit.get("scope") == "district":
            if district in named:
                adjustment += DISTRICT_MATCH_BONUS
            else:
                # Scoped to somewhere else entirely.
                adjustment -= WRONG_DISTRICT_PENALTY
        hit["adjusted"] = hit["score"] + adjustment

    return sorted(hits, key=lambda h: -h.get("adjusted", h["score"]))


def search(question: str, k: int = 4, district: str | None = None) -> list[dict]:
    """Return the most relevant passages, best first.

    Vectors are pre-normalised, so cosine similarity is a dot product. At this
    corpus size this is instant and needs no vector database.
    """
    vectors, chunks, source = _load()
    scores = vectors @ _embed_query(question)

    order = np.argsort(scores)[::-1][:CANDIDATES]
    hits = []
    for idx in order:
        score = float(scores[idx])
        if score < MIN_SCORE:
            continue
        chunk = chunks[int(idx)]
        hits.append(
            {
                # The exact string an answer should cite, so the grounding
                # check recognises it verbatim. The page is the report's own
                # printed number, which is the one a reader can turn to.
                "citation": f"{source}, p. {chunk['page']}",
                "page": chunk["page"],
                "section": chunk.get("section"),
                "districts": chunk.get("districts") or [],
                # Carried through to the answer: a statewide finding must not
                # be written up as though it were about one district.
                "scope": chunk.get("scope", "statewide"),
                "score": round(score, 3),
                "text": chunk["text"],
            }
        )

    return rerank(hits, district)[:k]


def is_available() -> bool:
    try:
        _load()
        return True
    except IndexMissing:
        return False
