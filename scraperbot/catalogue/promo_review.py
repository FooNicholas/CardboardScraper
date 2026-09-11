"""Export and apply explicit English-name reviews for Yuyu-Tei D-Promo prints."""

from __future__ import annotations

import argparse
from collections import Counter
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from scraperbot.catalogue.repository import HELD_UTILITY_PROMO_NAMES, CatalogueRepository, MappingImportResult
from scraperbot.models import EnglishNameMapping, normalise_collector_number, normalise_set_code


@dataclass(frozen=True, slots=True)
class PromoReviewExportResult:
    entries: int
    held_utility_entries: int


@dataclass(frozen=True, slots=True)
class PromoReviewIssue:
    record_number: int
    serial: str
    reason: str


@dataclass(frozen=True, slots=True)
class PromoReviewApplyResult:
    approved_records: int
    ignored_records: int
    mapping_result: MappingImportResult
    issues: tuple[PromoReviewIssue, ...] = ()


def _identity(catalogue: CatalogueRepository, number: str) -> sqlite3.Row | None:
    return catalogue.connection.execute(
        """SELECT j.*, m.english_name AS mapped_name,
                  o.japanese_name AS official_name, o.source_url AS official_url
           FROM japanese_prints j
           LEFT JOIN english_name_mappings m ON m.japanese_print_id=j.id
           LEFT JOIN official_promo_identities o ON o.collector_number=j.collector_number
           WHERE j.set_code='DPR' AND j.collector_number=?""",
        (number,),
    ).fetchone()


def export_yuyutei_promo_review(database: Path, output: Path) -> PromoReviewExportResult:
    """Export current canonical identity and evidence without overwriting reviews."""
    review_entries = []
    with CatalogueRepository(database) as catalogue:
        # One consistent local snapshot; no retailer requests or translations.
        catalogue.connection.execute("BEGIN")
        evidence: dict[str, list[dict[str, str]]] = {}
        for row in catalogue.eligible_name_mapping_evidence():
            evidence.setdefault(row['japanese_name'], []).append({
                key: row[key] for key in (
                    'set_code', 'collector_number', 'english_name', 'mapping_source', 'mapping_source_url'
                )
            })
        for entry in catalogue.unmapped_yuyutei_promo_entries():
            identity = _identity(catalogue, entry.collector_number)
            assert identity is not None
            name = identity['japanese_name']
            held = name in HELD_UTILITY_PROMO_NAMES
            candidates = [] if held else evidence.get(name, [])
            names = {candidate['english_name'] for candidate in candidates}
            reason = (
                'serial_only_utility' if held else
                'conflicting_candidates' if len(names) > 1 else
                'exact_name_candidate' if names else 'no_exact_name_candidate'
            )
            review_entries.append({
                "set_code": entry.set_code,
                "collector_number": entry.collector_number,
                "japanese_name": name,
                "japanese_source_url": identity['source_url'],
                "official_japanese_name": identity['official_name'],
                "official_source_url": identity['official_url'],
                "retailer_japanese_name": entry.japanese_name,
                "yuyutei_listing_url": entry.listing_url,
                "yuyutei_page_slug": entry.page_slug,
                "status": "held" if held else "needs_review",
                "reason": reason,
                "candidates": candidates,
                "english_name": None,
                "aliases": [],
                "source_url": None,
                "notes": "",
            })
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(
            {
                "schema_version": 2,
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "scope": "Yuyu-Tei-listed Japanese D-PR prints without an English mapping",
                "entries": review_entries,
            },
            ensure_ascii=False,
            indent=2,
        ) + "\n")
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
    if payload.get('schema_version', 1) not in (1, 2):
        raise ValueError("Unsupported review schema version; export a fresh review file.")
    approved_records = ignored_records = 0
    mappings: list[EnglishNameMapping] = []
    issues: list[PromoReviewIssue] = []
    fallback_source_url = review_file.resolve().as_uri()

    def serial_key(record: dict) -> tuple[str, str]:
        code, number = record.get('set_code'), record.get('collector_number')
        if not isinstance(code, str) or not isinstance(number, str) or not number.isascii() or not number.isdigit():
            return ('', '')
        return normalise_set_code(code), normalise_collector_number(number)

    counts = Counter(serial_key(record) for record in records
                     if isinstance(record, dict) and record.get('status') == 'approved')
    with CatalogueRepository(database) as catalogue:
        # Identity checks and writes share a transaction so a catalogue refresh
        # cannot change the target between validation and applying its review.
        catalogue.connection.execute("BEGIN IMMEDIATE")
        for index, record in enumerate(records, start=1):
            if not isinstance(record, dict) or record.get("status") != "approved":
                continue
            set_code, collector_number = serial_key(record)
            english_name = record.get("english_name")
            entry = catalogue.promo_catalogue_entry("yuyutei", set_code, collector_number)
            identity = _identity(catalogue, collector_number) if set_code == 'DPR' else None
            aliases = record.get("aliases", [])
            reason = None
            if set_code != 'DPR' or entry is None or identity is None:
                reason = 'out_of_scope'
            elif counts[(set_code, collector_number)] > 1:
                reason = 'duplicate_approval'
            elif identity['japanese_name'] in HELD_UTILITY_PROMO_NAMES:
                reason = 'serial_only_utility'
            elif record.get('japanese_name') != identity['japanese_name']:
                reason = 'stale_or_missing_japanese_identity'
            elif identity['official_name'] and identity['official_name'] != identity['japanese_name']:
                reason = 'official_identity_conflict'
            elif payload.get('schema_version') == 2 and record.get('japanese_source_url') != identity['source_url']:
                reason = 'stale_japanese_source'
            elif identity['mapped_name'] is not None:
                reason = 'already_mapped'
            elif not isinstance(english_name, str) or not english_name.strip():
                reason = 'invalid_english_name'
            elif not isinstance(aliases, list) or not all(isinstance(alias, str) and alias.strip() for alias in aliases):
                reason = 'invalid_aliases'
            elif record.get('source_url') is not None and not isinstance(record['source_url'], str):
                reason = 'invalid_source_url'
            if reason:
                ignored_records += 1
                issues.append(PromoReviewIssue(index, f'{set_code}/{collector_number}', reason))
                continue
            approved_records += 1
            mappings.append(
                EnglishNameMapping(
                    set_code=set_code,
                    collector_number=collector_number,
                    rarity="",
                    english_name=english_name.strip(),
                    aliases=tuple(aliases),
                    source="promo-review",
                    source_url=str(record.get("source_url") or fallback_source_url),
                    status="reviewed",
                )
            )
        result = catalogue.apply_name_mappings(mappings, derive_same_name=False)
    return PromoReviewApplyResult(approved_records, ignored_records, result, tuple(issues))


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
        try:
            result = export_yuyutei_promo_review(args.database, args.output)
        except OSError as error:
            parser.exit(2, f"Promo review export failed (use a new filename): {error}\n")
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
    for issue in result.issues:
        print(f"Skipped record {issue.record_number} ({issue.serial}): {issue.reason}")


if __name__ == "__main__":
    main()
