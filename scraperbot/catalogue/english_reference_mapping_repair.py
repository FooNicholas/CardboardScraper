"""Archive legacy JP mappings derived from English printed references."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from scraperbot.catalogue.repository import CatalogueRepository


@dataclass(frozen=True, slots=True)
class EnglishReferenceMappingRepairResult:
    archived_mappings: int
    identities: int
    linked_printings: int


def repair_english_reference_mappings(database: Path) -> EnglishReferenceMappingRepairResult:
    """Archive unsafe equality claims while retaining all English serial data."""
    with CatalogueRepository(database) as catalogue:
        archived, links = catalogue.archive_english_reference_number_mappings()
        identities = int(catalogue.connection.execute("SELECT COUNT(*) FROM card_identities").fetchone()[0])
    return EnglishReferenceMappingRepairResult(archived, identities, links)


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Archive legacy Japanese mappings inferred from English set/serial numbers "
            "and rebuild Japanese-name identities."
        )
    )
    parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    args = parser.parse_args()
    result = repair_english_reference_mappings(args.database)
    print(
        f"Archived {result.archived_mappings} English-reference mapping claims; rebuilt "
        f"{result.identities} Japanese-name identities linking {result.linked_printings} Japanese prints."
    )


if __name__ == "__main__":
    main()
