"""Read-only readiness reporting for the local Japanese card catalogue."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from scraperbot.catalogue.repository import HELD_UTILITY_PROMO_NAMES, CatalogueRepository


@dataclass(frozen=True, slots=True)
class CatalogueStatus:
    """Counts that identify the next safe local catalogue-maintenance action."""

    japanese_prints: int
    searchable_japanese_prints: int
    unmapped_japanese_prints: int
    promo_prints: int
    unmapped_promo_prints: int
    held_utility_promo_prints: int
    unresolved_playable_promo_prints: int
    special_series_sets: int
    special_series_prints: int
    unmapped_special_series_prints: int
    yuyutei_promo_entries: int


def catalogue_status(database: Path) -> CatalogueStatus:
    """Return a local-only summary without fetching or scraping anything."""
    with CatalogueRepository(database) as catalogue:
        connection = catalogue.connection
        japanese_prints = catalogue.japanese_count
        unmapped = catalogue.unmapped_japanese_count()
        promo_prints = int(
            connection.execute(
                "SELECT COUNT(*) FROM japanese_prints WHERE set_code IN ('DPR', 'CP')"
            ).fetchone()[0]
        )
        unmapped_promos = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM japanese_prints AS j
                LEFT JOIN english_name_mappings AS m ON m.japanese_print_id = j.id
                WHERE j.set_code IN ('DPR', 'CP') AND m.japanese_print_id IS NULL
                """
            ).fetchone()[0]
        )
        held = int(
            connection.execute(
                """
                SELECT COUNT(*)
                FROM japanese_prints AS j
                LEFT JOIN english_name_mappings AS m ON m.japanese_print_id = j.id
                WHERE j.set_code IN ('DPR', 'CP')
                  AND j.japanese_name IN (?, ?, ?)
                  AND m.japanese_print_id IS NULL
                """,
                tuple(HELD_UTILITY_PROMO_NAMES),
            ).fetchone()[0]
        )
        special_sets = [
            set_code
            for set_code in catalogue.region_specific_japanese_set_codes()
            if set_code not in {"DPR", "CP"}
        ]
        if special_sets:
            placeholders = ", ".join("?" for _ in special_sets)
            special_prints = int(
                connection.execute(
                    f"SELECT COUNT(*) FROM japanese_prints WHERE set_code IN ({placeholders})",
                    special_sets,
                ).fetchone()[0]
            )
            unmapped_special = int(
                connection.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM japanese_prints AS j
                    LEFT JOIN english_name_mappings AS m ON m.japanese_print_id = j.id
                    WHERE j.set_code IN ({placeholders}) AND m.japanese_print_id IS NULL
                    """,
                    special_sets,
                ).fetchone()[0]
            )
        else:
            special_prints = unmapped_special = 0
        return CatalogueStatus(
            japanese_prints=japanese_prints,
            searchable_japanese_prints=japanese_prints - unmapped,
            unmapped_japanese_prints=unmapped,
            promo_prints=promo_prints,
            unmapped_promo_prints=unmapped_promos,
            held_utility_promo_prints=held,
            unresolved_playable_promo_prints=unmapped_promos - held,
            special_series_sets=len(special_sets),
            special_series_prints=special_prints,
            unmapped_special_series_prints=unmapped_special,
            yuyutei_promo_entries=int(
                connection.execute(
                    "SELECT COUNT(*) FROM promo_catalogue_entries WHERE store_id = 'yuyutei'"
                ).fetchone()[0]
            ),
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Show local catalogue coverage and outstanding Japanese promo mapping work."
    )
    parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    parser.add_argument("--json", action="store_true", help="Print a machine-readable JSON summary.")
    args = parser.parse_args()
    status = catalogue_status(args.database)
    if args.json:
        print(json.dumps(asdict(status), indent=2, sort_keys=True))
        return
    print(f"Japanese prints: {status.japanese_prints}")
    print(f"Searchable by English name: {status.searchable_japanese_prints}")
    print(f"Unmapped Japanese prints: {status.unmapped_japanese_prints}")
    print(
        "Promos: "
        f"{status.promo_prints} total; {status.unresolved_playable_promo_prints} playable names need review; "
        f"{status.held_utility_promo_prints} utility prints held"
    )
    print(
        "Special Series: "
        f"{status.special_series_sets} sets, {status.special_series_prints} prints, "
        f"{status.unmapped_special_series_prints} unmapped"
    )
    print(f"Yuyu-Tei D-Promo entries: {status.yuyutei_promo_entries}")


if __name__ == "__main__":
    main()
