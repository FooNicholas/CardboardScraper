"""Resumable import of Japanese D-Promo retailer locations."""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path

from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.catalogue.yuyutei_promo_source import PromoCatalogueSourceError, YuyuTeiPromoCatalogueSource


@dataclass(frozen=True, slots=True)
class PromoCatalogueImportResult:
    pages_imported: int
    pages_skipped: int
    pages_without_entries: int
    entries_imported: int


async def import_yuyutei_promo_pages(
    database: Path,
    page_slugs: Iterable[str] = (),
    *,
    all_pages: bool = False,
    refresh: bool = False,
    progress: Callable[[int, int, str, int | None], None] | None = None,
    source: YuyuTeiPromoCatalogueSource | None = None,
) -> PromoCatalogueImportResult:
    """Import named Yuyu-Tei D-Promo ranges and checkpoint each completed page."""
    source = source or YuyuTeiPromoCatalogueSource()
    pages = list(dict.fromkeys(page.strip().lower() for page in page_slugs if page.strip()))
    if all_pages and pages:
        raise ValueError("Choose named pages or all available D-Promo pages, not both.")
    if all_pages:
        pages = await source.list_page_slugs()
    if not pages:
        raise ValueError("Supply at least one Yuyu-Tei D-Promo page.")
    pages_imported = pages_skipped = entries_imported = 0
    pages_without_entries = 0
    with CatalogueRepository(database) as catalogue:
        for index, page_slug in enumerate(pages, start=1):
            if catalogue.has_promo_catalogue_page(source.store_id, page_slug) and not refresh:
                pages_skipped += 1
                if progress:
                    progress(index, len(pages), page_slug, None)
                continue
            entries = await source.entries_for_page(page_slug)
            if not entries:
                # A range control can exist before the retailer has an active
                # listing in that range. Do not checkpoint it: a later --all
                # run must be able to discover newly listed cards.
                pages_without_entries += 1
                if progress:
                    progress(index, len(pages), page_slug, 0)
                continue
            entries_imported += catalogue.upsert_promo_catalogue_entries(entries)
            catalogue.mark_promo_catalogue_page_imported(
                source.store_id, page_slug, source.page_url(page_slug), len(entries)
            )
            pages_imported += 1
            if progress:
                progress(index, len(pages), page_slug, len(entries))
    return PromoCatalogueImportResult(pages_imported, pages_skipped, pages_without_entries, entries_imported)


def main() -> None:
    parser = argparse.ArgumentParser(description="Import exact Japanese D-Promo listing locations from Yuyu-Tei.")
    parser.add_argument(
        "--page",
        dest="pages",
        action="append",
        default=[],
        help="Yuyu-Tei promo page, e.g. dpromo-1200. Repeat for more ranges.",
    )
    parser.add_argument("--all", action="store_true", help="Import every D-Promo page exposed by Yuyu-Tei.")
    parser.add_argument("--refresh", action="store_true", help="Re-read pages that already have checkpoints.")
    parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    args = parser.parse_args()
    if not args.pages and not args.all:
        parser.error("supply at least one --page, such as dpromo-1200, or choose --all")
    if args.pages and args.all:
        parser.error("choose named --page values or --all, not both")
    try:
        result = asyncio.run(
            import_yuyutei_promo_pages(
                args.database,
                args.pages,
                all_pages=args.all,
                refresh=args.refresh,
                progress=lambda index, total, page, count: print(
                    f"[{index}/{total}] {page}: "
                    f"{'already imported' if count is None else f'{count} exact promo entries'}",
                    flush=True,
                ),
            )
        )
    except (PromoCatalogueSourceError, ValueError) as error:
        parser.exit(2, f"D-Promo import failed: {error}\n")
    print(
        f"Imported {result.entries_imported} promo entries from {result.pages_imported} page(s); "
        f"skipped {result.pages_skipped} completed page(s); "
        f"{result.pages_without_entries} range page(s) currently had no listings."
    )


if __name__ == "__main__":
    main()
