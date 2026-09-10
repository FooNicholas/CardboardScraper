import asyncio
from pathlib import Path

from scraperbot.catalogue.promo_catalogue_importer import import_yuyutei_promo_pages
from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import PromoCatalogueEntry


class FakePromoSource:
    store_id = "yuyutei"

    def __init__(self) -> None:
        self.calls: list[str] = []

    def page_url(self, page_slug: str) -> str:
        return f"https://example.test/{page_slug}"

    async def list_page_slugs(self) -> list[str]:
        return ["dpromo-100", "dpromo-200"]

    async def entries_for_page(self, page_slug: str) -> list[PromoCatalogueEntry]:
        self.calls.append(page_slug)
        return [
            PromoCatalogueEntry(
                store_id=self.store_id,
                page_slug=page_slug,
                set_code="D-PR",
                collector_number="1101",
                japanese_name="エネルギー",
                listing_url="https://example.test/card/10019",
                source_page_url=self.page_url(page_slug),
                product_id="10019",
            )
        ]


def test_promo_catalogue_import_is_checkpointed_and_refreshable(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    source = FakePromoSource()

    first = asyncio.run(import_yuyutei_promo_pages(database, ["dpromo-1200"], source=source))
    second = asyncio.run(import_yuyutei_promo_pages(database, ["dpromo-1200"], source=source))
    refreshed = asyncio.run(
        import_yuyutei_promo_pages(database, ["dpromo-1200"], refresh=True, source=source)
    )

    assert first.pages_imported == 1
    assert first.entries_imported == 1
    assert second.pages_skipped == 1
    assert refreshed.pages_imported == 1
    assert source.calls == ["dpromo-1200", "dpromo-1200"]
    with CatalogueRepository(database) as catalogue:
        entry = catalogue.promo_catalogue_entry("yuyutei", "D-PR", "1101")
        assert entry is not None
        assert entry.japanese_name == "エネルギー"
        assert entry.page_slug == "dpromo-1200"


def test_promo_catalogue_import_can_discover_all_pages(tmp_path: Path) -> None:
    source = FakePromoSource()
    result = asyncio.run(
        import_yuyutei_promo_pages(tmp_path / "catalogue.sqlite3", all_pages=True, source=source)
    )

    assert result.pages_imported == 2
    assert source.calls == ["dpromo-100", "dpromo-200"]


class EmptyPromoSource(FakePromoSource):
    async def entries_for_page(self, page_slug: str) -> list[PromoCatalogueEntry]:
        self.calls.append(page_slug)
        return []


def test_promo_catalogue_import_does_not_checkpoint_empty_range_pages(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    source = EmptyPromoSource()

    result = asyncio.run(import_yuyutei_promo_pages(database, ["dpromo-1800"], source=source))

    assert result.pages_without_entries == 1
    with CatalogueRepository(database) as catalogue:
        assert not catalogue.has_promo_catalogue_page("yuyutei", "dpromo-1800")
