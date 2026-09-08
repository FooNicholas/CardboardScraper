from pathlib import Path

from scraperbot.catalogue.importer import import_file
from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import CardPrint


def test_search_supports_partial_alias_and_typo(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    with CatalogueRepository(database) as catalogue:
        catalogue.import_many(
            [
                CardPrint(
                    set_code="DZ-BT16",
                    collector_number="15",
                    rarity="FFR",
                    english_name='Youthberk "Skyfall Arms"',
                    japanese_name="蒼嵐竜 メイルストローム",
                    aliases=("skyfall youthberk", "youth berk"),
                    source="test",
                ),
                CardPrint(
                    set_code="DZ-BT16",
                    collector_number="16",
                    rarity="RRR",
                    english_name="Blaster Blade",
                    aliases=("blaster",),
                    source="test",
                ),
            ]
        )
        assert catalogue.count == 2
        assert catalogue.search("skyfall")[0].english_name == 'Youthberk "Skyfall Arms"'
        assert catalogue.search("youth berk")[0].collector_number == "015"
        assert catalogue.search("youthberk")[0].rarity == "FFR"
        assert catalogue.search("blastr")[0].english_name == "Blaster Blade"
        assert catalogue.search("blaster", rarity="RRR")[0].collector_number == "016"


def test_importer_accepts_card_prints_envelope(tmp_path: Path) -> None:
    source = tmp_path / "cards.json"
    source.write_text(
        '[{"set_code":"DZBT01","collector_number":"1","rarity":"RRR",'
        '"english_name":"Chronojet Dragon","aliases":["chrono jet"]}]',
        encoding="utf-8",
    )
    database = tmp_path / "catalogue.sqlite3"
    assert import_file(database, source) == 1
    with CatalogueRepository(database) as catalogue:
        card = catalogue.search("chrono jet")[0]
        assert card.display_code == "DZBT01/001 · RRR"


def test_repository_detects_completed_official_expansion(tmp_path: Path) -> None:
    with CatalogueRepository(tmp_path / "catalogue.sqlite3") as catalogue:
        catalogue.upsert(
            CardPrint(
                set_code="D-BT06",
                collector_number="010",
                rarity="",
                english_name="Example Card",
                source="official-english",
                source_url="https://en.cf-vanguard.com/cardlist/?cardno=D-BT06/010EN&expansion=99",
            )
        )
        assert catalogue.has_official_expansion(99)
        assert not catalogue.has_official_expansion(100)
        catalogue.upsert(
            CardPrint(
                set_code="D-BT06",
                collector_number="011",
                rarity="",
                english_name="Another Card",
                source="official-english",
                source_url="https://en.cf-vanguard.com/cardlist/?cardno=D-BT06/011EN&expansion=230",
            )
        )
        assert not catalogue.has_official_expansion(23)
