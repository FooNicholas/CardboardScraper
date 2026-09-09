"""Link exact official English print names to the Japanese print master."""

from __future__ import annotations

import argparse
from pathlib import Path

from scraperbot.catalogue.repository import CatalogueRepository


def link_official_english_names(database: Path) -> tuple[int, int]:
    with CatalogueRepository(database) as catalogue:
        mappings = catalogue.official_english_name_mappings()
        result = catalogue.apply_name_mappings(mappings)
    return len(mappings), result.preserved_official


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Link exact official English card names to Japanese print records."
    )
    parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    args = parser.parse_args()
    candidates, linked = link_official_english_names(args.database)
    print(f"Linked {linked} official-English print references from {candidates} exact print matches.")


if __name__ == "__main__":
    main()
