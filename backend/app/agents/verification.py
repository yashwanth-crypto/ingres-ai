"""Agent 7.4 - Verification.

Checks a draft answer against the data it was supposed to be grounded in,
before the user ever sees it. This is the agent that makes the pipeline
trustworthy, so it is deliberately strict.
"""

from __future__ import annotations

import json

from pydantic import BaseModel, Field

from app.services.llm_client import (
    EFFORT_REASONING,
    parse_structured,
    slim_for_prompt,
)


class Verdict(BaseModel):
    approved: bool
    issues: list[str] = Field(default_factory=list)


SYSTEM = """Check every number in this draft answer against the source data provided.

Flag and do NOT approve if any of these hold:
- A number in the draft does not appear in the data.
- A number is attributed to the wrong station, district or date.
- The draft names a different district than the data covers.
- The draft states a projection as a certainty, or drops a caveat the data marks as important (confidence_note, threshold_caveat).
- The draft claims data exists for a district the data marks as unavailable.
- The draft reverses the meaning of depth: larger depth-to-water means a DEEPER, WORSE water table.

Rounding a figure sensibly is fine. Omitting a figure is fine. Inventing or misattributing one is not.

Respond with JSON: {"approved": bool, "issues": [str]}. Each issue names the specific problem."""


def verification_agent(draft: str, raw_data: dict) -> Verdict:
    """Return a verdict on the draft. Fails closed if the model is unreachable."""
    payload = json.dumps(slim_for_prompt(raw_data), indent=1, default=str)
    # LLMUnavailable propagates deliberately: the orchestrator must never
    # present an unverified answer as verified.
    return parse_structured(
        SYSTEM,
        f"Draft answer:\n{draft}\n\nSource data:\n{payload}",
        Verdict,
        effort=EFFORT_REASONING,
    )
