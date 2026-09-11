from pathlib import Path

from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.catalogue.status import catalogue_status
from scraperbot.models import EnglishNameMapping, JapaneseCardPrint, PromoCatalogueEntry


def test_catalogue_status_separates_playable_and_held_promo_work(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    with CatalogueRepository(database) as catalogue:
        catalogue.import_japanese_many(
            [
                JapaneseCardPrint("D-PR", "100", "PR", "Playable", "https://jp/100"),
                JapaneseCardPrint("D-PR", "101", "PR", "エネルギー", "https://jp/101"),
                JapaneseCardPrint("DZ-SS10", "018", "", "ケッパー・コンパニオン", "https://jp/018"),
            ]
        )
        catalogue.apply_name_mappings(
            [
                EnglishNameMapping(
                    "DZ-SS10", "018", "", "Caper Companion", "fandom", "https://fandom/018"
                )
            ]
        )
        catalogue.upsert_promo_catalogue_entries(
            [
                PromoCatalogueEntry(
                    "yuyutei", "dpromo-100", "D-PR", "100", "Playable",
                    "https://yuyu/100", "https://yuyu/dpromo-100", "100"
                )
            ]
        )

    status = catalogue_status(database)

    assert status.japanese_prints == 3
    assert status.searchable_japanese_prints == 1
    assert status.unmapped_japanese_prints == 2
    assert status.promo_prints == 2
    assert status.unmapped_promo_prints == 2
    assert status.held_utility_promo_prints == 1
    assert status.unresolved_playable_promo_prints == 1
    assert status.special_series_sets == 1
    assert status.special_series_prints == 1
    assert status.unmapped_special_series_prints == 0
    assert status.yuyutei_promo_entries == 1
