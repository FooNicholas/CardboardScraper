from pathlib import Path

from scraperbot.catalogue.promo_mapping_repair import repair_promo_mappings
from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import CardPrint, EnglishNameMapping, JapaneseCardPrint


def test_repair_replaces_false_promo_serial_mapping_with_fandom_name_match(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    with CatalogueRepository(database) as catalogue:
        catalogue.import_japanese_many(
            [
                JapaneseCardPrint("D-PR", "953", "PR", "大地を駆ける守主 ルアン", "https://jp/dpr953"),
                JapaneseCardPrint("D-PR", "1000", "PR", "エネルギー", "https://jp/dpr1000"),
                JapaneseCardPrint("D-SS11", "108", "C", "大地を駆ける守主 ルアン", "https://jp/dss11108"),
            ]
        )
        catalogue.apply_name_mappings(
            [
                EnglishNameMapping(
                    "D-SS11",
                    "108",
                    "C",
                    "Guard Running Through The Earth, Leuhan",
                    "fandom",
                    "https://fandom/leuhan",
                )
            ]
        )
        # Reproduce the legacy bad data from the equal-serial official linker.
        catalogue.connection.execute(
            """
            INSERT INTO card_prints (
                set_code, collector_number, rarity, english_name, japanese_name,
                aliases_json, normalised_name, normalised_aliases, source, source_url
            ) VALUES ('DPR', '953', 'PR', 'Nebula Knight of Glory, Serius', '大地を駆ける守主 ルアン',
                      '[]', 'nebula knight of glory serius', '', 'official-english', 'https://en/dpr953')
            """
        )
        catalogue.connection.execute(
            """
            INSERT INTO english_name_mappings (
                japanese_print_id, english_name, aliases_json, mapping_source, mapping_source_url, status
            ) SELECT id, 'Nebula Knight of Glory, Serius', '[]', 'official-english', 'https://en/dpr953', 'official'
            FROM japanese_prints WHERE set_code = 'DPR' AND collector_number = '953'
            """
        )
        catalogue.connection.commit()

    result = repair_promo_mappings(database)

    assert result.archived_english_references == 1
    assert result.mapped_by_japanese_name == 1
    assert result.mapped_shared_utility_names == 1
    assert result.unresolved == 0
    with CatalogueRepository(database) as catalogue:
        leuhan = catalogue.search("leuhan", japanese_only=True)
        repaired = next(card for card in leuhan if card.set_code == "DPR")
        assert repaired.collector_number == "953"
        assert repaired.english_name == "Guard Running Through The Earth, Leuhan"
        assert not catalogue.search("nebula knight of glory", japanese_only=True)
        energy = next(card for card in catalogue.search("energy", japanese_only=True) if card.set_code == "DPR")
        assert energy.collector_number == "1000"
        assert energy.english_name == "Energy"
        assert catalogue.unmapped_japanese_count("DPR") == 0
        archived = catalogue.connection.execute(
            "SELECT english_name FROM english_print_references WHERE set_code = 'DPR' AND collector_number = '953'"
        ).fetchone()
        assert archived["english_name"] == "Nebula Knight of Glory, Serius"


def test_new_official_promo_import_is_archived_not_user_searchable(tmp_path: Path) -> None:
    with CatalogueRepository(tmp_path / "catalogue.sqlite3") as catalogue:
        catalogue.upsert(
            CardPrint(
                "D-PR",
                "953",
                "PR",
                "Nebula Knight of Glory, Serius",
                source="official-english",
                source_url="https://en/dpr953",
            )
        )
        assert catalogue.count == 0
        assert not catalogue.search("nebula knight")
        archived = catalogue.connection.execute(
            "SELECT english_name FROM english_print_references WHERE set_code = 'DPR' AND collector_number = '953'"
        ).fetchone()
        assert archived["english_name"] == "Nebula Knight of Glory, Serius"


def test_fandom_promo_mapping_archives_a_legacy_official_record(tmp_path: Path) -> None:
    with CatalogueRepository(tmp_path / "catalogue.sqlite3") as catalogue:
        catalogue.import_japanese_many(
            [JapaneseCardPrint("D-PR", "953", "PR", "日本語名", "https://jp/dpr953")]
        )
        catalogue.connection.execute(
            """
            INSERT INTO card_prints (
                set_code, collector_number, rarity, english_name, japanese_name,
                aliases_json, normalised_name, normalised_aliases, source, source_url
            ) VALUES ('DPR', '953', 'PR', 'Legacy English Name', NULL,
                      '[]', 'legacy english name', '', 'official-english', 'https://en/dpr953')
            """
        )
        catalogue.connection.commit()

        catalogue.apply_name_mappings(
            [EnglishNameMapping("D-PR", "953", "PR", "Trusted Promo Name", "fandom", "https://fandom/dpr953")]
        )

        card = catalogue.search("trusted promo", japanese_only=True)[0]
        assert card.english_name == "Trusted Promo Name"
        archived = catalogue.connection.execute(
            "SELECT english_name FROM english_print_references WHERE set_code = 'DPR' AND collector_number = '953'"
        ).fetchone()
        assert archived["english_name"] == "Legacy English Name"
