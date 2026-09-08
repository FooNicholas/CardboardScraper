"""BigWeb connector using the store's public product JSON endpoint."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Any

import httpx

from scraperbot.connectors.base import StoreConnector, StoreUnavailableError, references_card
from scraperbot.models import Availability, CardPrint, MatchConfidence, StoreOffer, normalise_set_code


class BigWebConnector(StoreConnector):
    store_id = "bigweb"
    store_name = "BigWeb"
    cardsets_url = "https://www.bigweb.co.jp/ja/assets/data/cardsets.json"
    api_base_url = "https://api.bigweb.co.jp"
    game_id = 144

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client
        self._cardsets: dict[str, int] | None = None
        self._rarities: dict[int, dict[str, int]] = {}
        self._cache_lock = asyncio.Lock()

    async def search(self, card: CardPrint) -> list[StoreOffer]:
        cardset_id = await self._cardset_id(card.set_code)
        rarity_id = await self._rarity_id(cardset_id, card.rarity)
        payload = await self._get_json(
            f"{self.api_base_url}/products",
            params={
                "game_id": self.game_id,
                "cardsets": cardset_id,
                "rarity": rarity_id,
                "is_box": 0,
            },
        )
        if not payload.get("success"):
            raise StoreUnavailableError("BigWeb returned an unsuccessful product response.")
        return self.parse_items(card, payload.get("items", []))

    async def _cardset_id(self, set_code: str) -> int:
        if self._cardsets is None:
            async with self._cache_lock:
                if self._cardsets is None:
                    payload = await self._get_json(self.cardsets_url)
                    game = next((entry for entry in payload if entry.get("id") == self.game_id), None)
                    if not game:
                        raise StoreUnavailableError("BigWeb no longer exposes its Vanguard card-set catalogue.")
                    self._cardsets = {
                        normalise_set_code(entry.get("code", "")): int(entry["id"])
                        for entry in game.get("cardsets", [])
                        if entry.get("code") and not entry.get("is_separation")
                    }
        cardset_id = self._cardsets.get(normalise_set_code(set_code))
        if cardset_id is None:
            raise StoreUnavailableError(f"BigWeb does not currently list the set {set_code}.")
        return cardset_id

    async def _rarity_id(self, cardset_id: int, rarity: str) -> int:
        if cardset_id not in self._rarities:
            async with self._cache_lock:
                if cardset_id not in self._rarities:
                    payload = await self._get_json(f"{self.api_base_url}/Cardsets/loadRarities/{cardset_id}")
                    self._rarities[cardset_id] = {
                        entry["name"].strip().upper(): int(entry["id"])
                        for entry in payload.get("rarities", [])
                        if entry.get("name")
                    }
        rarity_id = self._rarities[cardset_id].get(rarity.strip().upper())
        if rarity_id is None:
            raise StoreUnavailableError(f"BigWeb does not list rarity {rarity} for this set.")
        return rarity_id

    async def _get_json(self, url: str, *, params: Mapping[str, Any] | None = None) -> Any:
        headers = {"User-Agent": "ScraperBot/0.1 (+personal price comparison)"}
        if self.client:
            response = await self.client.get(url, params=params, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        return response.json()

    @classmethod
    def parse_items(cls, card: CardPrint, items: list[Mapping[str, Any]]) -> list[StoreOffer]:
        offers: list[StoreOffer] = []
        for item in items:
            cardset = item.get("cardset") or {}
            reference = (item.get("comment") or "").strip().split(maxsplit=1)[0]
            if not reference:
                reference = f"{cardset.get('slip', '')}/{(item.get('rarity') or {}).get('slip', '')}"
            if not references_card(card, reference):
                continue
            sold_out = bool(item.get("is_sold_out")) or int(item.get("stock_count") or 0) <= 0
            price = int(item["price"]) if not sold_out and item.get("price") is not None else None
            condition = ((item.get("condition") or {}).get("name") or "").strip() or None
            offers.append(
                StoreOffer(
                    store_id=cls.store_id,
                    store_name=cls.store_name,
                    raw_name=str(item.get("name", "")),
                    price_yen=price,
                    price_display=f"¥{price:,}" if price is not None else "Sold out",
                    availability=Availability.SOLD_OUT if sold_out else Availability.IN_STOCK,
                    listing_url=f"https://www.bigweb.co.jp/ja/products/vg/cardViewer/{item['id']}",
                    match_confidence=MatchConfidence.EXACT_PRINT,
                    condition=condition,
                )
            )
        return offers
