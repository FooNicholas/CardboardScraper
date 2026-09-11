"""Rebuild Japanese promo mappings without trusting cross-region serial equality."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from scraperbot.catalogue.repository import CatalogueRepository, HELD_UTILITY_PROMO_NAMES
from scraperbot.models import normalise_set_code


@dataclass(frozen=True, slots=True)
class PromoMappingRepairResult:
    archived_english_references: int
    removed_user_search_records: int
    restored_direct_fandom: int
    mapped_by_japanese_name: int
    held_utility_prints: int
    unresolved: int


def repair_promo_mappings(
    database: Path,
    set_codes: tuple[str, ...] = ("DPR",),
) -> PromoMappingRepairResult:
    """Rebuild selected Japanese promo family mappings from trusted evidence.

    Only explicit Fandom cross-print links are retained. The generic English
    D-Promo list cannot identify a Japanese promo by equal serial: regional
    sequences reuse numbers for unrelated cards (for example D-PR/953).
    Remaining promo prints can inherit one unambiguous Fandom-backed English
    name from a non-promo Japanese printing. Utility printings deliberately use
    Japanese serial search without English-name mapping. English
    promo references are archived for internal cross-print research and are
    never Japanese identity evidence.
    """
    wanted = tuple(sorted({normalise_set_code(code) for code in set_codes if code.strip()}))
    if not wanted:
        raise ValueError("Supply at least one promo print family.")

    with CatalogueRepository(database) as catalogue:
        reviewed = catalogue.reviewed_promo_mappings(wanted)
        # Direct Fandom evidence must be saved before the rebuild removes all
        # prior promo mapping rows.
        direct_mappings = [
            mapping
            for mapping in catalogue.direct_fandom_mappings(wanted)
            if mapping.source in {"fandom-cross-print", "fandom-japanese-promo"}
        ]
        archived, removed = catalogue.clear_promo_mappings_for_rebuild(wanted)
        restored = catalogue.apply_name_mappings(direct_mappings).mapped
        catalogue.apply_name_mappings(reviewed)
        inferred = catalogue.unambiguous_fandom_name_mappings(wanted)
        name_matched = catalogue.apply_name_mappings(inferred).mapped
        remaining = catalogue.unmapped_japanese_prints(wanted)
        held_utility = sum(card.japanese_name in HELD_UTILITY_PROMO_NAMES for card in remaining)
        return PromoMappingRepairResult(
            archived_english_references=archived,
            removed_user_search_records=removed,
            restored_direct_fandom=restored,
            mapped_by_japanese_name=name_matched,
            held_utility_prints=held_utility,
            unresolved=len(remaining) - held_utility,
        )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Rebuild Japanese promo mappings without matching English promo serials."
    )
    parser.add_argument(
        "--set",
        dest="sets",
        action="append",
        default=["D-PR"],
        help="Promo family to repair (default: D-PR).",
    )
    parser.add_argument("--database", type=Path, default=Path("data/catalogue.sqlite3"))
    args = parser.parse_args()
    result = repair_promo_mappings(args.database, tuple(args.sets))
    print(
        "Archived "
        f"{result.archived_english_references} English references; removed "
        f"{result.removed_user_search_records} stale search records; restored "
        f"{result.restored_direct_fandom} direct Fandom mappings; mapped "
        f"{result.mapped_by_japanese_name} by exact Japanese name; held "
        f"{result.held_utility_prints} utility prints; "
        f"{result.unresolved} playable prints still need review."
    )


if __name__ == "__main__":
    main()
