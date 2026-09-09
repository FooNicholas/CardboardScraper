import asyncio
from pathlib import Path

from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.connectors.base import StoreConnector
from scraperbot.models import Availability, CardPrint, MatchConfidence, StoreOffer
from scraperbot.services.comparison import ComparisonService
from scraperbot.web import LocalPriceCheckWeb


class FixedConnector(StoreConnector):
    store_id = "example"
    store_name = "Example Store"

    async def search(self, _: CardPrint) -> list[StoreOffer]:
        return [
            StoreOffer(
                store_id=self.store_id,
                store_name=self.store_name,
                raw_name="Japanese listing",
                price_yen=1500,
                price_display="¥1,500",
                availability=Availability.IN_STOCK,
                listing_url="https://example.test/listing",
                match_confidence=MatchConfidence.EXACT_JAPANESE_NAME,
            )
        ]


def test_local_web_search_and_comparison_share_the_catalogue(tmp_path: Path) -> None:
    with CatalogueRepository(tmp_path / "catalogue.sqlite3") as catalogue:
        card = catalogue.upsert(
            CardPrint(
                "DZ-BT16",
                "FFR02",
                "FFR",
                "Exacerbate Dragon",
                japanese_name="エグザサベイト・ドラゴン",
                source="test",
            )
        )
        app = LocalPriceCheckWeb(catalogue, ComparisonService([FixedConnector()]))

        search = app.search("exacerbate ffr")
        assert search["cards"] == [
            {
                "id": card.id,
                "english_name": "Exacerbate Dragon",
                "japanese_name": "エグザサベイト・ドラゴン",
                "set_code": "DZBT16",
                "collector_number": "FFR02",
                "rarity": "FFR",
                "display_code": "DZBT16/FFR02 · FFR",
                "source": "test",
            }
        ]

        comparison = asyncio.run(app.compare(card.id or 0))
        assert comparison["offers"][0]["store_name"] == "Example Store"
        assert comparison["offers"][0]["match_confidence"] == "exact_japanese_name"


def test_local_web_rejects_an_empty_search(tmp_path: Path) -> None:
    with CatalogueRepository(tmp_path / "catalogue.sqlite3") as catalogue:
        app = LocalPriceCheckWeb(catalogue, ComparisonService([]))
        try:
            app.search("   ")
        except ValueError as error:
            assert str(error) == "Enter a card name to search."
        else:
            raise AssertionError("An empty web search should fail clearly.")
