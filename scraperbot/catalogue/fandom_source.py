"""Fandom-backed provisional English mappings for Japanese-only card sets."""

from __future__ import annotations

import asyncio
from html import unescape
import re
from urllib.parse import quote

from bs4 import BeautifulSoup
import httpx

from scraperbot.catalogue.official_source import OfficialSourceError
from scraperbot.models import EnglishNameMapping, normalise_set_code


class FandomMappingSource:
    """Read trusted community English names through Fandom's public API.

    Fandom mappings are explicitly stored as ``provisional``. When Bushiroad
    publishes the card in English, the official importer wins for that print.
    """

    api_url = "https://cardfight.fandom.com/api.php"
    wiki_base_url = "https://cardfight.fandom.com/wiki/"
    known_list_pages = {
        "CP": "List of D Promo Cards",
        "DPR": "List of D Promo Cards",
    }

    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        request_attempts: int = 3,
        page_delay: float = 0.25,
    ) -> None:
        self.client = client
        self.request_attempts = request_attempts
        self.page_delay = page_delay

    async def mappings_for_set(
        self, set_code: str, *, page_title: str | None = None
    ) -> tuple[str, list[EnglishNameMapping]]:
        wanted = normalise_set_code(set_code)
        titles = (
            [page_title]
            if page_title
            else [self.known_list_pages[wanted]]
            if wanted in self.known_list_pages
            else await self._candidate_titles(self._search_term(set_code))
        )
        best_title = ""
        best_mappings: list[EnglishNameMapping] = []
        for title in titles:
            if not title:
                continue
            page_html = await self._page_html(title)
            mappings = self.parse_mappings(page_html, set_code, source_url=self._page_url(title))
            if not mappings:
                mappings = self.parse_list_mappings(page_html, set_code, source_url=self._page_url(title))
            if len(mappings) > len(best_mappings):
                best_title, best_mappings = title, mappings
            if self.page_delay:
                await asyncio.sleep(self.page_delay)
        if not best_mappings:
            raise OfficialSourceError(f"Fandom did not provide card mappings for {wanted}.")
        return best_title, best_mappings

    async def _candidate_titles(self, set_code: str) -> list[str]:
        payload = await self._get_json(
            {
                "action": "query",
                "list": "search",
                "srsearch": f'"{set_code.upper()}"',
                "srlimit": 10,
                "format": "json",
            }
        )
        return [str(row.get("title", "")) for row in payload.get("query", {}).get("search", [])]

    @staticmethod
    def _search_term(set_code: str) -> str:
        """Restore the conventional hyphen before searching Fandom titles."""
        compact = normalise_set_code(set_code)
        matched = re.fullmatch(
            r"(DZ|D)(TBP|TTD|LBT|LTD|MBX|BT|TB|SS|SD|TD|VS|PS|PV|PR)(\d+)?", compact
        )
        if not matched:
            return compact
        era, family, number = matched.groups()
        return f"{era}-{family}{number or ''}"

    async def _page_html(self, title: str) -> str:
        payload = await self._get_json({"action": "parse", "page": title, "prop": "text", "format": "json"})
        html = payload.get("parse", {}).get("text", {}).get("*")
        if not isinstance(html, str):
            raise OfficialSourceError(f"Fandom did not return a readable page for {title!r}.")
        return html

    @classmethod
    def parse_mappings(
        cls, html: str, set_code: str, *, source_url: str
    ) -> list[EnglishNameMapping]:
        wanted = normalise_set_code(set_code)
        soup = BeautifulSoup(html, "lxml")
        mappings: list[EnglishNameMapping] = []
        seen: set[str] = set()
        for table in soup.select("table"):
            header_cells = table.select("tr th")
            headers = [cls._normalise_header(cell.get_text(" ", strip=True)) for cell in header_cells]
            if not headers or "card no" not in headers or "name" not in headers:
                continue
            number_index = headers.index("card no")
            name_index = headers.index("name")
            rarity_index = headers.index("rarity") if "rarity" in headers else None
            for row in table.select("tr"):
                cells = row.find_all("td", recursive=False)
                if len(cells) <= max(number_index, name_index):
                    continue
                parsed = cls._parse_reference(cells[number_index].get_text(" ", strip=True))
                name = unescape(cells[name_index].get_text(" ", strip=True))
                if not parsed or not name or "?" in parsed[1] or name in {"?", "???"}:
                    continue
                row_set, collector = parsed
                if normalise_set_code(row_set) != wanted or collector in seen:
                    continue
                seen.add(collector)
                rarity_text = (
                    cells[rarity_index].get_text(" ", strip=True) if rarity_index is not None else ""
                )
                mappings.append(
                    EnglishNameMapping(
                        set_code=row_set,
                        collector_number=collector,
                        rarity=cls._rarity(collector, rarity_text),
                        english_name=name,
                        source="fandom",
                        source_url=source_url,
                    )
                )
        return mappings

    @classmethod
    def parse_list_mappings(
        cls, html: str, set_code: str, *, source_url: str
    ) -> list[EnglishNameMapping]:
        """Parse Fandom's promo-page ``CODE/NUMBER - Name`` list format."""
        wanted = normalise_set_code(set_code)
        soup = BeautifulSoup(html, "lxml")
        mappings: list[EnglishNameMapping] = []
        seen: set[str] = set()
        for item in soup.select("li"):
            parsed = cls._parse_list_reference(item.get_text(" ", strip=True))
            link = item.select_one("a[title]")
            if not parsed or not link:
                continue
            row_set, collector = parsed
            if normalise_set_code(row_set) != wanted or collector in seen:
                continue
            name = unescape(link.get_text(" ", strip=True))
            if not name or name in {"?", "???"}:
                continue
            seen.add(collector)
            mappings.append(
                EnglishNameMapping(
                    set_code=row_set,
                    collector_number=collector,
                    rarity=cls._rarity(collector, ""),
                    english_name=name,
                    source="fandom",
                    source_url=source_url,
                )
            )
        return mappings

    @staticmethod
    def _normalise_header(value: str) -> str:
        return " ".join(value.casefold().replace(".", "").split())

    @staticmethod
    def _parse_reference(value: str) -> tuple[str, str] | None:
        matched = re.search(r"([A-Za-z]+-[A-Za-z]+\d+(?:-[A-Za-z]+)?)/([A-Za-z0-9-]+)", value)
        if not matched:
            return None
        set_code, collector = matched.groups()
        return set_code, collector[:-2] if collector.endswith("EN") else collector

    @staticmethod
    def _parse_list_reference(value: str) -> tuple[str, str] | None:
        matched = re.match(r"\s*([A-Za-z]+(?:-[A-Za-z]+)?\d*)/([A-Za-z0-9-]+)\s*-", value)
        if not matched:
            return None
        set_code, collector = matched.groups()
        return set_code, collector[:-2] if collector.endswith("EN") else collector

    @staticmethod
    def _rarity(collector_number: str, table_rarity: str) -> str:
        prefix = re.match(r"([A-Z]+)\d", collector_number.upper())
        if prefix:
            return prefix.group(1)
        return table_rarity.strip().upper().split("+", maxsplit=1)[0]

    @classmethod
    def _page_url(cls, title: str) -> str:
        return cls.wiki_base_url + quote(title.replace(" ", "_"), safe="_:()")

    async def _get_json(self, params: dict[str, str | int]) -> dict[str, object]:
        headers = {"User-Agent": "ScraperBot/0.1 (+local catalogue mapping; contact: local-use)"}
        response: httpx.Response | None = None
        for attempt in range(1, self.request_attempts + 1):
            try:
                if self.client:
                    response = await self.client.get(self.api_url, params=params, headers=headers)
                else:
                    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
                        response = await client.get(self.api_url, params=params, headers=headers)
                response.raise_for_status()
                break
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as error:
                if attempt == self.request_attempts:
                    raise OfficialSourceError(
                        f"The Fandom endpoint failed after {self.request_attempts} attempts."
                    ) from error
                await asyncio.sleep(attempt)
        assert response is not None
        payload = response.json()
        if "error" in payload:
            raise OfficialSourceError(f"Fandom API error: {payload['error']}")
        return payload
