"""Importer for the official English Cardfight!! Vanguard card database.

The source is used only to build the local name catalogue. It is never called
while a Telegram user is waiting for a price. The importer deliberately makes
one request at a time and handles the site's documented lazy-loaded pages.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
import re
from typing import Iterable
from urllib.parse import parse_qs, urljoin, urlparse

from bs4 import BeautifulSoup, Tag
import httpx

from scraperbot.models import CardPrint, normalise_set_code


class OfficialSourceError(RuntimeError):
    """The official card database could not supply a valid list response."""


@dataclass(frozen=True, slots=True)
class OfficialExpansion:
    id: int
    set_code: str | None
    title: str


class OfficialEnglishCardSource:
    """Read English names and print identifiers from the official public site."""

    base_url = "https://en.cf-vanguard.com"
    card_list_url = f"{base_url}/cardlist/"
    card_search_url = f"{base_url}/cardlist/cardsearch/"
    card_search_extra_url = f"{base_url}/cardlist/cardsearch_ex/"

    def __init__(self, client: httpx.AsyncClient | None = None, *, page_delay: float = 0.15) -> None:
        self.client = client
        self.page_delay = page_delay

    async def list_expansions(self) -> list[OfficialExpansion]:
        html = await self._get_text(self.card_list_url)
        expansions = self.parse_expansions(html)
        if not expansions:
            raise OfficialSourceError("The official card-list page did not contain product expansions.")
        return expansions

    async def cards_for_expansion(self, expansion: OfficialExpansion) -> list[CardPrint]:
        """Load every lazy-loaded result page for one official expansion."""
        parameters = {"expansion": expansion.id, "view": "text"}
        html = await self._get_text(self.card_search_url, params=parameters)
        cards = self.parse_card_entries(html)
        page_count = self.parse_page_count(html)
        for page in range(2, page_count + 1):
            if self.page_delay:
                await asyncio.sleep(self.page_delay)
            extra_html = await self._get_text(
                self.card_search_extra_url,
                params={**parameters, "page": page},
            )
            cards.extend(self.parse_card_entries(extra_html))
        return cards

    async def expansions_for_sets(self, set_codes: Iterable[str]) -> list[OfficialExpansion]:
        """Resolve printed set codes to official product groups."""
        wanted = {normalise_set_code(code) for code in set_codes}
        expansions = await self.list_expansions()
        selected = [
            expansion
            for expansion in expansions
            if expansion.set_code and normalise_set_code(expansion.set_code) in wanted
        ]
        found = {normalise_set_code(expansion.set_code or "") for expansion in selected}
        missing = sorted(wanted - found)
        if missing:
            raise OfficialSourceError(
                "The official English database does not list these sets yet: " + ", ".join(missing)
            )
        return selected

    async def cards_for_sets(self, set_codes: Iterable[str]) -> list[CardPrint]:
        """Load exact official product groups for the requested printed set codes."""
        selected = await self.expansions_for_sets(set_codes)
        cards: list[CardPrint] = []
        for expansion in selected:
            cards.extend(await self.cards_for_expansion(expansion))
        return cards

    @classmethod
    def parse_expansions(cls, html: str) -> list[OfficialExpansion]:
        soup = BeautifulSoup(html, "lxml")
        result: list[OfficialExpansion] = []
        seen: set[int] = set()
        for product in soup.select(".product-item"):
            link = product.select_one("a[href*='expansion=']")
            title_node = product.select_one(".title")
            if not link or not title_node:
                continue
            query = parse_qs(urlparse(link.get("href", "")).query)
            try:
                expansion_id = int(query["expansion"][0])
            except (KeyError, ValueError, IndexError):
                continue
            if expansion_id in seen:
                continue
            seen.add(expansion_id)
            title = title_node.get_text(" ", strip=True)
            result.append(OfficialExpansion(expansion_id, cls._set_code_from_title(title), title))
        return result

    @classmethod
    def parse_card_entries(cls, html: str) -> list[CardPrint]:
        soup = BeautifulSoup(html, "lxml")
        cards: list[CardPrint] = []
        # The first response has a ``#cardlist-container`` wrapper. The
        # documented ``cardsearch_ex`` follow-up endpoint returns only
        # ``<li class=\"ex-item\">`` fragments, so accept either shape.
        items = soup.select("#cardlist-container li") or soup.select("li.ex-item")
        for item in items:
            number_node = item.select_one(".number")
            name_node = item.select_one("h5")
            link = item.select_one("a[href]")
            if not number_node or not name_node or not link:
                continue
            parsed = cls._parse_card_number(number_node.get_text(" ", strip=True))
            if not parsed:
                continue
            set_code, collector_number = parsed
            name = name_node.get_text(" ", strip=True)
            if not name:
                continue
            cards.append(
                CardPrint(
                    set_code=set_code,
                    collector_number=collector_number,
                    rarity=cls._rarity_from_collector_number(collector_number),
                    english_name=name,
                    source="official-english",
                    source_url=urljoin(cls.base_url, link["href"]),
                )
            )
        return cards

    @staticmethod
    def parse_page_count(html: str) -> int:
        matched = re.search(r"var\s+max_page\s*=\s*(\d+)", html)
        return int(matched.group(1)) if matched else 1

    @staticmethod
    def _set_code_from_title(title: str) -> str | None:
        match = re.search(r"\[(?:VGE-)?([A-Z]+-[A-Z]+\d+(?:-[A-Z]+)?)\]", title)
        return match.group(1) if match else None

    @staticmethod
    def _parse_card_number(value: str) -> tuple[str, str] | None:
        compact = "".join(value.split())
        if "/" not in compact:
            return None
        set_code, collector = compact.split("/", maxsplit=1)
        if collector.endswith("EN"):
            collector = collector[:-2]
        return (set_code, collector) if set_code and collector else None

    @staticmethod
    def _rarity_from_collector_number(collector_number: str) -> str:
        """Official list rows omit rarity; prefixes such as FFR10 are unambiguous."""
        match = re.match(r"([A-Z]+)\d", collector_number.upper())
        return match.group(1) if match else ""

    async def _get_text(self, url: str, *, params: dict[str, object] | None = None) -> str:
        headers = {"User-Agent": "ScraperBot/0.1 (+local catalogue import; polite sequential requests)"}
        if self.client:
            response = await self.client.get(url, params=params, headers=headers)
        else:
            async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                response = await client.get(url, params=params, headers=headers)
        response.raise_for_status()
        html = response.text
        # ``cardsearch_ex`` intentionally returns bare ``<li>`` elements for
        # the next page, so validating for a full document here would reject a
        # successful lazy-load response. Detect the site's actual not-found
        # response instead.
        if "ページが存在しません" in html or "<title>404" in html.casefold():
            raise OfficialSourceError("The official endpoint returned a not-found page.")
        return html
