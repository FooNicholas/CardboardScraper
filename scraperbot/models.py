"""Domain objects shared by the catalogue, connectors, and bot."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import re
import unicodedata


def normalise_text(value: str) -> str:
    """Return a punctuation-insensitive form suitable for user search."""
    value = unicodedata.normalize("NFKC", value).casefold()
    value = "".join(char if char.isalnum() else " " for char in value)
    return " ".join(value.split())


def normalise_set_code(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def normalise_collector_number(value: str) -> str:
    cleaned = re.sub(r"\s+", "", value).upper()
    return cleaned.zfill(3) if cleaned.isdigit() else cleaned


@dataclass(frozen=True, slots=True)
class CardPrint:
    """A specific printed card version, identified independently of its name."""

    set_code: str
    collector_number: str
    rarity: str
    english_name: str
    japanese_name: str | None = None
    aliases: tuple[str, ...] = ()
    source: str = "manual"
    source_url: str | None = None
    id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "set_code", normalise_set_code(self.set_code))
        object.__setattr__(self, "collector_number", normalise_collector_number(self.collector_number))
        object.__setattr__(self, "rarity", self.rarity.strip().upper())
        object.__setattr__(self, "english_name", self.english_name.strip())
        object.__setattr__(self, "japanese_name", self.japanese_name.strip() if self.japanese_name else None)
        object.__setattr__(self, "aliases", tuple(alias.strip() for alias in self.aliases if alias.strip()))

    @property
    def print_key(self) -> str:
        suffix = f":{self.rarity}" if self.rarity else ""
        return f"{self.set_code}/{self.collector_number}{suffix}"

    @property
    def display_code(self) -> str:
        base = f"{self.set_code}/{self.collector_number}"
        return f"{base} · {self.rarity}" if self.rarity else base

    @property
    def search_terms(self) -> tuple[str, ...]:
        return (self.english_name, *self.aliases)


@dataclass(frozen=True, slots=True)
class JapaneseCardPrint:
    """An official Japanese printing, kept even before an English name exists."""

    set_code: str
    collector_number: str
    rarity: str
    japanese_name: str
    source_url: str
    id: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "set_code", normalise_set_code(self.set_code))
        object.__setattr__(self, "collector_number", normalise_collector_number(self.collector_number))
        object.__setattr__(self, "rarity", self.rarity.strip().upper())
        object.__setattr__(self, "japanese_name", self.japanese_name.strip())


@dataclass(frozen=True, slots=True)
class PromoCatalogueEntry:
    """A retailer's verified location for one Japanese promo printing.

    It deliberately contains no English card name. Retailer discovery and
    canonical Japanese-card identity are separate from the later name-mapping
    review process.
    """

    store_id: str
    page_slug: str
    set_code: str
    collector_number: str
    japanese_name: str
    listing_url: str
    source_page_url: str
    product_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "store_id", self.store_id.strip().lower())
        object.__setattr__(self, "page_slug", self.page_slug.strip().lower())
        object.__setattr__(self, "set_code", normalise_set_code(self.set_code))
        object.__setattr__(self, "collector_number", normalise_collector_number(self.collector_number))
        object.__setattr__(self, "japanese_name", self.japanese_name.strip())
        object.__setattr__(self, "listing_url", self.listing_url.strip())
        object.__setattr__(self, "source_page_url", self.source_page_url.strip())
        object.__setattr__(self, "product_id", self.product_id.strip() if self.product_id else None)


@dataclass(frozen=True, slots=True)
class EnglishNameMapping:
    """A reviewed English name for an official Japanese card print."""

    set_code: str
    collector_number: str
    rarity: str
    english_name: str
    source: str
    source_url: str
    aliases: tuple[str, ...] = ()
    status: str = "provisional"

    def __post_init__(self) -> None:
        object.__setattr__(self, "set_code", normalise_set_code(self.set_code))
        object.__setattr__(self, "collector_number", normalise_collector_number(self.collector_number))
        object.__setattr__(self, "rarity", self.rarity.strip().upper())
        object.__setattr__(self, "english_name", self.english_name.strip())
        object.__setattr__(self, "aliases", tuple(alias.strip() for alias in self.aliases if alias.strip()))
        object.__setattr__(self, "status", self.status.strip().lower())


class Availability(StrEnum):
    IN_STOCK = "in_stock"
    SOLD_OUT = "sold_out"
    UNKNOWN = "unknown"


class MatchConfidence(StrEnum):
    EXACT_PRINT = "exact_print"
    EXACT_JAPANESE_NAME = "exact_japanese_name"
    EXACT_ENGLISH_NAME = "exact_english_name"
    UNMATCHED = "unmatched"


@dataclass(frozen=True, slots=True)
class StoreOffer:
    store_id: str
    store_name: str
    raw_name: str
    price_yen: int | None
    price_display: str
    availability: Availability
    listing_url: str | None
    match_confidence: MatchConfidence
    condition: str | None = None
    direction: str = "retail"
    stock_count: int | None = None


@dataclass(frozen=True, slots=True)
class ComparisonResult:
    card: CardPrint
    offers: tuple[StoreOffer, ...]
    no_active_listing_stores: tuple[str, ...] = ()
    unavailable_stores: tuple[str, ...] = ()
    failed_stores: tuple[str, ...] = ()
