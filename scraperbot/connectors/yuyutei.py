"""Yuyu-Tei connector with exact card-print matching and no live translation."""

from __future__ import annotations

from collections.abc import Mapping
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag
import httpx

from scraperbot.connectors.base import StoreConnector, StoreUnavailableError, price_from_text, references_card
from scraperbot.models import Availability, CardPrint, MatchConfidence, StoreOffer


class YuyuTeiConnector(StoreConnector):
    store_id = "yuyutei"
    store_name = "Yuyu-Tei"
    base_url = "https://yuyu-tei.jp"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self.client = client

    async def search(self, card: CardPrint) -> list[StoreOffer]:
        url = f"{self.base_url}/sell/vg/s/{card.set_code.lower()}"
        headers = {"User-Agent": "ScraperBot/0.1 (+personal price comparison)"}
        if self.client:
            response = await self.client.get(url, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
                response = await client.get(url, headers=headers)
        if response.status_code == 404:
            raise StoreUnavailableError(f"Yuyu-Tei does not list the set {card.set_code}.")
        response.raise_for_status()
        return self.parse_html(card, response.text)

    @classmethod
    def parse_html(cls, card: CardPrint, page_content: str) -> list[StoreOffer]:
        soup = BeautifulSoup(page_content, "lxml")
        offers: list[StoreOffer] = []
        for item in soup.select("div.col-md"):
            name_heading = item.select_one("h4")
            price_element = item.select_one("strong")
            if not name_heading or not price_element:
                continue
            item_text = item.get_text(" ", strip=True)
            if not cls._contains_print_reference(card, item_text):
                continue
            card_link = item.select_one("a[href*='/sell/vg/card/']")
            stock_text = item_text
            price = price_from_text(price_element.get_text(" ", strip=True))
            stock_zero = "在庫" in stock_text and any(marker in stock_text for marker in ("在庫 : 0", "在庫：0", "在庫なし"))
            availability = Availability.SOLD_OUT if stock_zero else Availability.IN_STOCK
            offers.append(
                StoreOffer(
                    store_id=cls.store_id,
                    store_name=cls.store_name,
                    raw_name=name_heading.get_text(" ", strip=True),
                    price_yen=price if availability == Availability.IN_STOCK else None,
                    price_display=f"¥{price:,}" if price is not None and availability == Availability.IN_STOCK else "Sold out",
                    availability=availability,
                    listing_url=urljoin(cls.base_url, card_link["href"]) if card_link else None,
                    match_confidence=MatchConfidence.EXACT_PRINT,
                )
            )
        return offers

    @staticmethod
    def _contains_print_reference(card: CardPrint, text: str) -> bool:
        candidates = re.findall(r"[A-Za-z0-9-]+/[A-Za-z0-9-]+", text)
        return any(references_card(card, candidate) for candidate in candidates)
