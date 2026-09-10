import asyncio
from pathlib import Path

from scraperbot.catalogue.regional_mapping_repair import repair_region_specific_mappings
from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import CardPrint, EnglishNameMapping, JapaneseCardPrint


class FixedFandomSource:
    async def mappings_for_set(self, set_code: str) -> tuple[str, list[EnglishNameMapping]]:
        assert set_code == "DZSS10"
        return (
            "DZ Special Series 10: Master Deckset -Michiru Hazama-",
            [
                EnglishNameMapping(
                    "DZ-SS10",
                    "018",
                    "",
                    "Caper Companion",
                    "fandom",
                    "https://cardfight.fandom.com/wiki/DZ_Special_Series_10:_Master_Deckset_-Michiru_Hazama-",
                )
            ],
        )


def test_special_set_repair_replaces_false_equal_serial_mapping(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    with CatalogueRepository(database) as catalogue:
        catalogue.import_japanese_many(
            [
                JapaneseCardPrint(
                    "DZ-SS10",
                    "018",
                    "",
                    "ケッパー・コンパニオン",
                    "https://cf-vanguard.com/cardlist/?cardno=DZ-SS10/018",
                )
            ]
        )
        # Reproduce a legacy equal-serial link created before special sets
        # were recognised as separate Japanese and English product sequences.
        catalogue.connection.execute(
            """
            INSERT INTO card_prints (
                set_code, collector_number, rarity, english_name, japanese_name,
                aliases_json, normalised_name, normalised_aliases, source, source_url
            ) VALUES ('DZSS10', '018', '', 'Vital Blaze Blast', 'ケッパー・コンパニオン',
                      '[]', 'vital blaze blast', '', 'official-english', 'https://en.test/dzss10/018')
            """
        )
        catalogue.connection.execute(
            """
            INSERT INTO english_name_mappings (
                japanese_print_id, english_name, aliases_json, mapping_source, mapping_source_url, status
            ) SELECT id, 'Vital Blaze Blast', '[]', 'official-english', 'https://en.test/dzss10/018', 'official'
            FROM japanese_prints WHERE set_code = 'DZSS10' AND collector_number = '018'
            """
        )
        catalogue.connection.commit()
        assert catalogue.official_english_name_mappings() == []

    result = asyncio.run(
        repair_region_specific_mappings(database, ("DZ-SS10",), source=FixedFandomSource())
    )

    assert result.archived_english_references == 1
    assert result.restored_fandom == 1
    assert result.unresolved == 0
    with CatalogueRepository(database) as catalogue:
        card = catalogue.search("caper companion", japanese_only=True)[0]
        assert card.set_code == "DZSS10"
        assert card.collector_number == "018"
        assert card.japanese_name == "ケッパー・コンパニオン"
        assert not catalogue.search("vital blaze blast", japanese_only=True)
        archived = catalogue.connection.execute(
            "SELECT english_name FROM english_print_references WHERE set_code = ? AND collector_number = ?",
            ("DZSS10", "018"),
        ).fetchone()
        assert archived["english_name"] == "Vital Blaze Blast"


def test_new_official_special_set_import_is_archived_not_searchable(tmp_path: Path) -> None:
    with CatalogueRepository(tmp_path / "catalogue.sqlite3") as catalogue:
        catalogue.upsert(
            CardPrint(
                "DZ-SS10",
                "018",
                "",
                "Vital Blaze Blast",
                source="official-english",
                source_url="https://en.test/dzss10/018",
            )
        )

        assert catalogue.count == 0
        assert not catalogue.search("vital blaze blast")
        archived = catalogue.connection.execute(
            "SELECT english_name FROM english_print_references WHERE set_code = ? AND collector_number = ?",
            ("DZSS10", "018"),
        ).fetchone()
        assert archived["english_name"] == "Vital Blaze Blast"
