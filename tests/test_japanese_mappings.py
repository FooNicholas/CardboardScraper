from pathlib import Path

from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import CardPrint, EnglishNameMapping, JapaneseCardPrint


def test_fandom_mapping_promotes_a_japanese_master_print_to_name_search(tmp_path: Path) -> None:
    with CatalogueRepository(tmp_path / "catalogue.sqlite3") as catalogue:
        catalogue.import_japanese_many(
            [
                JapaneseCardPrint(
                    set_code="DZ-BT16",
                    collector_number="002",
                    rarity="",
                    japanese_name="エグザサベイト・ドラゴン",
                    source_url="https://cf-vanguard.com/cardlist/?cardno=DZ-BT16/002",
                ),
                JapaneseCardPrint(
                    set_code="DZ-BT16",
                    collector_number="FFR02",
                    rarity="FFR",
                    japanese_name="エグザサベイト・ドラゴン",
                    source_url="https://cf-vanguard.com/cardlist/?cardno=DZ-BT16/FFR02",
                ),
            ]
        )
        result = catalogue.apply_name_mappings(
            [
                EnglishNameMapping(
                    set_code="DZ-BT16",
                    collector_number="002",
                    rarity="RRR",
                    english_name="Exacerbate Dragon",
                    source="fandom",
                    source_url="https://cardfight.fandom.com/wiki/DZ_Booster_Set_16",
                    aliases=("exzabite dragon",),
                ),
                EnglishNameMapping(
                    set_code="DZ-BT16",
                    collector_number="FFR02",
                    rarity="FFR",
                    english_name="Exacerbate Dragon",
                    source="fandom",
                    source_url="https://cardfight.fandom.com/wiki/DZ_Booster_Set_16",
                ),
            ]
        )
        assert result.mapped == 2
        assert catalogue.japanese_count == 2
        assert catalogue.unmapped_japanese_count("DZBT16") == 0
        card = catalogue.search("exzabite ffr", rarity="FFR")[0]
        assert card.english_name == "Exacerbate Dragon"
        assert card.japanese_name == "エグザサベイト・ドラゴン"


def test_mapping_does_not_overwrite_an_official_english_card(tmp_path: Path) -> None:
    with CatalogueRepository(tmp_path / "catalogue.sqlite3") as catalogue:
        catalogue.upsert(
            CardPrint(
                set_code="DZ-BT16",
                collector_number="002",
                rarity="RRR",
                english_name="Official Exacerbate Dragon",
                source="official-english",
            )
        )
        catalogue.import_japanese_many(
            [
                JapaneseCardPrint(
                    set_code="DZ-BT16",
                    collector_number="002",
                    rarity="RRR",
                    japanese_name="エグザサベイト・ドラゴン",
                    source_url="https://cf-vanguard.com/cardlist/?cardno=DZ-BT16/002",
                )
            ]
        )
        result = catalogue.apply_name_mappings(
            [
                EnglishNameMapping(
                    set_code="DZ-BT16",
                    collector_number="002",
                    rarity="RRR",
                    english_name="Community Exacerbate Dragon",
                    source="fandom",
                    source_url="https://cardfight.fandom.com/wiki/DZ_Booster_Set_16",
                )
            ]
        )
        assert result.preserved_official == 1
        assert catalogue.search("official exacerbate")[0].source == "official-english"


def test_mapping_propagates_a_trusted_name_to_parallel_prints(tmp_path: Path) -> None:
    with CatalogueRepository(tmp_path / "catalogue.sqlite3") as catalogue:
        catalogue.import_japanese_many(
            [
                JapaneseCardPrint("DZ-BT16", "002", "", "エグザサベイト・ドラゴン", "https://official/002"),
                JapaneseCardPrint("DZ-BT16", "FFR02", "FFR", "エグザサベイト・ドラゴン", "https://official/ffr02"),
            ]
        )
        result = catalogue.apply_name_mappings(
            [
                EnglishNameMapping(
                    "DZ-BT16", "002", "RRR", "Exacerbate Dragon", "fandom", "https://fandom/set"
                )
            ]
        )
        assert result.mapped == 2
        assert result.derived == 1
        assert catalogue.search("exacerbate", rarity="FFR")[0].collector_number == "FFR02"
