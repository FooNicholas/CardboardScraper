"""Shared connector protocol and exact print-reference matching helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
import re

from scraperbot.models import CardPrint, StoreOffer, normalise_collector_number, normalise_set_code


class StoreUnavailableError(RuntimeError):
    """The store cannot currently answer a lookup for this card."""


class StoreConnector(ABC):
    store_id: str
    store_name: str

    @abstractmethod
    async def search(self, card: CardPrint) -> list[StoreOffer]:
        """Return offers matched to exactly one selected card print."""


def print_reference(card: CardPrint) -> str:
    return f"{card.set_code}/{card.collector_number}"


def normalise_print_reference(value: str) -> str:
    """Make retailer variants such as ``DZ-BT16/FFR02`` comparable."""
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def references_card(card: CardPrint, retailer_reference: str) -> bool:
    return normalise_print_reference(print_reference(card)) == normalise_print_reference(retailer_reference)


def price_from_text(value: str) -> int | None:
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None
