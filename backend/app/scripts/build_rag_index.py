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

WHAT EACH CHUNK CARRIES, AND WHY
--------------------------------
The first version stored `{page, text}` and nothing else. That is what made a
Punjab-wide salinity figure attributable to Bathinda: the model received a
passage with nothing on it saying what it was scoped to. Every chunk now
declares its chapter, its section, the districts it names, and whether it is
about those districts or about the state as a whole.
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
from app.scripts.districts import CANONICAL_DISTRICTS, variants_of

# The report's own page numbering runs nine behind the PDF's: PDF page 10 is
# printed page 1, and it holds through to the end of the body. Citations quote
# the printed number, because that is the one a reader opening the report can
# actually turn to. The first version cited the PDF index, so every citation
# pointed nine pages past its source.
PAGE_OFFSET = 9

# Printed pages 1-78 are the report proper. 79-90 are appendices - government
# notifications and the minutes of committee meetings. 91 onward are plates and
# figures, whose extracted "text" is axis labels: "FIGURE-7 / 75.18% / 2.61%".
# The first version indexed through printed 105, so a quarter of the corpus was
# notifications and chart tick marks competing with the chapters for retrieval.
FIRST_PRINTED_PAGE = 1
LAST_PRINTED_PAGE = 78

CHUNK_CHARS = 900
OVERLAP_CHARS = 150
MIN_CHUNK_CHARS = 120

# Below this fraction of real words, a chunk is a table that survived text
# extraction - "15 Muktsar 33 10(30%) 13(39%) 8(24%)". It cannot answer a
# question in prose, and it brings a crowd of numbers with it.
MIN_WORDINESS = 0.45

# A passage naming more districts than this is surveying the state, not
# reporting on a place. One chunk names seventeen of the twenty-three; treating
# it as local to each of them would hand a Bathinda question a passage that is
# no more about Bathinda than about Moga.
BROAD_DISTRICT_COUNT = 6

INDEX_DIR = BACKEND_DIR / "data" / "rag"
DEFAULT_PDF = BACKEND_DIR / "data" / "raw" / "cgwb_punjab_2024.pdf"

SOURCE_LABEL = "CGWB, Ground Water Resources of Punjab 2024"

# Read from the report's own contents pages (PDF 5-7) and checked against the
# chapter headings in the body. Printed page each chapter starts on.
CHAPTERS: tuple[tuple[int, str], ...] = (
    (1, "Chapter 1 - Introduction"),
    (4, "Chapter 2 - Hydrogeological conditions of Punjab"),
    (12, "Chapter 3 - Ground water resources estimation methodology"),
    (39, "Chapter 4 - Procedure followed in the present assessment"),
    (42, "Chapter 5 - Computation of ground water resources estimation"),
    (46, "Chapter 6 - Ground water quality"),
    (78, "Chapter 7 - Conclusions"),
)

# Chapter 6's subsections. These are the ones quality questions actually want -
# a question about uranium should be able to outrank a chapter of prose that
# merely mentions it.
SUBSECTIONS: tuple[tuple[int, str], ...] = (
    (48, "Ground water quality scenario"),
    (49, "Quality assessment in unconfined aquifers - electrical conductivity"),
    (53, "Nitrate"),
    (57, "Fluoride"),
    (62, "Arsenic"),
    (66, "Iron"),
    (70, "Uranium"),
    (74, "Quality summary"),
)

# One matcher per district, covering every spelling CGWB uses - the report
# writes "Bhatinda" for Bathinda.
_DISTRICT_PATTERNS = {
    district: re.compile(
        r"\b(?:" + "|".join(sorted(map(re.escape, variants_of(district)), key=len, reverse=True)) + r")\b",
        re.IGNORECASE,
    )
    for district in CANONICAL_DISTRICTS
    if variants_of(district)
}


def chapter_of(page: int) -> str:
    label = CHAPTERS[0][1]
    for start, name in CHAPTERS:
        if page >= start:
            label = name
    return label


def section_of(page: int) -> str:
    """The most specific heading covering this page."""
    chapter = chapter_of(page)
    if not chapter.startswith("Chapter 6"):
        return chapter
    label = chapter
    for start, name in SUBSECTIONS:
        if page >= start:
            label = name
    return label


def districts_in(text: str) -> list[str]:
    return sorted(d for d, pattern in _DISTRICT_PATTERNS.items() if pattern.search(text))


def wordiness(text: str) -> float:
    """Fraction of tokens that are actually words rather than table cells."""
    tokens = text.split()
    if not tokens:
        return 0.0
    real = sum(1 for t in tokens if re.search(r"[A-Za-z]{3,}", t))
    return real / len(tokens)


def clean(text: str, printed_page: int) -> str:
    """Collapse the whitespace pypdf leaves behind, keep sentence structure."""
    text = text.replace("–", "-").replace("’", "'").replace("�", "-")
    text = re.sub(r"Ground Water Resources of Punjab\s*.\s*2024", " ", text)
    # The running header is followed by the page number on its own line, which
    # otherwise opens the chunk with a bare integer: "18 \n\nThe first method".
    text = re.sub(rf"^\s*{printed_page}\s*$", " ", text, flags=re.MULTILINE)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip()


def chunk_page(text: str, printed_page: int) -> list[str]:
    """Split one page into overlapping windows, preferring sentence breaks."""
    text = clean(text, printed_page)
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


def build_records(reader) -> tuple[list[dict], int]:
    """Chunk the narrative chapters. Returns the records and how many were
    dropped as tables."""
    records: list[dict] = []
    dropped = 0

    for printed in range(FIRST_PRINTED_PAGE, LAST_PRINTED_PAGE + 1):
        pdf_index = printed + PAGE_OFFSET
        if pdf_index > len(reader.pages):
            break
        text = reader.pages[pdf_index - 1].extract_text() or ""
        for piece in chunk_page(text, printed):
            if wordiness(piece) < MIN_WORDINESS:
                dropped += 1
                continue
            named = districts_in(piece)
            records.append(
                {
                    "page": printed,
                    "pdf_page": pdf_index,
                    "chapter": chapter_of(printed),
                    "section": section_of(printed),
                    "districts": named,
                    # Whether the passage is about the districts it names or
                    # about Punjab as a whole. A statewide figure presented as
                    # a district's is the misattribution this exists to stop.
                    "scope": (
                        "district"
                        if named and len(named) <= BROAD_DISTRICT_COUNT
                        else "statewide"
                    ),
                    "text": piece,
                }
            )
    return records, dropped


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf", type=Path, default=DEFAULT_PDF)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Chunk and report, without embedding or writing the index.",
    )
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
    records, dropped = build_records(reader)

    if not records:
        sys.exit("ERROR: no text extracted - is this the right PDF?")

    print(
        f"{len(records)} chunks from printed pages "
        f"{FIRST_PRINTED_PAGE}-{LAST_PRINTED_PAGE} "
        f"(PDF {FIRST_PRINTED_PAGE + PAGE_OFFSET}-{LAST_PRINTED_PAGE + PAGE_OFFSET})"
    )
    print(f"  {dropped} chunks dropped as tables rather than prose")
    scoped = sum(1 for r in records if r["scope"] == "district")
    named = sum(1 for r in records if r["districts"])
    print(
        f"  {scoped} scoped to a district, {len(records) - scoped} statewide "
        f"({named - scoped} of those name districts but survey too many to be local)"
    )
    sections = {r["section"] for r in records}
    print(f"  {len(sections)} distinct sections")

    if args.dry_run:
        print("\ndry run - nothing embedded, nothing written")
        return

    vectors = embed([r["text"] for r in records])

    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    np.save(INDEX_DIR / "vectors.npy", vectors)
    (INDEX_DIR / "chunks.json").write_text(
        json.dumps(
            {
                "source": SOURCE_LABEL,
                "model": get_settings().embedding_model,
                "page_offset": PAGE_OFFSET,
                "pages": [FIRST_PRINTED_PAGE, LAST_PRINTED_PAGE],
                "chunks": records,
            },
            indent=1,
        ),
        encoding="utf-8",
    )
    size = (INDEX_DIR / "vectors.npy").stat().st_size / 1024
    print(f"wrote {INDEX_DIR} ({vectors.shape[0]} x {vectors.shape[1]}, {size:.0f} KB)")


if __name__ == "__main__":
    main()
