import asyncio
from pathlib import Path

from scraperbot.catalogue.cross_print_importer import import_cross_print_mappings
from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import CardPrint, EnglishNameMapping, JapaneseCardPrint


class FakeCrossPrintSource:
    async def cross_print_mappings_for_card(self, card: CardPrint) -> list[EnglishNameMapping]:
        assert card.print_key == "DZBT12/RE07:RE"
        return [
            EnglishNameMapping(
                "D-PR",
                "1247",
                "",
                card.english_name,
                "fandom-cross-print",
                "https://cardfight.fandom.com/wiki/The_Nebula_Knight%27s_Path_to_Reach_for_the_Stars",
                status="verified",
            )
        ]


def test_cross_print_import_maps_an_english_reprint_to_its_japanese_promo(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    with CatalogueRepository(database) as catalogue:
        catalogue.import_japanese_many(
            [JapaneseCardPrint("D-PR", "1247", "", "星海より手繰る星霧騎士の道", "https://official/1247")]
        )
        catalogue.upsert(
            CardPrint(
                "DZ-BT12",
                "Re07",
                "RE",
                "The Nebula Knight's Path to Reach for the Stars",
                source="official-english",
            )
        )

    items = asyncio.run(
        import_cross_print_mappings(database, ["DZ-BT12"], source=FakeCrossPrintSource())  # type: ignore[arg-type]
    )

    assert len(items) == 1
    assert items[0].result is not None
    with CatalogueRepository(database) as catalogue:
        cards = catalogue.search("nebula knight path", japanese_only=True)
        assert [(card.set_code, card.collector_number, card.japanese_name) for card in cards] == [
            ("DPR", "1247", "星海より手繰る星霧騎士の道"),
        ]
