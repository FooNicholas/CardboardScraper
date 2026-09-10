"""SQLite-backed card catalogue with fast name and alias lookups."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
from typing import Iterable

from rapidfuzz import fuzz

from scraperbot.models import (
    CardPrint,
    EnglishNameMapping,
    JapaneseCardPrint,
    PromoCatalogueEntry,
    normalise_collector_number,
    normalise_set_code,
    normalise_text,
)


PROMO_PRINT_SET_CODES = frozenset({"DPR", "CP"})

# These shared-name utility prints remain in the Japanese master while their
# user-facing search and selection workflow is on hold. Do not add a generic
# English mapping during an ordinary Fandom or repair import.
HELD_UTILITY_PROMO_NAMES = frozenset(
    {
        "エネルギー",
        "エネルギージェネレーター",
        "四精織り成す清浄の盾",
    }
)


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS card_prints (
    id INTEGER PRIMARY KEY,
    set_code TEXT NOT NULL,
    collector_number TEXT NOT NULL,
    rarity TEXT NOT NULL,
    english_name TEXT NOT NULL,
    japanese_name TEXT,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    normalised_name TEXT NOT NULL,
    normalised_aliases TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    source_url TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(set_code, collector_number, rarity)
);

CREATE INDEX IF NOT EXISTS idx_card_prints_name ON card_prints(normalised_name);
CREATE INDEX IF NOT EXISTS idx_card_prints_rarity ON card_prints(rarity);
CREATE INDEX IF NOT EXISTS idx_card_prints_source ON card_prints(source);

CREATE TABLE IF NOT EXISTS english_print_references (
    id INTEGER PRIMARY KEY,
    set_code TEXT NOT NULL,
    collector_number TEXT NOT NULL,
    rarity TEXT NOT NULL,
    english_name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    source TEXT NOT NULL,
    source_url TEXT,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(set_code, collector_number, rarity)
);

CREATE INDEX IF NOT EXISTS idx_english_print_references_name
ON english_print_references(english_name);

CREATE TABLE IF NOT EXISTS japanese_prints (
    id INTEGER PRIMARY KEY,
    set_code TEXT NOT NULL,
    collector_number TEXT NOT NULL,
    rarity TEXT NOT NULL DEFAULT '',
    japanese_name TEXT NOT NULL,
    source_url TEXT NOT NULL,
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(set_code, collector_number)
);

CREATE INDEX IF NOT EXISTS idx_japanese_prints_set ON japanese_prints(set_code);

CREATE TABLE IF NOT EXISTS promo_catalogue_entries (
    store_id TEXT NOT NULL,
    page_slug TEXT NOT NULL,
    set_code TEXT NOT NULL,
    collector_number TEXT NOT NULL,
    japanese_name TEXT NOT NULL,
    listing_url TEXT NOT NULL,
    source_page_url TEXT NOT NULL,
    product_id TEXT,
    first_imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, set_code, collector_number)
);

CREATE INDEX IF NOT EXISTS idx_promo_catalogue_entries_page
ON promo_catalogue_entries(store_id, page_slug);

CREATE TABLE IF NOT EXISTS promo_catalogue_imports (
    store_id TEXT NOT NULL,
    page_slug TEXT NOT NULL,
    source_page_url TEXT NOT NULL,
    entry_count INTEGER NOT NULL,
    completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (store_id, page_slug)
);

CREATE TABLE IF NOT EXISTS japanese_expansion_imports (
    expansion_id INTEGER PRIMARY KEY,
    completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS english_name_mappings (
    japanese_print_id INTEGER PRIMARY KEY REFERENCES japanese_prints(id) ON DELETE CASCADE,
    english_name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    mapping_source TEXT NOT NULL,
    mapping_source_url TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'provisional',
    imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE IF NOT EXISTS card_search USING fts5(
    print_id UNINDEXED,
    english_name,
    japanese_name,
    aliases,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


@dataclass(frozen=True, slots=True)
class MappingImportResult:
    mapped: int
    derived: int
    unmatched: int
    preserved_official: int


class CatalogueRepository:
    """Owns the local card catalogue database.

    The public lookup API accepts only user-facing names. Store connectors use
    the selected :class:`CardPrint` object's hidden print key afterwards.
    """

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.executescript(SCHEMA)

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "CatalogueRepository":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    @property
    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM card_prints").fetchone()[0])

    @property
    def japanese_count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM japanese_prints").fetchone()[0])

    def upsert(self, card: CardPrint) -> CardPrint:
        stored = self._upsert(card)
        self.connection.commit()
        return stored

    def import_many(self, cards: Iterable[CardPrint]) -> int:
        """Import a batch in one SQLite transaction instead of one per card."""
        imported = 0
        try:
            for card in cards:
                self._upsert(card)
                imported += 1
        except Exception:
            self.connection.rollback()
            raise
        self.connection.commit()
        return imported

    def import_japanese_many(self, cards: Iterable[JapaneseCardPrint]) -> int:
        """Store official Japanese print data without requiring an English name."""
        imported = 0
        try:
            for card in cards:
                self._upsert_japanese(card)
                imported += 1
        except Exception:
            self.connection.rollback()
            raise
        self.connection.commit()
        return imported

    def apply_name_mappings(self, mappings: Iterable[EnglishNameMapping]) -> MappingImportResult:
        """Layer community English names over the Japanese print master.

        A matching official-English card is never overwritten. Its publication
        remains the authoritative replacement for a provisional mapping.
        """
        mapped = derived = unmatched = preserved_official = 0
        mappings_by_japanese_name: dict[tuple[str, str], EnglishNameMapping] = {}
        try:
            for mapping in mappings:
                japanese = self._japanese_by_reference(mapping.set_code, mapping.collector_number)
                if not japanese:
                    unmatched += 1
                    continue
                # Japanese and English promo serials use independent regional
                # sequences. Never let an equal D-PR/CP reference turn into a
                # false official match (for example JP D-PR/953 and EN
                # D-PR/953EN name different cards).
                is_region_specific_promo = japanese["set_code"] in PROMO_PRINT_SET_CODES
                if (
                    is_region_specific_promo
                    and japanese["japanese_name"] in HELD_UTILITY_PROMO_NAMES
                ):
                    continue
                if is_region_specific_promo:
                    # An upgrade may encounter legacy official promo records
                    # before the explicit repair command runs. Preserve them
                    # as English-only evidence before this Japanese mapping
                    # replaces the shared catalogue key.
                    for legacy_row in self._official_english_by_reference(
                        mapping.set_code, mapping.collector_number
                    ):
                        self._archive_english_print_reference(legacy_row)
                    official_rows = []
                else:
                    official_rows = self._official_english_by_reference(
                        mapping.set_code, mapping.collector_number
                    )
                existing_mapping = self.connection.execute(
                    "SELECT mapping_source FROM english_name_mappings WHERE japanese_print_id = ?",
                    (japanese["id"],),
                ).fetchone()
                if (
                    not is_region_specific_promo
                    and existing_mapping
                    and existing_mapping["mapping_source"] == "official-english"
                    and (
                    mapping.source != "official-english"
                    )
                ):
                    preserved_official += 1
                    continue
                # An exact official-English print is a stronger source than a
                # community page, even when the caller has not synced the
                # official links beforehand.
                if official_rows and mapping.source != "official-english":
                    official = official_rows[0]
                    mapping = EnglishNameMapping(
                        set_code=official["set_code"],
                        collector_number=official["collector_number"],
                        rarity=official["rarity"] or japanese["rarity"],
                        english_name=official["english_name"],
                        aliases=tuple(json.loads(official["aliases_json"])),
                        source="official-english",
                        source_url=official["source_url"] or "https://en.cf-vanguard.com/cardlist/",
                        status="official",
                    )
                rarity = mapping.rarity or japanese["rarity"]
                if mapping.rarity and mapping.rarity != japanese["rarity"]:
                    self.connection.execute(
                        "UPDATE japanese_prints SET rarity = ?, imported_at = CURRENT_TIMESTAMP WHERE id = ?",
                        (mapping.rarity, japanese["id"]),
                    )
                    japanese = self._japanese_by_reference(mapping.set_code, mapping.collector_number)
                    assert japanese is not None
                mappings_by_japanese_name.setdefault(
                    (mapping.set_code, japanese["japanese_name"]), mapping
                )
                self.connection.execute(
                    """
                    INSERT INTO english_name_mappings (
                        japanese_print_id, english_name, aliases_json, mapping_source,
                        mapping_source_url, status
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(japanese_print_id) DO UPDATE SET
                        english_name = excluded.english_name,
                        aliases_json = excluded.aliases_json,
                        mapping_source = excluded.mapping_source,
                        mapping_source_url = excluded.mapping_source_url,
                        status = excluded.status,
                        imported_at = CURRENT_TIMESTAMP
                    """,
                    (
                        japanese["id"],
                        mapping.english_name,
                        json.dumps(mapping.aliases, ensure_ascii=False),
                        mapping.source,
                        mapping.source_url,
                        mapping.status,
                    ),
                )
                if official_rows:
                    self._link_japanese_name_to_official_cards(official_rows, japanese["japanese_name"])
                    preserved_official += 1
                    continue
                self._upsert(
                    CardPrint(
                        set_code=mapping.set_code,
                        collector_number=mapping.collector_number,
                        rarity=rarity,
                        english_name=mapping.english_name,
                        japanese_name=japanese["japanese_name"],
                        aliases=mapping.aliases,
                        source=f"{mapping.source}-{mapping.status}",
                        source_url=mapping.source_url,
                    )
                )
                mapped += 1
            # Fandom's set page names the base printing of many cards but may
            # omit its FFR/SR/SEC parallel rows. Official Japanese data gives
            # those rows the same Japanese name, so they can safely inherit
            # that already-trusted English name without a machine translation.
            for (set_code, japanese_name), source_mapping in mappings_by_japanese_name.items():
                rows = self.connection.execute(
                    """
                    SELECT j.* FROM japanese_prints AS j
                    LEFT JOIN english_name_mappings AS m ON m.japanese_print_id = j.id
                    WHERE j.set_code = ? AND j.japanese_name = ? AND m.japanese_print_id IS NULL
                    """,
                    (set_code, japanese_name),
                ).fetchall()
                for japanese in rows:
                    self.connection.execute(
                        """
                        INSERT INTO english_name_mappings (
                            japanese_print_id, english_name, aliases_json, mapping_source,
                            mapping_source_url, status
                        ) VALUES (?, ?, ?, ?, ?, ?)
                        """,
                        (
                            japanese["id"],
                            source_mapping.english_name,
                            json.dumps(source_mapping.aliases, ensure_ascii=False),
                            f"{source_mapping.source}-derived",
                            source_mapping.source_url,
                            source_mapping.status,
                        ),
                    )
                    official_rows = self._official_english_by_reference(
                        set_code, japanese["collector_number"]
                    )
                    if official_rows:
                        self._link_japanese_name_to_official_cards(official_rows, japanese["japanese_name"])
                        preserved_official += 1
                        continue
                    self._upsert(
                        CardPrint(
                            set_code=set_code,
                            collector_number=japanese["collector_number"],
                            rarity=japanese["rarity"],
                            english_name=source_mapping.english_name,
                            japanese_name=japanese["japanese_name"],
                            aliases=source_mapping.aliases,
                            source=f"{source_mapping.source}-derived-{source_mapping.status}",
                            source_url=source_mapping.source_url,
                        )
                    )
                    mapped += 1
                    derived += 1
        except Exception:
            self.connection.rollback()
            raise
        self.connection.commit()
        return MappingImportResult(mapped, derived, unmatched, preserved_official)

    def official_english_name_mappings(self) -> list[EnglishNameMapping]:
        """Return exact Japanese/official-English matches for a local sync.

        Matching is by printed set code and collector number, never merely by
        card name. This retains distinct Japanese and English printings while
        making an official English name searchable for the Japanese print.
        """
        rows = self.connection.execute(
            """
            SELECT j.set_code, j.collector_number, j.rarity AS japanese_rarity,
                   c.rarity, c.english_name, c.aliases_json, c.source_url
            FROM japanese_prints AS j
            JOIN card_prints AS c
              ON c.set_code = j.set_code AND c.collector_number = j.collector_number
            WHERE c.source = 'official-english'
              AND j.set_code NOT IN ('DPR', 'CP')
            ORDER BY j.set_code, j.collector_number, c.rarity
            """
        ).fetchall()
        return [
            EnglishNameMapping(
                set_code=row["set_code"],
                collector_number=row["collector_number"],
                rarity=row["rarity"] or row["japanese_rarity"],
                english_name=row["english_name"],
                aliases=tuple(json.loads(row["aliases_json"])),
                source="official-english",
                source_url=row["source_url"] or "https://en.cf-vanguard.com/cardlist/",
                status="official",
            )
            for row in rows
        ]

    def direct_fandom_mappings(self, set_codes: Iterable[str]) -> list[EnglishNameMapping]:
        """Return direct Fandom evidence already attached to selected prints.

        Derived rows are deliberately excluded: a promo rebuild must preserve
        only evidence directly obtained from a Fandom set or card page.
        """
        wanted = self._normalised_set_codes(set_codes)
        if not wanted:
            return []
        placeholders = ", ".join("?" for _ in wanted)
        rows = self.connection.execute(
            f"""
            SELECT j.set_code, j.collector_number, j.rarity, m.english_name,
                   m.aliases_json, m.mapping_source, m.mapping_source_url, m.status
            FROM japanese_prints AS j
            JOIN english_name_mappings AS m ON m.japanese_print_id = j.id
            WHERE j.set_code IN ({placeholders})
              AND m.mapping_source IN ('fandom', 'fandom-cross-print')
            ORDER BY j.set_code, j.collector_number
            """,
            wanted,
        ).fetchall()
        return [
            EnglishNameMapping(
                set_code=row["set_code"],
                collector_number=row["collector_number"],
                rarity=row["rarity"],
                english_name=row["english_name"],
                aliases=tuple(json.loads(row["aliases_json"])),
                source=row["mapping_source"],
                source_url=row["mapping_source_url"],
                status=row["status"],
            )
            for row in rows
        ]

    def clear_promo_mappings_for_rebuild(self, set_codes: Iterable[str]) -> tuple[int, int]:
        """Archive English promo references and clear affected user-facing rows.

        Japanese and English promo serials are region-specific. The English
        rows remain in ``english_print_references`` for mapping evidence but
        must not occupy the Japanese catalogue key or appear in user searches.
        """
        wanted = self._normalised_set_codes(set_codes)
        if not wanted:
            return 0, 0
        if not set(wanted).issubset(PROMO_PRINT_SET_CODES):
            raise ValueError("Only region-specific promo print families may be rebuilt this way.")
        placeholders = ", ".join("?" for _ in wanted)
        try:
            official_rows = self.connection.execute(
                f"""
                SELECT * FROM card_prints
                WHERE set_code IN ({placeholders}) AND source = 'official-english'
                """,
                wanted,
            ).fetchall()
            for row in official_rows:
                self._archive_english_print_reference(row)
            card_ids = [
                int(row[0])
                for row in self.connection.execute(
                    f"SELECT id FROM card_prints WHERE set_code IN ({placeholders})", wanted
                ).fetchall()
            ]
            self.connection.execute(
                f"""
                DELETE FROM english_name_mappings
                WHERE japanese_print_id IN (
                    SELECT id FROM japanese_prints WHERE set_code IN ({placeholders})
                )
                """,
                wanted,
            )
            if card_ids:
                self.connection.executemany(
                    "DELETE FROM card_search WHERE print_id = ?", ((str(card_id),) for card_id in card_ids)
                )
            self.connection.execute(f"DELETE FROM card_prints WHERE set_code IN ({placeholders})", wanted)
        except Exception:
            self.connection.rollback()
            raise
        self.connection.commit()
        return len(official_rows), len(card_ids)

    def unmapped_japanese_prints(self, set_codes: Iterable[str]) -> list[JapaneseCardPrint]:
        """Return unmapped Japanese prints in the requested set families."""
        wanted = self._normalised_set_codes(set_codes)
        if not wanted:
            return []
        placeholders = ", ".join("?" for _ in wanted)
        rows = self.connection.execute(
            f"""
            SELECT j.* FROM japanese_prints AS j
            LEFT JOIN english_name_mappings AS m ON m.japanese_print_id = j.id
            WHERE j.set_code IN ({placeholders}) AND m.japanese_print_id IS NULL
            ORDER BY j.set_code, j.collector_number
            """,
            wanted,
        ).fetchall()
        return [
            JapaneseCardPrint(
                set_code=row["set_code"],
                collector_number=row["collector_number"],
                rarity=row["rarity"],
                japanese_name=row["japanese_name"],
                source_url=row["source_url"],
                id=int(row["id"]),
            )
            for row in rows
        ]

    def japanese_prints(self, set_codes: Iterable[str]) -> list[JapaneseCardPrint]:
        """Return every Japanese print in the requested set families."""
        wanted = self._normalised_set_codes(set_codes)
        if not wanted:
            return []
        placeholders = ", ".join("?" for _ in wanted)
        rows = self.connection.execute(
            f"""
            SELECT * FROM japanese_prints
            WHERE set_code IN ({placeholders})
            ORDER BY set_code, collector_number
            """,
            wanted,
        ).fetchall()
        return [
            JapaneseCardPrint(
                set_code=row["set_code"],
                collector_number=row["collector_number"],
                rarity=row["rarity"],
                japanese_name=row["japanese_name"],
                source_url=row["source_url"],
                id=int(row["id"]),
            )
            for row in rows
        ]

    def upsert_promo_catalogue_entries(self, entries: Iterable[PromoCatalogueEntry]) -> int:
        """Persist retailer promo locations without creating card-name mappings."""
        imported = 0
        try:
            for entry in entries:
                self.connection.execute(
                    """
                    INSERT INTO promo_catalogue_entries (
                        store_id, page_slug, set_code, collector_number, japanese_name,
                        listing_url, source_page_url, product_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(store_id, set_code, collector_number) DO UPDATE SET
                        page_slug = excluded.page_slug,
                        japanese_name = excluded.japanese_name,
                        listing_url = excluded.listing_url,
                        source_page_url = excluded.source_page_url,
                        product_id = excluded.product_id,
                        last_seen_at = CURRENT_TIMESTAMP
                    """,
                    (
                        entry.store_id,
                        entry.page_slug,
                        entry.set_code,
                        entry.collector_number,
                        entry.japanese_name,
                        entry.listing_url,
                        entry.source_page_url,
                        entry.product_id,
                    ),
                )
                imported += 1
        except Exception:
            self.connection.rollback()
            raise
        self.connection.commit()
        return imported

    def has_promo_catalogue_page(self, store_id: str, page_slug: str) -> bool:
        return self.connection.execute(
            """
            SELECT 1 FROM promo_catalogue_imports
            WHERE store_id = ? AND page_slug = ?
            """,
            (store_id.strip().lower(), page_slug.strip().lower()),
        ).fetchone() is not None

    def mark_promo_catalogue_page_imported(
        self, store_id: str, page_slug: str, source_page_url: str, entry_count: int
    ) -> None:
        """Checkpoint a completed page only after all its entries are stored."""
        self.connection.execute(
            """
            INSERT INTO promo_catalogue_imports (store_id, page_slug, source_page_url, entry_count)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(store_id, page_slug) DO UPDATE SET
                source_page_url = excluded.source_page_url,
                entry_count = excluded.entry_count,
                completed_at = CURRENT_TIMESTAMP
            """,
            (store_id.strip().lower(), page_slug.strip().lower(), source_page_url, entry_count),
        )
        self.connection.commit()

    def promo_catalogue_entry(
        self, store_id: str, set_code: str, collector_number: str
    ) -> PromoCatalogueEntry | None:
        """Look up a retailer location for a selected Japanese promo print."""
        row = self.connection.execute(
            """
            SELECT * FROM promo_catalogue_entries
            WHERE store_id = ? AND set_code = ? AND collector_number = ?
            """,
            (
                store_id.strip().lower(),
                normalise_set_code(set_code),
                normalise_collector_number(collector_number),
            ),
        ).fetchone()
        if not row:
            return None
        return self._to_promo_entry(row)

    def promo_catalogue_page_url(
        self, store_id: str, set_code: str, collector_number: str
    ) -> str | None:
        """Return the retailer page that contains one exact promo print."""
        entry = self.promo_catalogue_entry(store_id, set_code, collector_number)
        return entry.source_page_url if entry else None

    def unmapped_yuyutei_promo_entries(self) -> list[PromoCatalogueEntry]:
        """Return actual Yuyu-Tei D-PR listings lacking an English mapping."""
        rows = self.connection.execute(
            """
            SELECT p.* FROM promo_catalogue_entries AS p
            JOIN japanese_prints AS j
              ON j.set_code = p.set_code AND j.collector_number = p.collector_number
            LEFT JOIN english_name_mappings AS m ON m.japanese_print_id = j.id
            WHERE p.store_id = 'yuyutei' AND p.set_code = 'DPR'
              AND m.japanese_print_id IS NULL
            ORDER BY CAST(p.collector_number AS INTEGER), p.collector_number
            """
        ).fetchall()
        return [self._to_promo_entry(row) for row in rows]

    def unambiguous_fandom_name_mappings(self, set_codes: Iterable[str]) -> list[EnglishNameMapping]:
        """Map selected prints from one exact Japanese-name Fandom candidate.

        This intentionally uses direct Fandom mappings outside the promo
        families. It avoids the false premise that equal regional promo serials
        identify the same card.
        """
        wanted = self._normalised_set_codes(set_codes)
        if not wanted:
            return []
        placeholders = ", ".join("?" for _ in wanted)
        target_rows = self.connection.execute(
            f"""
            SELECT j.* FROM japanese_prints AS j
            LEFT JOIN english_name_mappings AS m ON m.japanese_print_id = j.id
            WHERE j.set_code IN ({placeholders}) AND m.japanese_print_id IS NULL
            ORDER BY j.set_code, j.collector_number
            """,
            wanted,
        ).fetchall()
        source_rows = self.connection.execute(
            """
            SELECT j.japanese_name, m.english_name, m.aliases_json, m.mapping_source_url
            FROM japanese_prints AS j
            JOIN english_name_mappings AS m ON m.japanese_print_id = j.id
            WHERE j.set_code NOT IN ('DPR', 'CP')
              AND m.mapping_source IN ('fandom', 'fandom-cross-print')
            ORDER BY m.imported_at DESC
            """
        ).fetchall()
        candidates: dict[str, dict[str, sqlite3.Row]] = {}
        for row in source_rows:
            candidates.setdefault(str(row["japanese_name"]), {}).setdefault(str(row["english_name"]), row)
        mappings: list[EnglishNameMapping] = []
        for target in target_rows:
            names = candidates.get(str(target["japanese_name"]), {})
            if len(names) != 1:
                continue
            source = next(iter(names.values()))
            mappings.append(
                EnglishNameMapping(
                    set_code=target["set_code"],
                    collector_number=target["collector_number"],
                    rarity=target["rarity"],
                    english_name=source["english_name"],
                    aliases=tuple(json.loads(source["aliases_json"])),
                    source="fandom-name-match",
                    source_url=source["mapping_source_url"],
                    status="provisional",
                )
            )
        return mappings

    def unlinked_official_english_cards(self, set_codes: Iterable[str]) -> list[CardPrint]:
        """Return official English prints still lacking a Japanese counterpart.

        Callers provide a small, explicit set scope because resolving a
        cross-print relationship requires reading each card's Fandom page.
        """
        wanted = sorted({normalise_set_code(set_code) for set_code in set_codes if set_code.strip()})
        if not wanted:
            return []
        placeholders = ", ".join("?" for _ in wanted)
        rows = self.connection.execute(
            f"""
            SELECT * FROM card_prints
            WHERE source = 'official-english'
              AND (japanese_name IS NULL OR TRIM(japanese_name) = '')
              AND set_code IN ({placeholders})
            ORDER BY set_code, collector_number, rarity
            """,
            wanted,
        ).fetchall()
        return [self._to_card(row) for row in rows]

    def derive_name_mappings_from_known_japanese_names(self) -> MappingImportResult:
        """Map reprints when their Japanese name has one trusted English name.

        This never translates text. A candidate is accepted only when every
        existing mapping for the exact Japanese name agrees on one English
        name; official-English provenance wins when it is available.
        """
        rows = self.connection.execute(
            """
            WITH known_names AS (
                SELECT j.japanese_name
                FROM japanese_prints AS j
                JOIN english_name_mappings AS m ON m.japanese_print_id = j.id
                GROUP BY j.japanese_name
                HAVING COUNT(DISTINCT m.english_name) = 1
            ), ranked_sources AS (
                SELECT j.japanese_name, m.english_name, m.mapping_source,
                       m.mapping_source_url,
                       ROW_NUMBER() OVER (
                           PARTITION BY j.japanese_name
                           ORDER BY CASE WHEN m.mapping_source = 'official-english' THEN 0 ELSE 1 END,
                                    m.imported_at DESC
                       ) AS source_rank
                FROM japanese_prints AS j
                JOIN english_name_mappings AS m ON m.japanese_print_id = j.id
                JOIN known_names AS known ON known.japanese_name = j.japanese_name
            )
            SELECT j.set_code, j.collector_number, j.rarity, source.english_name,
                   source.mapping_source, source.mapping_source_url
            FROM japanese_prints AS j
            LEFT JOIN english_name_mappings AS mapped ON mapped.japanese_print_id = j.id
            JOIN ranked_sources AS source
              ON source.japanese_name = j.japanese_name AND source.source_rank = 1
            WHERE mapped.japanese_print_id IS NULL
              AND j.set_code NOT IN ('DPR', 'CP')
            ORDER BY j.set_code, j.collector_number
            """
        ).fetchall()
        mappings = [
            EnglishNameMapping(
                set_code=row["set_code"],
                collector_number=row["collector_number"],
                rarity=row["rarity"],
                english_name=row["english_name"],
                source="official-english" if row["mapping_source"] == "official-english" else "fandom",
                source_url=row["mapping_source_url"],
                status="derived",
            )
            for row in rows
        ]
        return self.apply_name_mappings(mappings)

    def _upsert(self, card: CardPrint) -> CardPrint:
        if not card.english_name:
            raise ValueError("A card print requires an English name.")
        if card.source == "official-english" and card.set_code in PROMO_PRINT_SET_CODES:
            self._archive_english_card_print(card)
            return card
        aliases_json = json.dumps(card.aliases, ensure_ascii=False)
        normalised_aliases = " ".join(normalise_text(alias) for alias in card.aliases)
        self.connection.execute(
            """
            INSERT INTO card_prints (
                set_code, collector_number, rarity, english_name, japanese_name,
                aliases_json, normalised_name, normalised_aliases, source, source_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(set_code, collector_number, rarity) DO UPDATE SET
                english_name = excluded.english_name,
                japanese_name = excluded.japanese_name,
                aliases_json = excluded.aliases_json,
                normalised_name = excluded.normalised_name,
                normalised_aliases = excluded.normalised_aliases,
                source = excluded.source,
                source_url = excluded.source_url,
                imported_at = CURRENT_TIMESTAMP
            """,
            (
                card.set_code,
                card.collector_number,
                card.rarity,
                card.english_name,
                card.japanese_name,
                aliases_json,
                normalise_text(card.english_name),
                normalised_aliases,
                card.source,
                card.source_url,
            ),
        )
        row = self.connection.execute(
            """
            SELECT * FROM card_prints
            WHERE set_code = ? AND collector_number = ? AND rarity = ?
            """,
            (card.set_code, card.collector_number, card.rarity),
        ).fetchone()
        assert row is not None
        self._refresh_search_row(row)
        return self._to_card(row)

    def get(self, print_id: int, *, japanese_only: bool = False) -> CardPrint | None:
        """Return one print, optionally requiring a Japanese store-search name."""
        conditions = ["id = ?"]
        if japanese_only:
            conditions.append("japanese_name IS NOT NULL AND TRIM(japanese_name) != ''")
        row = self.connection.execute(
            f"SELECT * FROM card_prints WHERE {' AND '.join(conditions)}", (print_id,)
        ).fetchone()
        return self._to_card(row) if row else None

    def get_user_selection(self, selection_id: int) -> CardPrint | None:
        """Resolve a stored card or an ephemeral Japanese-serial selection.

        Negative identifiers refer to a Japanese master record selected by its
        serial. They deliberately avoid writing a placeholder English name to
        the catalogue while still allowing exact-print store comparisons.
        """
        if selection_id >= 0:
            return self.get(selection_id, japanese_only=True)
        japanese = self.connection.execute(
            "SELECT * FROM japanese_prints WHERE id = ?", (-selection_id,)
        ).fetchone()
        return self._serial_selection_from_japanese(japanese) if japanese else None

    def lookup_japanese_serial(self, value: str) -> CardPrint | None:
        """Resolve one formatted Japanese serial without accepting bare numbers.

        This is Japanese-print only. It accepts punctuation and spacing
        variants such as ``D-PR/953``, ``DPR953``, and ``D-PR 953`` but does
        not use English promo references as a user-facing lookup key.
        """
        compact = re.sub(r"[^A-Za-z0-9]", "", value).upper()
        if not compact or not re.search(r"[A-Z]", compact) or not re.search(r"\d", compact):
            return None
        set_codes = [
            str(row["set_code"])
            for row in self.connection.execute(
                "SELECT DISTINCT set_code FROM japanese_prints ORDER BY LENGTH(set_code) DESC, set_code"
            )
        ]
        matches: list[sqlite3.Row] = []
        for set_code in set_codes:
            if not compact.startswith(set_code):
                continue
            supplied_collector = compact.removeprefix(set_code)
            if not supplied_collector:
                continue
            wanted_collector = normalise_collector_number(supplied_collector)
            rows = self.connection.execute(
                "SELECT * FROM japanese_prints WHERE set_code = ?", (set_code,)
            ).fetchall()
            matches.extend(
                row
                for row in rows
                if self._compact_reference_part(row["collector_number"])
                == self._compact_reference_part(wanted_collector)
            )
        if len(matches) != 1:
            return None
        return self._serial_selection_from_japanese(matches[0])

    def unmapped_japanese_count(self, set_code: str | None = None) -> int:
        conditions = ["m.japanese_print_id IS NULL"]
        values: list[object] = []
        if set_code:
            conditions.append("j.set_code = ?")
            values.append(set_code)
        return int(
            self.connection.execute(
                f"""
                SELECT COUNT(*) FROM japanese_prints AS j
                LEFT JOIN english_name_mappings AS m ON m.japanese_print_id = j.id
                WHERE {' AND '.join(conditions)}
                """,
                values,
            ).fetchone()[0]
        )

    def unmapped_japanese_set_codes(self) -> list[str]:
        """Return Japanese set codes that still need an English-name source."""
        return [
            str(row[0])
            for row in self.connection.execute(
                """
                SELECT DISTINCT j.set_code
                FROM japanese_prints AS j
                LEFT JOIN english_name_mappings AS m ON m.japanese_print_id = j.id
                WHERE m.japanese_print_id IS NULL
                ORDER BY j.set_code
                """
            )
        ]

    def has_official_expansion(self, expansion_id: int) -> bool:
        """Whether a completed official import already wrote this expansion.

        Official detail URLs include the stable product expansion identifier.
        It makes a lengthy one-time import resumable after a transient network
        failure without a second bookkeeping database.
        """
        row = self.connection.execute(
            """
            SELECT 1 FROM (
                SELECT source, source_url FROM card_prints
                UNION ALL
                SELECT source, source_url FROM english_print_references
            )
            WHERE source = 'official-english'
              AND (source_url LIKE ? OR source_url LIKE ?)
            LIMIT 1
            """,
            (f"%expansion={expansion_id}&%", f"%expansion={expansion_id}"),
        ).fetchone()
        return row is not None

    def has_japanese_expansion(self, expansion_id: int) -> bool:
        """Whether a Japanese product page has already been imported fully.

        The explicit checkpoint also covers legitimate empty product pages.
        The URL check makes the first full import resume cleanly from Japanese
        cards that were imported before checkpoints were introduced.
        """
        checkpoint = self.connection.execute(
            "SELECT 1 FROM japanese_expansion_imports WHERE expansion_id = ?", (expansion_id,)
        ).fetchone()
        if checkpoint:
            return True
        return self.connection.execute(
            """
            SELECT 1 FROM japanese_prints
            WHERE source_url LIKE ? OR source_url LIKE ?
            LIMIT 1
            """,
            (f"%expansion={expansion_id}&%", f"%expansion={expansion_id}"),
        ).fetchone() is not None

    def mark_japanese_expansion_imported(self, expansion_id: int) -> None:
        """Record a completed Japanese product import after its cards commit."""
        self.connection.execute(
            """
            INSERT INTO japanese_expansion_imports (expansion_id)
            VALUES (?)
            ON CONFLICT(expansion_id) DO UPDATE SET completed_at = CURRENT_TIMESTAMP
            """,
            (expansion_id,),
        )
        self.connection.commit()

    def search(
        self,
        query: str,
        *,
        rarity: str | None = None,
        limit: int = 8,
        japanese_only: bool = False,
    ) -> list[CardPrint]:
        """Search English names and aliases by prefix, substring, and typo score.

        ``japanese_only`` keeps user-facing store searches to prints that have
        an official Japanese name. English-only catalogue records remain
        available as a local mapping source, but Yuyu-Tei cannot list them.
        """
        normalised_query = normalise_text(query)
        if not normalised_query:
            return []
        if rarity:
            rarity = rarity.strip().upper()

        rows = self._fts_rows(normalised_query, rarity, japanese_only)
        if not rows:
            rows = self._substring_rows(normalised_query, rarity, japanese_only)
        if not rows:
            rows = self._all_rows(rarity, japanese_only)

        ranked = sorted(
            ((self._score(normalised_query, row), self._to_card(row)) for row in rows),
            key=lambda item: (-item[0], item[1].english_name.casefold(), item[1].display_code),
        )
        return [card for score, card in ranked if score >= 55][:limit]

    def _fts_rows(self, query: str, rarity: str | None, japanese_only: bool) -> list[sqlite3.Row]:
        tokens = [token for token in query.split() if token]
        if not tokens:
            return []
        match_expression = " AND ".join(f'"{token}"*' for token in tokens)
        conditions = ["card_search MATCH ?"]
        values: list[object] = [match_expression]
        if rarity:
            conditions.append("p.rarity = ?")
            values.append(rarity)
        if japanese_only:
            conditions.append("p.japanese_name IS NOT NULL AND TRIM(p.japanese_name) != ''")
        try:
            return self.connection.execute(
                f"""
                SELECT p.* FROM card_search
                JOIN card_prints AS p ON p.id = CAST(card_search.print_id AS INTEGER)
                WHERE {' AND '.join(conditions)}
                LIMIT 80
                """,
                values,
            ).fetchall()
        except sqlite3.OperationalError:
            return []

    def _substring_rows(self, query: str, rarity: str | None, japanese_only: bool) -> list[sqlite3.Row]:
        conditions = ["(normalised_name LIKE ? OR normalised_aliases LIKE ?)"]
        values: list[object] = [f"%{query}%", f"%{query}%"]
        if rarity:
            conditions.append("rarity = ?")
            values.append(rarity)
        if japanese_only:
            conditions.append("japanese_name IS NOT NULL AND TRIM(japanese_name) != ''")
        return self.connection.execute(
            f"SELECT * FROM card_prints WHERE {' AND '.join(conditions)} LIMIT 120", values
        ).fetchall()

    def _all_rows(self, rarity: str | None, japanese_only: bool) -> list[sqlite3.Row]:
        conditions: list[str] = []
        values: list[object] = []
        if rarity:
            conditions.append("rarity = ?")
            values.append(rarity)
        if japanese_only:
            conditions.append("japanese_name IS NOT NULL AND TRIM(japanese_name) != ''")
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        return self.connection.execute(f"SELECT * FROM card_prints{where}", values).fetchall()

    @staticmethod
    def _score(query: str, row: sqlite3.Row) -> float:
        names = [row["normalised_name"]]
        names.extend(normalise_text(alias) for alias in json.loads(row["aliases_json"]))
        best = 0.0
        query_tokens = set(query.split())
        for name in names:
            if query == name:
                best = max(best, 200.0)
            elif name.startswith(query):
                best = max(best, 160.0)
            elif query in name:
                best = max(best, 140.0)
            elif query_tokens.issubset(set(name.split())):
                best = max(best, 120.0)
            best = max(best, float(fuzz.WRatio(query, name)))
        return best

    def _refresh_search_row(self, row: sqlite3.Row) -> None:
        self.connection.execute("DELETE FROM card_search WHERE print_id = ?", (str(row["id"]),))
        self.connection.execute(
            "INSERT INTO card_search(print_id, english_name, japanese_name, aliases) VALUES (?, ?, ?, ?)",
            (
                str(row["id"]),
                row["english_name"],
                row["japanese_name"] or "",
                " ".join(json.loads(row["aliases_json"])),
            ),
        )

    def _archive_english_card_print(self, card: CardPrint) -> None:
        self.connection.execute(
            """
            INSERT INTO english_print_references (
                set_code, collector_number, rarity, english_name, aliases_json, source, source_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(set_code, collector_number, rarity) DO UPDATE SET
                english_name = excluded.english_name,
                aliases_json = excluded.aliases_json,
                source = excluded.source,
                source_url = excluded.source_url,
                imported_at = CURRENT_TIMESTAMP
            """,
            (
                card.set_code,
                card.collector_number,
                card.rarity,
                card.english_name,
                json.dumps(card.aliases, ensure_ascii=False),
                card.source,
                card.source_url,
            ),
        )

    def _archive_english_print_reference(self, row: sqlite3.Row) -> None:
        self.connection.execute(
            """
            INSERT INTO english_print_references (
                set_code, collector_number, rarity, english_name, aliases_json, source, source_url
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(set_code, collector_number, rarity) DO UPDATE SET
                english_name = excluded.english_name,
                aliases_json = excluded.aliases_json,
                source = excluded.source,
                source_url = excluded.source_url,
                imported_at = CURRENT_TIMESTAMP
            """,
            (
                row["set_code"],
                row["collector_number"],
                row["rarity"],
                row["english_name"],
                row["aliases_json"],
                row["source"],
                row["source_url"],
            ),
        )

    @staticmethod
    def _normalised_set_codes(set_codes: Iterable[str]) -> list[str]:
        return sorted({normalise_set_code(set_code) for set_code in set_codes if set_code.strip()})

    def _serial_selection_from_japanese(self, japanese: sqlite3.Row) -> CardPrint:
        mapped = self.connection.execute(
            """
            SELECT * FROM card_prints
            WHERE set_code = ? AND collector_number = ?
              AND japanese_name IS NOT NULL AND TRIM(japanese_name) != ''
            ORDER BY id
            LIMIT 1
            """,
            (japanese["set_code"], japanese["collector_number"]),
        ).fetchone()
        if mapped:
            return self._to_card(mapped)
        # No English mapping is created. The Japanese title is an explicit
        # serial-only display label, sufficient for exact retailer matching.
        return CardPrint(
            id=-int(japanese["id"]),
            set_code=japanese["set_code"],
            collector_number=japanese["collector_number"],
            rarity=japanese["rarity"],
            english_name=japanese["japanese_name"],
            japanese_name=japanese["japanese_name"],
            source="japanese-serial-only",
            source_url=japanese["source_url"],
        )

    @staticmethod
    def _compact_reference_part(value: str) -> str:
        return re.sub(r"[^A-Za-z0-9]", "", value).upper()

    @staticmethod
    def _to_promo_entry(row: sqlite3.Row) -> PromoCatalogueEntry:
        return PromoCatalogueEntry(
            store_id=row["store_id"],
            page_slug=row["page_slug"],
            set_code=row["set_code"],
            collector_number=row["collector_number"],
            japanese_name=row["japanese_name"],
            listing_url=row["listing_url"],
            source_page_url=row["source_page_url"],
            product_id=row["product_id"],
        )

    def _upsert_japanese(self, card: JapaneseCardPrint) -> sqlite3.Row:
        if not card.japanese_name:
            raise ValueError("A Japanese print requires a Japanese name.")
        self.connection.execute(
            """
            INSERT INTO japanese_prints (
                set_code, collector_number, rarity, japanese_name, source_url
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(set_code, collector_number) DO UPDATE SET
                rarity = CASE
                    WHEN excluded.rarity != '' THEN excluded.rarity
                    ELSE japanese_prints.rarity
                END,
                japanese_name = excluded.japanese_name,
                source_url = excluded.source_url,
                imported_at = CURRENT_TIMESTAMP
            """,
            (card.set_code, card.collector_number, card.rarity, card.japanese_name, card.source_url),
        )
        row = self._japanese_by_reference(card.set_code, card.collector_number)
        assert row is not None
        return row

    def _official_english_by_reference(self, set_code: str, collector_number: str) -> list[sqlite3.Row]:
        return self.connection.execute(
            """
            SELECT * FROM card_prints
            WHERE set_code = ? AND collector_number = ? AND source = 'official-english'
            """,
            (set_code, collector_number),
        ).fetchall()

    def _link_japanese_name_to_official_cards(
        self, official_rows: Iterable[sqlite3.Row], japanese_name: str
    ) -> None:
        for official in official_rows:
            self.connection.execute(
                "UPDATE card_prints SET japanese_name = ?, imported_at = CURRENT_TIMESTAMP WHERE id = ?",
                (japanese_name, official["id"]),
            )
            refreshed = self.connection.execute(
                "SELECT * FROM card_prints WHERE id = ?", (official["id"],)
            ).fetchone()
            assert refreshed is not None
            self._refresh_search_row(refreshed)

    def _japanese_by_reference(self, set_code: str, collector_number: str) -> sqlite3.Row | None:
        return self.connection.execute(
            "SELECT * FROM japanese_prints WHERE set_code = ? AND collector_number = ?",
            (set_code, collector_number),
        ).fetchone()

    @staticmethod
    def _to_card(row: sqlite3.Row) -> CardPrint:
        return CardPrint(
            id=int(row["id"]),
            set_code=row["set_code"],
            collector_number=row["collector_number"],
            rarity=row["rarity"],
            english_name=row["english_name"],
            japanese_name=row["japanese_name"],
            aliases=tuple(json.loads(row["aliases_json"])),
            source=row["source"],
            source_url=row["source_url"],
        )
