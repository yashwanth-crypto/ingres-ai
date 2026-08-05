"""Deterministic grounding checks - no LLM involved.

The Verification Agent (7.4) asks a model to fact-check another model. That
works, but it fails exactly when you need it most: a small local model approved
a draft citing "Kot Shamir" (a Bathinda station) as the source for a Ludhiana
figure, and attributed a non-CGWB threshold to CGWB.

These checks are pure Python over the retrieved data, so they cannot
hallucinate. They run before the LLM verifier and their findings are merged
with its issues. Defense in depth: the model catches nuance, this catches
invented names and numbers.
"""

from __future__ import annotations

import re

from app.scripts.districts import CANONICAL_DISTRICTS, variants_of

# Sources an answer may legitimately name without them appearing as data values.
ALLOWED_SOURCES = {"cgwb", "punjab", "india", "district", "average", "mean"}

# Tolerance for a cited number matching a value in the data. Generous enough
# that sensible rounding passes, tight enough that a wrong figure does not.
ABS_TOLERANCE = 0.055

# Keys whose values measure a particular quantity. Check 2 asks only whether a
# figure appears in the data at all, which is not enough: every number in a
# projection answer is in the data somewhere, and the model still stated the
# number of years as though it were a depth.
DEPTH_KEYS = frozenset(
    {"value_m", "district_mean_m", "current_depth_m", "reference_depth_m"}
)
RATE_KEYS = frozenset({"rate_m_per_year", "current_rate_m_per_year"})
DURATION_KEYS = frozenset({"years_to_reference_depth", "years_analyzed"})

# A figure written with a unit, and the quantity it therefore has to match.
# Rate is tested before depth, and depth refuses to match anything followed by
# "/year" or "per year", so "0.504 m/year" is never read as a depth.
UNIT_CHECKS = (
    (
        "rate",
        r"(?<![\d.])(-?\d+(?:\.\d+)?)\s*(?:m|met(?:re|er)s?)\s*(?:/|per\s+)(?:year|yr|annum)",
        "a rate in metres per year",
    ),
    (
        "depth",
        r"(?<![\d.])(-?\d+(?:\.\d+)?)\s*(?:m|met(?:re|er)s?)\b(?!\s*(?:/|per\b))",
        "a depth in metres",
    ),
    (
        "duration",
        r"(?<![\d.])(-?\d+(?:\.\d+)?)\s*(?:years?|yrs?)\b",
        "a number of years",
    ),
)


def _collect_strings(node, out: set[str]) -> None:
    if isinstance(node, dict):
        for v in node.values():
            _collect_strings(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_strings(v, out)
    elif isinstance(node, str):
        out.add(node.strip().lower())


def _collect_numbers(node, out: set[float]) -> None:
    if isinstance(node, dict):
        for v in node.values():
            _collect_numbers(v, out)
    elif isinstance(node, list):
        for v in node:
            _collect_numbers(v, out)
    elif isinstance(node, bool):
        pass
    elif isinstance(node, (int, float)):
        out.add(float(node))
    elif isinstance(node, str):
        # Dates carry numbers an answer may legitimately cite (2024-01-01).
        for part in re.findall(r"-?\d+(?:\.\d+)?", node):
            try:
                out.add(float(part))
            except ValueError:
                pass


def _typed_numbers(node, out: dict[str, set[float]]) -> None:
    """Collect figures by what they measure, not merely by value."""
    if isinstance(node, dict):
        # A ranked row carries its unit as data rather than in a telling key
        # name, so classify it from that.
        unit = node.get("unit")
        value = node.get("value")
        if isinstance(unit, str) and isinstance(value, (int, float)):
            out["rate" if "/year" in unit else "depth"].add(float(value))

        for key, item in node.items():
            if isinstance(item, (int, float)) and not isinstance(item, bool):
                if key in DEPTH_KEYS:
                    out["depth"].add(float(item))
                elif key in RATE_KEYS:
                    out["rate"].add(float(item))
                elif key in DURATION_KEYS:
                    out["duration"].add(float(item))
            _typed_numbers(item, out)
    elif isinstance(node, list):
        for item in node:
            _typed_numbers(item, out)


def _number_supported(value: float, known: set[float]) -> bool:
    for k in known:
        if abs(k - value) <= ABS_TOLERANCE:
            return True
        # Accept a sensibly rounded citation of a longer figure.
        for places in (0, 1, 2):
            if round(k, places) == value:
                return True
    return False


def grounding_issues(draft: str, raw_data: dict) -> list[str]:
    """Return problems found by comparing the draft against the data only."""
    issues: list[str] = []

    known_strings: set[str] = set()
    _collect_strings(raw_data, known_strings)
    known_numbers: set[float] = set()
    _collect_numbers(raw_data, known_numbers)

    # --- 1. Citations in parentheses must name something in the data ---
    for inner in re.findall(r"\(([^)]{2,120})\)", draft):
        for token in re.split(r"[,;]", inner):
            # "CGWB 2024" and "CGWB, 2024" are the same source; drop the year
            # before deciding whether the name is one we recognise.
            token = re.sub(r"\b(19|20)\d{2}\b", "", token).strip(" .,;-")
            if not token or token.lower() in ALLOWED_SOURCES:
                continue
            if re.fullmatch(r"[\d\s./-]+", token):  # a date or bare number
                continue
            # Only proper-noun-shaped phrases are citations. A parenthetical
            # like "(as projected by the median trend across 75 stations)" is
            # prose, and flagging it as an invented source is a false positive.
            if not token[0].isupper() or len(token.split()) > 5:
                continue
            # Must appear inside some string in the data (station names,
            # districts, categories and notes all live there).
            needle = token.lower()
            if not any(needle in s for s in known_strings):
                issues.append(
                    f"Citation {token!r} does not appear anywhere in the "
                    f"retrieved data - it may be invented or belong to a "
                    f"different district."
                )

    # --- 2. Every number in the draft must be supported ---
    # Strip ISO dates first: "2024-01-01" would otherwise tokenise as 2024,
    # -01, -01 and report two phantom negative figures.
    prose = re.sub(r"\d{4}-\d{2}-\d{2}", " ", draft)
    # A "-" only counts as a minus sign when it does not follow a digit, so
    # ranges like "5-9 blocks" are not read as negative numbers either.
    for raw in re.findall(r"(?<![\d.])-?\d+(?:\.\d+)?", prose):
        value = float(raw)
        if 1900 <= value <= 2100 and "." not in raw:
            continue  # a year
        if not _number_supported(value, known_numbers):
            issues.append(
                f"The figure {raw} does not match any value in the retrieved "
                f"data."
            )

    # --- 3. The draft must not discuss a district the data does not cover ---
    # Catches the mirror image of an invented citation: a real station quoted
    # under the wrong district's name.
    for district in CANONICAL_DISTRICTS:
        if not re.search(rf"\b{re.escape(district)}\b", draft, re.IGNORECASE):
            continue
        # Match any spelling the data might use, not just the canonical one -
        # the CGWB report writes "Bhatinda" for Bathinda.
        spellings = variants_of(district) | {district.lower()}
        if not any(s in text for text in known_strings for s in spellings):
            issues.append(
                f"The draft discusses {district}, but the retrieved data "
                f"does not cover that district."
            )

    # --- 4. A threshold the data flags as non-official must not be credited
    #        to CGWB ---
    projection = raw_data.get("projection") or {}
    if projection.get("threshold_caveat"):
        depth = projection.get("reference_depth_m")
        if depth is not None:
            pattern = rf"{depth:g}\s*(?:m|metre|meter)[^.]{{0,40}}\(?\s*CGWB"
            if re.search(pattern, draft, re.IGNORECASE):
                issues.append(
                    f"The draft attributes the {depth:g} m reference depth to "
                    f"CGWB. The data states it is a practical pumping limit, "
                    f"not a CGWB threshold."
                )

    # --- 5. A projected arrival year must be the year the data computed ---
    # Check 2 exempts every 1900-2100 integer, because citations legitimately
    # carry years ("CGWB, 2024"). That exemption is a hole: asked how long until
    # Ludhiana reaches 30 m, the draft said "approximately 20 years (2034)" when
    # the projection gives 2044, and nothing objected - on the one question
    # where the year is the headline. A year *after* the last reading cannot be
    # a citation, so the only thing it can be is the projection's arrival year.
    projected_year = projection.get("projected_year")
    from_year = projection.get("from_year")
    if projected_year and from_year:
        for raw in re.findall(r"(?<![\d.])((?:19|20)\d{2})\b", prose):
            year = int(raw)
            # One year of slack: the projection lands mid-year, and rounding it
            # either way is a fair reading rather than a fabrication.
            if year > from_year and abs(year - projected_year) > 1:
                issues.append(
                    f"The draft gives {year} as the year the "
                    f"{projection.get('reference_depth_m'):g} m reference depth "
                    f"is reached, but the projection gives {projected_year}."
                )

    # --- 6. A figure written with a unit must match a value of that unit ---
    # Check 2 only asks whether a figure appears in the data at all. In a
    # projection answer every figure does, so "projected to reach a reference
    # depth of 20.1 metres" passed: 20.1 is real, but it is the number of
    # years, and the depth is 30. Being in the data is not the same as
    # measuring the thing the sentence says it measures.
    #
    # Skipped for report-backed answers. Those are grounded in prose whose
    # passages quote figures of every kind, so there is no typed set to check
    # against and this would flag legitimate quotation.
    if not raw_data.get("passages"):
        typed: dict[str, set[float]] = {"depth": set(), "rate": set(), "duration": set()}
        _typed_numbers(raw_data, typed)

        for kind, pattern, noun in UNIT_CHECKS:
            known = typed[kind]
            if not known:
                continue  # nothing of this kind was retrieved; nothing to say
            for raw in re.findall(pattern, prose):
                if not _number_supported(float(raw), known):
                    issues.append(
                        f"The draft states {raw} as {noun}, but no such value "
                        f"was retrieved - it may be a figure of a different "
                        f"kind restated with the wrong unit."
                    )

    # De-duplicate while preserving order.
    seen, unique = set(), []
    for issue in issues:
        if issue not in seen:
            seen.add(issue)
            unique.append(issue)
    return unique
