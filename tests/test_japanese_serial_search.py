import asyncio
from pathlib import Path

from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import EnglishNameMapping, JapaneseCardPrint
from scraperbot.services.comparison import ComparisonService
from scraperbot.web import LocalPriceCheckWeb
from tests.test_web import FixedConnector


def test_japanese_serial_lookup_normalises_formatted_dpr_references(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    with CatalogueRepository(database) as catalogue:
        catalogue.import_japanese_many(
            [JapaneseCardPrint("D-PR", "953", "PR", "大地を駆ける守主 ルアン", "https://jp/dpr953")]
        )
        selections = [
            catalogue.lookup_japanese_serial(value) for value in ("D-PR/953", "DPR953", "D-PR 953")
        ]

        assert all(card is not None for card in selections)
        assert {card.id for card in selections if card} == {selections[0].id}
        assert selections[0].source == "japanese-serial-only"
        assert not catalogue.lookup_japanese_serial("953")


def test_japanese_serial_lookup_returns_mapped_card_when_available(tmp_path: Path) -> None:
    with CatalogueRepository(tmp_path / "catalogue.sqlite3") as catalogue:
        catalogue.import_japanese_many(
            [JapaneseCardPrint("D-PR", "953", "PR", "大地を駆ける守主 ルアン", "https://jp/dpr953")]
        )
        catalogue.apply_name_mappings(
            [
                EnglishNameMapping(
                    "D-PR",
                    "953",
                    "PR",
                    "Guard Running Through The Earth, Leuhan",
                    "fandom",
                    "https://fandom/leuhan",
                )
            ]
        )

        card = catalogue.lookup_japanese_serial("DPR953")
        assert card is not None
        assert card.id is not None and card.id > 0
        assert card.english_name == "Guard Running Through The Earth, Leuhan"


def test_web_serial_search_can_compare_an_unmapped_japanese_print(tmp_path: Path) -> None:
    with CatalogueRepository(tmp_path / "catalogue.sqlite3") as catalogue:
        catalogue.import_japanese_many(
            [JapaneseCardPrint("D-PR", "1101", "PR", "エネルギー", "https://jp/dpr1101")]
        )
        app = LocalPriceCheckWeb(catalogue, ComparisonService([FixedConnector()]))

        search = app.search("DPR1101")
        selection_id = search["cards"][0]["id"]
        assert search["mode"] == "japanese_serial"
        assert selection_id < 0
        comparison = asyncio.run(app.compare(selection_id))
        assert comparison["card"]["display_code"] == "DPR/1101 · PR"
        assert comparison["offers"][0]["price_yen"] == 1500
