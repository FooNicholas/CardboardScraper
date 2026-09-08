"""Command-line import of official English names into the local SQLite catalogue."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
from collections.abc import Callable

from scraperbot.catalogue.official_source import OfficialEnglishCardSource, OfficialSourceError
from scraperbot.catalogue.repository import CatalogueRepository


async def import_official_sets(
    database: Path,
    set_codes: list[str],
    *,
    all_sets: bool = False,
    progress: Callable[[int, int, str, int | None], None] | None = None,
) -> int:
    source = OfficialEnglishCardSource()
    if all_sets:
        expansions = await source.list_expansions()
    else:
        expansions = await source.expansions_for_sets(set_codes)
    with CatalogueRepository(database) as catalogue:
        imported = 0
        for index, expansion in enumerate(expansions, start=1):
            if all_sets and catalogue.has_official_expansion(expansion.id):
                if progress:
                    progress(index, len(expansions), expansion.set_code or expansion.title, None)
                continue
            cards = await source.cards_for_expansion(expansion)
            imported += catalogue.import_many(cards)
            if progress:
                progress(index, len(expansions), expansion.set_code or expansion.title, len(cards))
        return imported


async def list_official_sets() -> list[str]:
    expansions = await OfficialEnglishCardSource().list_expansions()
    return [f"{expansion.set_code or 'unrecognised'}\t{expansion.title}" for expansion in expansions]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import English names from the official Cardfight!! Vanguard card database."
    )
    parser.add_argument("--set", dest="sets", action="append", default=[], help="Set code, e.g. D-BT06")
    parser.add_argument("--all", dest="all_sets", action="store_true", help="Import every listed expansion sequentially")
    parser.add_argument("--list-sets", action="store_true", help="List official expansion set codes and exit")
    parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    args = parser.parse_args()
    if args.list_sets:
        print("\n".join(asyncio.run(list_official_sets())))
        return
    if not args.sets and not args.all_sets:
        parser.error("supply at least one --set or choose --all")
    try:
        count = asyncio.run(
            import_official_sets(
                args.database,
                args.sets,
                all_sets=args.all_sets,
                progress=lambda index, total, label, cards: print(
                    f"[{index}/{total}] {label}: "
                    f"{'already imported' if cards is None else f'{cards} card prints'}",
                    flush=True,
                ),
            )
        )
    except OfficialSourceError as error:
        parser.exit(2, f"Official import failed: {error}\n")
    print(f"Imported {count} English card prints into {args.database}.")


if __name__ == "__main__":
    main()
