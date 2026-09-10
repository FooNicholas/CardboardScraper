"""Rebuild Japanese promo mappings without trusting cross-region serial equality."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import EnglishNameMapping, normalise_set_code


UTILITY_PROMO_NAME_MAPPINGS = {
    "エネルギー": ("Energy", ()),
    "エネルギージェネレーター": ("Energy Generator", ()),
    "四精織り成す清浄の盾": (
        "Elementaria Sanctitude",
        ("Quick Shield", "Quickshield"),
    ),
}


@dataclass(frozen=True, slots=True)
class PromoMappingRepairResult:
    archived_english_references: int
    removed_user_search_records: int
    restored_direct_fandom: int
    mapped_by_japanese_name: int
    mapped_shared_utility_names: int
    unresolved: int


def repair_promo_mappings(
    database: Path,
    set_codes: tuple[str, ...] = ("DPR",),
) -> PromoMappingRepairResult:
    """Rebuild selected Japanese promo family mappings from trusted evidence.

    Existing direct Fandom links are retained. Remaining promo prints can
    inherit one unambiguous direct Fandom English name from a non-promo
    Japanese printing. Energy, Energy Generator, and Quick Shield prints use
    their shared reviewed names, so a single name search can list all of their
    Japanese promo printings. English promo references are archived for
    internal cross-print research and are never Japanese identity evidence.
    """
    wanted = tuple(sorted({normalise_set_code(code) for code in set_codes if code.strip()}))
    if not wanted:
        raise ValueError("Supply at least one promo print family.")

    with CatalogueRepository(database) as catalogue:
        promo_prints = catalogue.japanese_prints(wanted)
        # Direct Fandom evidence must be saved before the rebuild removes all
        # prior promo mapping rows.
        direct_mappings = [
            mapping
            for mapping in catalogue.direct_fandom_mappings(wanted)
        ]
        archived, removed = catalogue.clear_promo_mappings_for_rebuild(wanted)
        restored = catalogue.apply_name_mappings(direct_mappings).mapped
        inferred = catalogue.unambiguous_fandom_name_mappings(wanted)
        name_matched = catalogue.apply_name_mappings(inferred).mapped
        utility_mappings = [
            EnglishNameMapping(
                set_code=card.set_code,
                collector_number=card.collector_number,
                rarity=card.rarity,
                english_name=UTILITY_PROMO_NAME_MAPPINGS[card.japanese_name][0],
                aliases=UTILITY_PROMO_NAME_MAPPINGS[card.japanese_name][1],
                source="promo-utility-review",
                source_url="local://user-approved-promo-utility-names",
                status="reviewed",
            )
            for card in promo_prints
            if card.japanese_name in UTILITY_PROMO_NAME_MAPPINGS
        ]
        shared_utility = catalogue.apply_name_mappings(utility_mappings).mapped
        remaining = catalogue.unmapped_japanese_prints(wanted)
        return PromoMappingRepairResult(
            archived_english_references=archived,
            removed_user_search_records=removed,
            restored_direct_fandom=restored,
            mapped_by_japanese_name=name_matched,
            mapped_shared_utility_names=shared_utility,
            unresolved=len(remaining),
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
        f"{result.mapped_by_japanese_name} by exact Japanese name; mapped "
        f"{result.mapped_shared_utility_names} shared utility prints; "
        f"{result.unresolved} playable prints still need review."
    )


if __name__ == "__main__":
    main()
