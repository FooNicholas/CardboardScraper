"""CLI for applying trusted Fandom English mappings to Japanese print data."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from scraperbot.catalogue.fandom_source import FandomMappingSource
from scraperbot.catalogue.official_source import OfficialSourceError
from scraperbot.catalogue.repository import CatalogueRepository, MappingImportResult


@dataclass(frozen=True, slots=True)
class FandomBatchItem:
    set_code: str
    title: str | None
    result: MappingImportResult | None
    error: str | None = None


async def import_fandom_mappings(
    database: Path, set_code: str, *, page_title: str | None = None
) -> tuple[str, MappingImportResult]:
    title, mappings = await FandomMappingSource().mappings_for_set(set_code, page_title=page_title)
    with CatalogueRepository(database) as catalogue:
        return title, catalogue.apply_name_mappings(mappings)


async def import_all_fandom_mappings(
    database: Path,
    *,
    progress: Callable[[int, int, FandomBatchItem], None] | None = None,
    source: FandomMappingSource | None = None,
) -> list[FandomBatchItem]:
    """Map every still-unmapped Japanese set without stopping on one failure."""
    source = source or FandomMappingSource()
    with CatalogueRepository(database) as catalogue:
        set_codes = catalogue.unmapped_japanese_set_codes()
        items: list[FandomBatchItem] = []
        for index, set_code in enumerate(set_codes, start=1):
            try:
                title, mappings = await source.mappings_for_set(set_code)
                item = FandomBatchItem(set_code, title, catalogue.apply_name_mappings(mappings))
            except OfficialSourceError as error:
                item = FandomBatchItem(set_code, None, None, str(error))
            items.append(item)
            if progress:
                progress(index, len(set_codes), item)
        return items


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Fandom English mappings to an imported Japanese Vanguard set.")
    parser.add_argument("--set", help="Japanese set code, e.g. DZ-BT16")
    parser.add_argument("--all", action="store_true", help="Map every Japanese set that still lacks an English name")
    parser.add_argument("--page", help="Optional Fandom page title when automatic resolution is ambiguous")
    parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    args = parser.parse_args()
    if not args.set and not args.all:
        parser.error("supply --set or choose --all")
    if args.set and args.all:
        parser.error("choose either --set or --all")
    if args.page and args.all:
        parser.error("--page is only valid with --set")
    try:
        if args.all:
            items = asyncio.run(
                import_all_fandom_mappings(
                    args.database,
                    progress=lambda index, total, item: print(
                        f"[{index}/{total}] {item.set_code}: "
                        f"{item.error or f'{item.title}: {item.result.mapped} mapped'}",
                        flush=True,
                    ),
                )
            )
            mapped = sum(item.result.mapped for item in items if item.result)
            failed = sum(item.error is not None for item in items)
            print(f"Applied {mapped} Fandom mappings; {failed} set pages need review.")
            return
        title, result = asyncio.run(import_fandom_mappings(args.database, args.set, page_title=args.page))
    except OfficialSourceError as error:
        parser.exit(2, f"Fandom mapping import failed: {error}\n")
    print(
        f"Applied Fandom page {title!r}: {result.mapped} mapped ({result.derived} parallel variants derived), "
        f"{result.unmatched} unmatched, {result.preserved_official} official names preserved."
    )


if __name__ == "__main__":
    main()
