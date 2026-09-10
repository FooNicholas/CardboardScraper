"""Read exact Japanese D-Promo listings from Yuyu-Tei catalogue pages."""

from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup
import httpx

from scraperbot.models import PromoCatalogueEntry, normalise_set_code


class PromoCatalogueSourceError(RuntimeError):
    """The retailer page could not safely produce a promo catalogue batch."""


class YuyuTeiPromoCatalogueSource:
    """A polite, page-scoped reader for Yuyu-Tei D-Promo catalogue listings."""

    store_id = "yuyutei"
    base_url = "https://yuyu-tei.jp"
    _page_slug_pattern = re.compile(r"dpromo-\d+\Z")

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        request_attempts: int = 3,
    ) -> None:
        self.client = client
        self.request_attempts = request_attempts

    def page_url(self, page_slug: str) -> str:
        slug = page_slug.strip().lower()
        if not self._page_slug_pattern.fullmatch(slug):
            raise ValueError("Yuyu-Tei D-Promo pages must look like 'dpromo-1200'.")
        return f"{self.base_url}/sell/vg/s/{slug}"

    async def entries_for_page(self, page_slug: str) -> list[PromoCatalogueEntry]:
        page_url = self.page_url(page_slug)
        return self.parse_entries(page_slug, page_url, await self._get_text(page_url))

    async def list_page_slugs(self) -> list[str]:
        """Discover D-Promo navigation groups currently exposed by Yuyu-Tei."""
        # Any current D-Promo page contains the retailer's full product-range
        # selector. Keep this one stable page as the discovery seed.
        return self.parse_page_slugs(await self._get_text(self.page_url("dpromo-1200")))

    @classmethod
    def parse_page_slugs(cls, html: str) -> list[str]:
        """Extract only numeric D-Promo range controls from a catalogue page."""
        soup = BeautifulSoup(html, "lxml")
        page_slugs = {
            input_node["value"].strip().lower()
            for input_node in soup.select('input[name="vers[]"][value]')
            if cls._page_slug_pattern.fullmatch(input_node["value"].strip().lower())
        }
        return sorted(page_slugs, key=lambda slug: int(slug.removeprefix("dpromo-")))

    @classmethod
    def parse_entries(
        cls, page_slug: str, page_url: str, html: str
    ) -> list[PromoCatalogueEntry]:
        """Parse only exact D-PR reference cards, ignoring unrelated layout blocks."""
        soup = BeautifulSoup(html, "lxml")
        entries: list[PromoCatalogueEntry] = []
        seen: set[tuple[str, str]] = set()
        for item in soup.select("div.col-md"):
            reference_node = item.select_one("span")
            name_node = item.select_one("h4")
            product_link = item.select_one("a[href*='/sell/vg/card/']")
            if not reference_node or not name_node or not product_link:
                continue
            reference = "".join(reference_node.get_text(" ", strip=True).split())
            if "/" not in reference:
                continue
            raw_set_code, collector_number = reference.split("/", maxsplit=1)
            if normalise_set_code(raw_set_code) != "DPR" or not collector_number:
                continue
            japanese_name = name_node.get_text(" ", strip=True)
            if not japanese_name:
                continue
            key = (normalise_set_code(raw_set_code), collector_number.upper())
            if key in seen:
                continue
            seen.add(key)
            product_id_node = item.select_one("input.cart_cid[value]")
            entries.append(
                PromoCatalogueEntry(
                    store_id=cls.store_id,
                    page_slug=page_slug,
                    set_code=raw_set_code,
                    collector_number=collector_number,
                    japanese_name=japanese_name,
                    listing_url=urljoin(cls.base_url, product_link["href"]),
                    source_page_url=page_url,
                    product_id=product_id_node["value"] if product_id_node else None,
                )
            )
        return entries

    async def _get_text(self, url: str) -> str:
        headers = {"User-Agent": "ScraperBot/0.1 (+personal D-Promo catalogue import)"}
        response: httpx.Response | None = None
        for attempt in range(1, self.request_attempts + 1):
            try:
                if self.client:
                    response = await self.client.get(url, headers=headers)
                else:
                    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                        response = await client.get(url, headers=headers)
                if response.status_code == 404:
                    raise PromoCatalogueSourceError(f"Yuyu-Tei does not list the page {url!r}.")
                response.raise_for_status()
                break
            except PromoCatalogueSourceError:
                raise
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as error:
                if attempt == self.request_attempts:
                    raise PromoCatalogueSourceError(
                        f"Yuyu-Tei page failed after {self.request_attempts} attempts."
                    ) from error
                await asyncio.sleep(attempt)
        assert response is not None
        return response.text
