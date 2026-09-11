"""Compatibility command for the retired English-serial linker."""

from __future__ import annotations

import argparse
from pathlib import Path

from scraperbot.catalogue.repository import CatalogueRepository


def link_official_english_names(database: Path) -> tuple[int, int]:
    """Return zero: English serials are retained but never establish JP equality."""
    with CatalogueRepository(database) as catalogue:
        mappings = catalogue.official_english_name_mappings()
        result = catalogue.apply_name_mappings(mappings)
    return len(mappings), result.preserved_official


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Report that official English serials are reference-only for Japanese search."
    )
    parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    args = parser.parse_args()
    candidates, linked = link_official_english_names(args.database)
    print(
        f"Created {linked} Japanese mappings from {candidates} official-English references. "
        "English serials are retained as reference data only."
    )


if __name__ == "__main__":
    main()
