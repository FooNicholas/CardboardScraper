import asyncio
from pathlib import Path

from scraperbot.catalogue.fandom_importer import import_all_fandom_mappings
from scraperbot.catalogue.official_source import OfficialSourceError
from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import EnglishNameMapping, JapaneseCardPrint


class FakeFandomSource:
    def __init__(self) -> None:
        self.requested_sets: list[str] = []

    async def mappings_for_set(self, set_code: str) -> tuple[str, list[EnglishNameMapping]]:
        self.requested_sets.append(set_code)
        if set_code == "DBT02":
            raise OfficialSourceError("No matching Fandom page")
        return (
            "Example page",
            [EnglishNameMapping("D-BT01", "001", "RRR", "Mapped", "fandom", "https://fandom/1")],
        )


def test_bulk_fandom_import_continues_after_an_unavailable_set(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    with CatalogueRepository(database) as catalogue:
        catalogue.import_japanese_many(
            [
                JapaneseCardPrint("D-BT01", "001", "RRR", "マップ済み", "https://official/1"),
                JapaneseCardPrint("D-BT02", "001", "RRR", "未マップ", "https://official/2"),
            ]
        )

    items = asyncio.run(import_all_fandom_mappings(database, source=FakeFandomSource()))  # type: ignore[arg-type]

    assert [item.set_code for item in items] == ["DBT01", "DBT02"]
    assert items[0].result is not None
    assert items[1].error == "No matching Fandom page"
    with CatalogueRepository(database) as catalogue:
        assert catalogue.search("mapped")[0].japanese_name == "マップ済み"


def test_bulk_fandom_import_skips_region_specific_promo_lists(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    source = FakeFandomSource()
    with CatalogueRepository(database) as catalogue:
        catalogue.import_japanese_many(
            [
                JapaneseCardPrint("D-PR", "953", "PR", "大地を駆ける守主 ルアン", "https://official/dpr953"),
                JapaneseCardPrint("D-BT01", "001", "RRR", "マップ済み", "https://official/1"),
            ]
        )

    items = asyncio.run(import_all_fandom_mappings(database, source=source))  # type: ignore[arg-type]

    assert [item.set_code for item in items] == ["DBT01"]
    assert source.requested_sets == ["DBT01"]


def test_bulk_fandom_import_includes_d_era_p_and_v_products(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    source = FakeFandomSource()
    with CatalogueRepository(database) as catalogue:
        catalogue.import_japanese_many(
            [
                JapaneseCardPrint("D-BT01", "001", "RRR", "Dカード", "https://official/d"),
                JapaneseCardPrint("D-PS01", "001", "RRR", "Pカード", "https://official/p"),
                JapaneseCardPrint("D-PV01", "001", "RRR", "PVカード", "https://official/pv"),
                JapaneseCardPrint("D-VS01", "001", "RRR", "Vカード", "https://official/v"),
            ]
        )

    items = asyncio.run(import_all_fandom_mappings(database, source=source))  # type: ignore[arg-type]

    assert [item.set_code for item in items] == ["DBT01", "DPS01", "DPV01", "DVS01"]
    assert source.requested_sets == ["DBT01", "DPS01", "DPV01", "DVS01"]
