"""Concurrent offer comparison with a small in-memory cache."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from time import monotonic
from typing import Iterable

from scraperbot.connectors.base import StoreConnector, StoreUnavailableError
from scraperbot.models import (
    Availability,
    CardFamilyComparisonResult,
    CardPrint,
    ComparisonResult,
    FamilyOffer,
    StoreOffer,
)


@dataclass(slots=True)
class _CachedResult:
    expires_at: float
    result: ComparisonResult


class ComparisonService:
    def __init__(self, connectors: Iterable[StoreConnector], *, cache_ttl_seconds: int = 120) -> None:
        self.connectors = tuple(connectors)
        self.cache_ttl_seconds = cache_ttl_seconds
        self._cache: dict[str, _CachedResult] = {}

    async def compare(self, card: CardPrint, *, refresh: bool = False) -> ComparisonResult:
        cache_key = card.print_key
        cached = self._cache.get(cache_key)
        if not refresh and cached and cached.expires_at > monotonic():
            return cached.result

        results = await asyncio.gather(
            *(connector.search(card) for connector in self.connectors),
            return_exceptions=True,
        )
        offers: list[StoreOffer] = []
        no_active_listing: list[str] = []
        unavailable: list[str] = []
        failed: list[str] = []
        for connector, outcome in zip(self.connectors, results, strict=True):
            if isinstance(outcome, StoreUnavailableError):
                unavailable.append(connector.store_name)
            elif isinstance(outcome, Exception):
                failed.append(connector.store_name)
            else:
                if outcome:
                    offers.extend(outcome)
                else:
                    no_active_listing.append(connector.store_name)

        result = ComparisonResult(
            card=card,
            offers=tuple(sorted(offers, key=self._offer_sort_key)),
            no_active_listing_stores=tuple(no_active_listing),
            unavailable_stores=tuple(unavailable),
            failed_stores=tuple(failed),
        )
        self._cache[cache_key] = _CachedResult(monotonic() + self.cache_ttl_seconds, result)
        return result

    async def compare_family(
        self, selected_card: CardPrint, printings: Iterable[CardPrint], *, refresh: bool = False
    ) -> CardFamilyComparisonResult:
        """Compare verified reprints concurrently and sort offers by live price.

        Every connector still receives one exact selected printing at a time;
        this method only aggregates those exact results after they return.
        """
        unique_printings = tuple(
            {
                card.print_key: card
                for card in printings
            }.values()
        )
        results = await asyncio.gather(
            *(self.compare(card, refresh=refresh) for card in unique_printings)
        )
        offers = [FamilyOffer(result.card, offer) for result in results for offer in result.offers]
        return CardFamilyComparisonResult(
            selected_card=selected_card,
            printings=unique_printings,
            offers=tuple(sorted(offers, key=self._family_offer_sort_key)),
        )

    def invalidate(self, card: CardPrint | None = None) -> None:
        if card:
            self._cache.pop(card.print_key, None)
        else:
            self._cache.clear()

    @staticmethod
    def _offer_sort_key(offer: StoreOffer) -> tuple[int, int, str]:
        availability_rank = 0 if offer.availability == Availability.IN_STOCK else 1
        price_rank = offer.price_yen if offer.price_yen is not None else 10**12
        return availability_rank, price_rank, offer.store_name.casefold()

    @classmethod
    def _family_offer_sort_key(cls, family_offer: FamilyOffer) -> tuple[int, int, str, str]:
        offer = family_offer.offer
        availability_rank, price_rank, store_name = cls._offer_sort_key(offer)
        return availability_rank, price_rank, family_offer.card.display_code, store_name
