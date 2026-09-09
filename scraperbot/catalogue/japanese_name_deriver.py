"""Derive safe reprint name mappings from already trusted Japanese names."""

from __future__ import annotations

import argparse
from pathlib import Path

from scraperbot.catalogue.repository import CatalogueRepository, MappingImportResult


def derive_japanese_names(database: Path) -> MappingImportResult:
    with CatalogueRepository(database) as catalogue:
        return catalogue.derive_name_mappings_from_known_japanese_names()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Map Japanese reprints whose exact Japanese name has one trusted English equivalent."
    )
    parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    args = parser.parse_args()
    result = derive_japanese_names(args.database)
    print(f"Derived {result.mapped} English-name mappings ({result.derived} parallel variants derived).")


if __name__ == "__main__":
    main()
