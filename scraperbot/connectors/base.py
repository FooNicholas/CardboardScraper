"""Shared connector protocol and exact print-reference matching helpers."""

from __future__ import annotations

from abc import ABC, abstractmethod
import re

from scraperbot.models import CardPrint, Finish, StoreOffer, finish_from_text


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


def retailer_print_reference(card: CardPrint) -> str:
    """Return the conventional hyphenated Japanese serial used by stores.

    Database keys intentionally remove punctuation so variants such as
    ``D-PR/953`` and ``DPR953`` resolve to the same print.  Store search boxes,
    however, commonly index the displayed Japanese form with its hyphens.
    """
    set_code = card.set_code
    if set_code == "DPR":
        displayed_set = "D-PR"
    else:
        matched = re.fullmatch(r"(DZ|D|V)(LBT|TTD|BT|SS|SD|TD|TB|PS|PV|VS)(\d+)", set_code)
        displayed_set = f"{matched.group(1)}-{matched.group(2)}{matched.group(3)}" if matched else set_code
    return f"{displayed_set}/{card.collector_number}"


def normalise_print_reference(value: str) -> str:
    """Make retailer variants such as ``DZ-BT16/FFR02`` comparable."""
    return re.sub(r"[^A-Za-z0-9]", "", value).upper()


def references_card(card: CardPrint, retailer_reference: str) -> bool:
    return normalise_print_reference(print_reference(card)) == normalise_print_reference(retailer_reference)


def matches_card_finish(card: CardPrint, listing_name: str) -> bool:
    """Reject a seller listing only when it explicitly names another finish.

    Unknown is deliberately permissive. A retailer may omit finish data even
    when the selected canonical print has one, and absence is not evidence of
    a standard finish.
    """
    listing_finish, _ = finish_from_text(listing_name)
    return (
        card.finish is Finish.UNKNOWN
        or listing_finish is Finish.UNKNOWN
        or card.finish is listing_finish
    )


def price_from_text(value: str) -> int | None:
    digits = re.sub(r"[^0-9]", "", value)
    return int(digits) if digits else None
