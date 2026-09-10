"""Resolve Japanese counterparts for English prints with different card codes."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

from scraperbot.catalogue.fandom_source import FandomMappingSource
from scraperbot.catalogue.official_source import OfficialSourceError
from scraperbot.catalogue.repository import CatalogueRepository, MappingImportResult
from scraperbot.models import CardPrint


@dataclass(frozen=True, slots=True)
class CrossPrintBatchItem:
    """One attempted English-to-Japanese cross-print relationship import."""

    card: CardPrint
    result: MappingImportResult | None
    error: str | None = None


async def import_cross_print_mappings(
    database: Path,
    set_codes: list[str],
    *,
    source: FandomMappingSource | None = None,
) -> list[CrossPrintBatchItem]:
    """Map declared Japanese counterparts for unlinked English prints in sets."""
    source = source or FandomMappingSource()
    with CatalogueRepository(database) as catalogue:
        candidates = catalogue.unlinked_official_english_cards(set_codes)
        items: list[CrossPrintBatchItem] = []
        for card in candidates:
            try:
                mappings = await source.cross_print_mappings_for_card(card)
                items.append(CrossPrintBatchItem(card, catalogue.apply_name_mappings(mappings)))
            except OfficialSourceError as error:
                items.append(CrossPrintBatchItem(card, None, str(error)))
        return items


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Map Japanese counterparts for English prints with different print codes."
    )
    parser.add_argument(
        "--set",
        dest="sets",
        action="append",
        required=True,
        help="English set code to inspect, e.g. DZ-BT12. Repeat for more sets.",
    )
    parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    args = parser.parse_args()
    items = asyncio.run(import_cross_print_mappings(args.database, args.sets))
    mapped = sum(item.result.mapped for item in items if item.result)
    failed = sum(item.error is not None for item in items)
    print(f"Checked {len(items)} English prints; mapped {mapped} Japanese cross-prints; {failed} pages failed.")


if __name__ == "__main__":
    main()
