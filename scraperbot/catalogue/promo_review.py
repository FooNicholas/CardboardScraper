"""Export and apply explicit English-name reviews for Yuyu-Tei D-Promo prints."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from scraperbot.catalogue.repository import HELD_UTILITY_PROMO_NAMES, CatalogueRepository, MappingImportResult
from scraperbot.models import EnglishNameMapping


@dataclass(frozen=True, slots=True)
class PromoReviewExportResult:
    entries: int
    held_utility_entries: int


@dataclass(frozen=True, slots=True)
class PromoReviewApplyResult:
    approved_records: int
    ignored_records: int
    mapping_result: MappingImportResult


def export_yuyutei_promo_review(database: Path, output: Path) -> PromoReviewExportResult:
    """Write the unmapped, actually listed D-PR print queue for human review."""
    with CatalogueRepository(database) as catalogue:
        entries = catalogue.unmapped_yuyutei_promo_entries()
    review_entries = [
        {
            "set_code": entry.set_code,
            "collector_number": entry.collector_number,
            "japanese_name": entry.japanese_name,
            "yuyutei_listing_url": entry.listing_url,
            "yuyutei_page_slug": entry.page_slug,
            "status": "held" if entry.japanese_name in HELD_UTILITY_PROMO_NAMES else "needs_review",
            "english_name": None,
            "aliases": [],
            "source_url": None,
            "notes": "",
        }
        for entry in entries
    ]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "scope": "Yuyu-Tei-listed Japanese D-PR prints without an English mapping",
                "entries": review_entries,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return PromoReviewExportResult(
        entries=len(review_entries),
        held_utility_entries=sum(entry["status"] == "held" for entry in review_entries),
    )


def apply_yuyutei_promo_review(database: Path, review_file: Path) -> PromoReviewApplyResult:
    """Apply only explicit approved reviews that belong to a Yuyu-Tei D-PR entry."""
    payload = json.loads(review_file.read_text(encoding="utf-8"))
    records = payload.get("entries") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        raise ValueError("Review file must contain an 'entries' list.")
    approved_records = ignored_records = 0
    mappings: list[EnglishNameMapping] = []
    fallback_source_url = review_file.resolve().as_uri()
    with CatalogueRepository(database) as catalogue:
        for record in records:
            if not isinstance(record, dict) or record.get("status") != "approved":
                continue
            set_code = str(record.get("set_code", ""))
            collector_number = str(record.get("collector_number", ""))
            english_name = str(record.get("english_name", "")).strip()
            entry = catalogue.promo_catalogue_entry("yuyutei", set_code, collector_number)
            if (
                not english_name
                or entry is None
                or entry.japanese_name in HELD_UTILITY_PROMO_NAMES
            ):
                ignored_records += 1
                continue
            aliases = record.get("aliases", [])
            if not isinstance(aliases, list) or not all(isinstance(alias, str) for alias in aliases):
                ignored_records += 1
                continue
            approved_records += 1
            mappings.append(
                EnglishNameMapping(
                    set_code=set_code,
                    collector_number=collector_number,
                    rarity="",
                    english_name=english_name,
                    aliases=tuple(aliases),
                    source="promo-review",
                    source_url=str(record.get("source_url") or fallback_source_url),
                    status="reviewed",
                )
            )
        result = catalogue.apply_name_mappings(mappings)
    return PromoReviewApplyResult(approved_records, ignored_records, result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Export or apply reviewed English names for Yuyu-Tei D-Promo listings.")
    subparsers = parser.add_subparsers(dest="command", required=True)
    export_parser = subparsers.add_parser("export", help="Write Yuyu-Tei-listed unmapped D-PR cards to a review JSON file.")
    export_parser.add_argument("output", type=Path)
    export_parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    apply_parser = subparsers.add_parser("apply", help="Apply approved entries from a review JSON file.")
    apply_parser.add_argument("review_file", type=Path)
    apply_parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    args = parser.parse_args()
    if args.command == "export":
        result = export_yuyutei_promo_review(args.database, args.output)
        print(f"Wrote {result.entries} review entries ({result.held_utility_entries} utility entries held).")
        return
    try:
        result = apply_yuyutei_promo_review(args.database, args.review_file)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        parser.exit(2, f"Promo review apply failed: {error}\n")
    print(
        f"Applied {result.mapping_result.mapped} mappings from {result.approved_records} approved records; "
        f"ignored {result.ignored_records} invalid or out-of-scope records."
    )


if __name__ == "__main__":
    main()
