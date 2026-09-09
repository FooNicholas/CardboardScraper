"""CLI for applying trusted Fandom English mappings to Japanese print data."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from scraperbot.catalogue.fandom_source import FandomMappingSource
from scraperbot.catalogue.official_source import OfficialSourceError
from scraperbot.catalogue.repository import CatalogueRepository, MappingImportResult


async def import_fandom_mappings(
    database: Path, set_code: str, *, page_title: str | None = None
) -> tuple[str, MappingImportResult]:
    title, mappings = await FandomMappingSource().mappings_for_set(set_code, page_title=page_title)
    with CatalogueRepository(database) as catalogue:
        return title, catalogue.apply_name_mappings(mappings)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Fandom English mappings to an imported Japanese Vanguard set.")
    parser.add_argument("--set", required=True, help="Japanese set code, e.g. DZ-BT16")
    parser.add_argument("--page", help="Optional Fandom page title when automatic resolution is ambiguous")
    parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    args = parser.parse_args()
    try:
        title, result = asyncio.run(import_fandom_mappings(args.database, args.set, page_title=args.page))
    except OfficialSourceError as error:
        parser.exit(2, f"Fandom mapping import failed: {error}\n")
    print(
        f"Applied Fandom page {title!r}: {result.mapped} mapped ({result.derived} parallel variants derived), "
        f"{result.unmatched} unmatched, {result.preserved_official} official names preserved."
    )


if __name__ == "__main__":
    main()
