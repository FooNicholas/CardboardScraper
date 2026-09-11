import asyncio
from pathlib import Path

from scraperbot.catalogue.fandom_importer import FandomBatchItem
from scraperbot.catalogue.promo_catalogue_importer import PromoCatalogueImportResult
from scraperbot.catalogue.refresh import refresh_catalogue
from scraperbot.catalogue.repository import MappingImportResult


def test_refresh_orchestrates_only_approved_catalogue_sources(tmp_path: Path) -> None:
    calls: list[str] = []
    progress: list[str] = []

    async def official_importer(_: Path, __: list[str], **kwargs: object) -> int:
        calls.append("official")
        assert kwargs["all_sets"] is True
        kwargs["progress"](1, 1, "DZBT99", 3)  # type: ignore[operator]
        return 3

    async def japanese_importer(_: Path, __: list[str], **kwargs: object) -> int:
        calls.append("japanese")
        assert kwargs["all_sets"] is True
        kwargs["progress"](1, 1, "DZBT99", 4)  # type: ignore[operator]
        return 4

    def official_linker(_: Path) -> tuple[int, int]:
        calls.append("link")
        return 5, 4

    async def official_promo_importer(_: Path, **kwargs: object) -> int:
        calls.append("official-promos")
        return 9

    def promo_mapping_repairer(_: Path):
        calls.append("promo-repair")

    async def fandom_importer(_: Path, **kwargs: object) -> list[FandomBatchItem]:
        calls.append("fandom")
        item = FandomBatchItem("DZBT99", "Example", MappingImportResult(6, 0, 0, 0))
        kwargs["progress"](1, 1, item)  # type: ignore[operator]
        return [item]

    def name_deriver(_: Path) -> MappingImportResult:
        calls.append("derive")
        return MappingImportResult(7, 2, 0, 0)

    async def promo_importer(_: Path, **kwargs: object) -> PromoCatalogueImportResult:
        calls.append("yuyutei")
        assert kwargs["all_pages"] is True
        assert kwargs["refresh"] is True
        kwargs["progress"](1, 1, "dpromo-100", 8)  # type: ignore[operator]
        return PromoCatalogueImportResult(1, 0, 0, 8)

    result = asyncio.run(
        refresh_catalogue(
            tmp_path / "catalogue.sqlite3",
            refresh_promos=True,
            progress=progress.append,
            official_importer=official_importer,
            japanese_importer=japanese_importer,
            official_promo_importer=official_promo_importer,
            promo_mapping_repairer=promo_mapping_repairer,
            official_linker=official_linker,
            fandom_importer=fandom_importer,
            name_deriver=name_deriver,
            promo_importer=promo_importer,
        )
    )

    assert calls == ["official", "japanese", "official-promos", "link", "fandom", "derive", "yuyutei", "promo-repair"]
    assert result.official_promo_identities == 9
    assert result.english_prints_imported == 3
    assert result.japanese_prints_imported == 4
    assert result.official_link_candidates == 5
    assert result.official_links_applied == 4
    assert result.fandom_mappings_applied == 6
    assert result.derived_name_mappings == 7
    assert result.yuyutei_promo_result.entries_imported == 8
    assert result.regional_repair is None
    assert any(message.startswith("Fandom") for message in progress)
