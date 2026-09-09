"""SQLite-backed card catalogue with fast name and alias lookups."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Iterable

from rapidfuzz import fuzz

from scraperbot.models import CardPrint, EnglishNameMapping, JapaneseCardPrint, normalise_text


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
                official_rows = self._official_english_by_reference(
                    mapping.set_code, mapping.collector_number
                )
                existing_mapping = self.connection.execute(
                    "SELECT mapping_source FROM english_name_mappings WHERE japanese_print_id = ?",
                    (japanese["id"],),
                ).fetchone()
                if existing_mapping and existing_mapping["mapping_source"] == "official-english" and (
                    mapping.source != "official-english"
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
            SELECT 1 FROM card_prints
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
