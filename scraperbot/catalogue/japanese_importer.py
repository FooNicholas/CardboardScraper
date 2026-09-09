"""CLI for importing the official Japanese print master."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

from scraperbot.catalogue.japanese_source import OfficialJapaneseCardSource
from scraperbot.catalogue.official_source import OfficialSourceError
from scraperbot.catalogue.repository import CatalogueRepository


async def import_japanese_sets(database: Path, set_codes: list[str]) -> int:
    source = OfficialJapaneseCardSource()
    expansions = await source.expansions_for_sets(set_codes)
    with CatalogueRepository(database) as catalogue:
        imported = 0
        for expansion in expansions:
            imported += catalogue.import_japanese_many(await source.cards_for_expansion(expansion))
    return imported


def main() -> None:
    parser = argparse.ArgumentParser(description="Import official Japanese Vanguard print data into the local master.")
    parser.add_argument("--set", dest="sets", action="append", required=True, help="Japanese set code, e.g. DZ-BT16")
    parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    args = parser.parse_args()
    try:
        count = asyncio.run(import_japanese_sets(args.database, args.sets))
    except OfficialSourceError as error:
        parser.exit(2, f"Japanese import failed: {error}\n")
    print(f"Imported {count} official Japanese prints into {args.database}.")


if __name__ == "__main__":
    main()
