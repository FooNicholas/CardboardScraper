"""Build the verified catalogue assets uploaded with a desktop release."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
from pathlib import Path

from scraperbot.distribution import CatalogueSnapshotError, create_catalogue_snapshot


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create a validated JP Price Checker SQLite snapshot and release manifest."
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=Path("data/catalogue.sqlite3"),
        help="Curator-maintained SQLite catalogue to package.",
    )
    parser.add_argument("--output", type=Path, required=True, help="Empty or disposable release-asset directory.")
    parser.add_argument(
        "--version",
        default=datetime.now(UTC).date().isoformat(),
        help="Human-readable catalogue version shown to users (default: current UTC date).",
    )
    args = parser.parse_args()
    try:
        snapshot = create_catalogue_snapshot(args.database, args.output, version=args.version)
    except CatalogueSnapshotError as error:
        parser.exit(2, f"Catalogue snapshot was not created: {error}\n")
    print(
        f"Created catalogue {snapshot.catalogue_version}: {snapshot.database_file} "
        f"({snapshot.size_bytes:,} bytes, SHA-256 {snapshot.sha256})."
    )


if __name__ == "__main__":
    main()
