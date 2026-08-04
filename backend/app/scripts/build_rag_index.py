"""Build the document index for RAG over CGWB's Punjab report.

    python -m app.scripts.build_rag_index

The structured database answers "how much water is there". It holds no water
quality data at all, so questions about drinking safety, uranium, nitrate or
salinity had no source. Those answers live in the narrative chapters of the
report, which is what this indexes.

Deliberately NOT indexed: the numeric annexures. Those tables are already in
Postgres as exact, citable rows, and retrieving prose *about* a number is
strictly worse than querying the number.

The built index is committed, so the pipeline runs without the 7 MB PDF.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import httpx
import numpy as np

from app.config import BACKEND_DIR, get_settings

# Chapters 1-6: introduction, water levels, resources, quality, recommendations.
# Page 115 onward is Annexure I-V, all of it already in the database.
FIRST_PAGE = 9
LAST_PAGE = 114

CHUNK_CHARS = 900
OVERLAP_CHARS = 150
MIN_CHUNK_CHARS = 120

INDEX_DIR = BACKEND_DIR / "data" / "rag"
DEFAULT_PDF = BACKEND_DIR / "data" / "raw" / "cgwb_punjab_2024.pdf"

SOURCE_LABEL = "CGWB, Ground Water Resources of Punjab 2024"


def clean(text: str) -> str:
    """Collapse the whitespace pypdf leaves behind, keep sentence structure."""
    text = text.replace("–", "-").replace("’", "'")
    text = re.sub(r"Ground Water Resources of Punjab\s*.\s*2024", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def chunk_page(text: str) -> list[str]:
    """Split one page into overlapping windows, preferring sentence breaks."""
    text = clean(text)
    if len(text) < MIN_CHUNK_CHARS:
        return []

    chunks, start = [], 0
    while start < len(text):
        end = start + CHUNK_CHARS
        if end < len(text):
            # Prefer to break at a sentence end inside the last 200 chars.
            window = text[start:end]
            cut = max(window.rfind(". "), window.rfind(".\n"))
            if cut > CHUNK_CHARS - 200:
                end = start + cut + 1
        piece = text[start:end].strip()
        if len(piece) >= MIN_CHUNK_CHARS:
            chunks.append(piece)
        if end >= len(text):
            break
        start = end - OVERLAP_CHARS
    return chunks


def embed(texts: list[str], batch: int = 16) -> np.ndarray:
    """Embed with the local model. Free, offline, no API key."""
    settings = get_settings()
    vectors: list[list[float]] = []
    for i in range(0, len(texts), batch):
        window = texts[i : i + batch]
        reply = httpx.post(
            f"{settings.ollama_base_url}/api/embed",
            json={"model": settings.embedding_model, "input": window},
            timeout=300.0,
        )
        reply.raise_for_status()
        vectors.extend(reply.json()["embeddings"])
        print(f"  embedded {min(i + batch, len(texts))}/{len(texts)}", end="\r")
    print()

    matrix = np.array(vectors, dtype=np.float32)
    # Normalise once so search is a plain dot product.
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    return matrix / np.clip(norms, 1e-9, None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    args = parser.parse_args()

    if not args.pdf.exists():
        sys.exit(
            f"ERROR: {args.pdf} not found.\n"
            f"Download it from cgwb.gov.in (see README) or pass --pdf."
        )

    try:
        from pypdf import PdfReader
    except ImportError:
        sys.exit("ERROR: pypdf is required to build the index (pip install pypdf).")

    reader = PdfReader(str(args.pdf))
    records: list[dict] = []
    for page_no in range(FIRST_PAGE, min(LAST_PAGE, len(reader.pages)) + 1):
        text = reader.pages[page_no - 1].extract_text() or ""
        for piece in chunk_page(text):
            records.append({"page": page_no, "text": piece})

    if not records:
        sys.exit("ERROR: no text extracted - is this the right PDF?")

    print(f"{len(records)} chunks from pages {FIRST_PAGE}-{LAST_PAGE}")
    vectors = embed([r["text"] for r in records])

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(INDEX_DIR / "vectors.npy", vectors)
    (INDEX_DIR / "chunks.json").write_text(
        json.dumps(
            {"source": SOURCE_LABEL, "model": get_settings().embedding_model, "chunks": records},
            indent=1,
        ),
        encoding="utf-8",
    )
    size = (INDEX_DIR / "vectors.npy").stat().st_size / 1024
    print(f"wrote {INDEX_DIR} ({vectors.shape[0]} x {vectors.shape[1]}, {size:.0f} KB)")


if __name__ == "__main__":
    main()
