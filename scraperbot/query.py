"""Shared parsing for user-facing card-name queries."""

from __future__ import annotations

from typing import Final


KNOWN_RARITIES: Final[frozenset[str]] = frozenset(
    {
        "C",
        "R",
        "RR",
        "RRR",
        "SR",
        "FR",
        "FFR",
        "DSR",
        "SEC",
        "SER",
        "EX",
        "EXRRR",
        "SNR",
    }
)


def parse_name_query(raw_query: str) -> tuple[str, str | None]:
    """Split an optional trailing rarity from a user-facing name query."""
    words = raw_query.strip().split()
    if len(words) > 1 and words[-1].upper() in KNOWN_RARITIES:
        return " ".join(words[:-1]), words[-1].upper()
    return " ".join(words), None
