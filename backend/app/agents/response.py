"""Agent 7.5 - Response.

Writes the user-facing answer from verified data only.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.services.llm_client import (
    EFFORT_REASONING,
    parse_structured,
    slim_for_prompt,
)


class Citation(BaseModel):
    station: str = Field(description="Station or source the figure came from")
    date: str = Field(description="Date or assessment year of the figure")


class DraftAnswer(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    needs_chart: bool = False
    needs_map: bool = False


SYSTEM = """Write a clear, direct answer to the user's groundwater question using ONLY the data provided.

Rules:
- Every number must be followed by its source in parentheses, e.g. "12.4 m (Kot Shamir, 2024-01-01)" or "over-exploited (CGWB 2024)".
- Never state a number that does not appear in the data. If the data does not answer the question, say so plainly.
- Water levels are depth below ground: a LARGER number means a DEEPER water table, which is worse. A rising rate means the water table is falling.
- If the data includes a confidence_note or threshold_caveat, reflect its substance in the answer. Do not present a projection as a certainty.
- If a district has a risk category but no water level readings, say exactly that.
- Set needs_chart when the data covers several years or a trend; set needs_map when it covers several districts.
- Be concise. Two or three sentences is usually enough. Do not add caveats beyond those the data supports."""

STRICT_SUFFIX = """

A previous draft was rejected by a verification step for these problems:
{issues}

Rewrite it. State only figures that appear verbatim in the data. If you cannot support a claim, leave it out."""


def response_agent(
    raw_data: dict, question: str, issues: list[str] | None = None
) -> DraftAnswer:
    """Draft an answer. Pass `issues` to retry under stricter instructions."""
    system = SYSTEM
    if issues:
        system += STRICT_SUFFIX.format(issues="\n".join(f"- {i}" for i in issues))

    payload = json.dumps(slim_for_prompt(raw_data), indent=1, default=str)
    return parse_structured(
        system,
        f"Question: {question}\n\nData:\n{payload}",
        DraftAnswer,
        effort=EFFORT_REASONING,
    )
