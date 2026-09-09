import asyncio
from pathlib import Path

from scraperbot.catalogue.japanese_importer import current_standard_expansions, import_japanese_sets
from scraperbot.catalogue.official_source import OfficialExpansion
from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import JapaneseCardPrint


class FakeJapaneseSource:
    def __init__(self) -> None:
        self.calls: list[int] = []

    async def list_expansions(self) -> list[OfficialExpansion]:
        return [
            OfficialExpansion(190, "V-BT01", "Excluded V-series set"),
            OfficialExpansion(201, "D-BT01", "Example Japanese set"),
        ]

    async def expansions_for_sets(self, _set_codes: list[str]) -> list[OfficialExpansion]:
        return await self.list_expansions()

    async def cards_for_expansion(self, expansion: OfficialExpansion) -> list[JapaneseCardPrint]:
        self.calls.append(expansion.id)
        return [
            JapaneseCardPrint(
                "D-BT01", "001", "RRR", "Japanese Example", f"https://official/?expansion={expansion.id}"
            )
        ]


def test_full_japanese_import_resumes_by_product_checkpoint(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    source = FakeJapaneseSource()

    assert asyncio.run(import_japanese_sets(database, [], all_sets=True, source=source)) == 1  # type: ignore[arg-type]
    assert asyncio.run(import_japanese_sets(database, [], all_sets=True, source=source)) == 0  # type: ignore[arg-type]
    assert source.calls == [201]
    with CatalogueRepository(database) as catalogue:
        assert catalogue.japanese_count == 1


def test_current_standard_expansions_excludes_v_era_prs() -> None:
    selected = current_standard_expansions(
        [
            OfficialExpansion(190, "V-BT01", "V-series"),
            OfficialExpansion(201, "D-SD01", "D-series"),
            OfficialExpansion(300, "DZ-BT16", "DZ-series"),
            OfficialExpansion(2020, None, "2020 PR"),
            OfficialExpansion(2021, None, "2021 PR"),
        ]
    )
    assert [expansion.id for expansion in selected] == [201, 300, 2021]
