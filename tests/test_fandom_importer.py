import asyncio
from pathlib import Path

from scraperbot.catalogue.fandom_importer import import_all_fandom_mappings
from scraperbot.catalogue.official_source import OfficialSourceError
from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import EnglishNameMapping, JapaneseCardPrint


class FakeFandomSource:
    async def mappings_for_set(self, set_code: str) -> tuple[str, list[EnglishNameMapping]]:
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
