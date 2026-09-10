"""Shared parsing for user-facing card-name queries."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Final

from scraperbot.models import Finish, normalise_finish


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
        "PR",
        "SIR",
    }
)


@dataclass(frozen=True, slots=True)
class NameSearchQuery:
    """A name query with optional explicit rarity and finish filters."""

    name: str
    rarities: tuple[str, ...] = ()
    finishes: tuple[Finish, ...] = ()


_RARITY_FILTER = re.compile(r"^(?:rarity|r):(?P<values>.+)$", re.IGNORECASE)
_FINISH_FILTER = re.compile(r"^(?:finish|f):(?P<values>.+)$", re.IGNORECASE)


def parse_name_query(raw_query: str) -> tuple[str, str | None]:
    """Split an optional trailing rarity from a user-facing name query."""
    words = raw_query.strip().split()
    if len(words) > 1 and words[-1].upper() in KNOWN_RARITIES:
        return " ".join(words[:-1]), words[-1].upper()
    return " ".join(words), None


def parse_name_search_query(raw_query: str) -> NameSearchQuery:
    """Parse an English name plus explicit multi-value filters.

    ``Youthberk rarity:FFR,SEC finish:holo`` works in Telegram and the web
    search API. The legacy trailing rarity shortcut (``Youthberk FFR``) stays
    supported and combines with any explicit rarity filter.
    """
    name_words: list[str] = []
    rarities: set[str] = set()
    finishes: set[Finish] = set()
    for word in raw_query.strip().split():
        rarity_match = _RARITY_FILTER.fullmatch(word)
        if rarity_match:
            values = [value.strip().upper() for value in rarity_match.group("values").split(",") if value.strip()]
            if not values:
                raise ValueError("Provide at least one rarity after rarity:.")
            rarities.update(values)
            continue
        finish_match = _FINISH_FILTER.fullmatch(word)
        if finish_match:
            values = [value.strip() for value in finish_match.group("values").split(",") if value.strip()]
            if not values:
                raise ValueError("Provide at least one finish after finish:.")
            for value in values:
                finish = normalise_finish(value)
                if finish is Finish.UNKNOWN and value.casefold() != Finish.UNKNOWN.value:
                    raise ValueError("Finish filters must be holo, standard, or unknown.")
                finishes.add(finish)
            continue
        name_words.append(word)
    name, trailing_rarity = parse_name_query(" ".join(name_words))
    if trailing_rarity:
        rarities.add(trailing_rarity)
    return NameSearchQuery(name, tuple(sorted(rarities)), tuple(sorted(finishes, key=lambda finish: finish.value)))
