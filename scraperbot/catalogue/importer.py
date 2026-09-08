"""Import a reviewed card-catalogue JSON export into SQLite."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Iterable

from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import CardPrint


def records_from_json(path: Path) -> list[CardPrint]:
    """Load JSON records produced by an official/source-specific importer.

    Accepted shapes are either a JSON list or an object with a ``card_prints``
    array. The source importer is responsible for factual card data; this
    command deliberately keeps local aliases and manual corrections intact.
    """
    payload = json.loads(path.read_text(encoding="utf-8"))
    records: Iterable[dict[str, Any]] = payload.get("card_prints", []) if isinstance(payload, dict) else payload
    cards: list[CardPrint] = []
    for record in records:
        cards.append(
            CardPrint(
                set_code=record["set_code"],
                collector_number=record.get("collector_number", record.get("card_number", "")),
                rarity=record.get("rarity", ""),
                english_name=record["english_name"],
                japanese_name=record.get("japanese_name"),
                aliases=tuple(record.get("aliases", [])),
                source=record.get("source", "manual"),
                source_url=record.get("source_url"),
            )
        )
    return cards


def import_file(database_path: Path, input_path: Path) -> int:
    with CatalogueRepository(database_path) as catalogue:
        return catalogue.import_many(records_from_json(input_path))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import a reviewed Cardfight!! Vanguard catalogue JSON export.")
    parser.add_argument("input", type=Path, help="JSON file containing card print records")
    parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    args = parser.parse_args()
    print(f"Imported {import_file(args.database, args.input)} card prints into {args.database}.")


if __name__ == "__main__":
    main()
