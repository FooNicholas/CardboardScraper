"""SQLite-backed card catalogue with fast name and alias lookups."""

from __future__ import annotations

import json
from pathlib import Path
import sqlite3
from typing import Iterable, Sequence

from rapidfuzz import fuzz

from scraperbot.models import CardPrint, normalise_text


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

CREATE VIRTUAL TABLE IF NOT EXISTS card_search USING fts5(
    print_id UNINDEXED,
    english_name,
    japanese_name,
    aliases,
    tokenize = 'unicode61 remove_diacritics 2'
);
"""


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

    def upsert(self, card: CardPrint) -> CardPrint:
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
        self.connection.commit()
        return self._to_card(row)

    def import_many(self, cards: Iterable[CardPrint]) -> int:
        imported = 0
        for card in cards:
            self.upsert(card)
            imported += 1
        return imported

    def get(self, print_id: int) -> CardPrint | None:
        row = self.connection.execute("SELECT * FROM card_prints WHERE id = ?", (print_id,)).fetchone()
        return self._to_card(row) if row else None

    def search(self, query: str, *, rarity: str | None = None, limit: int = 8) -> list[CardPrint]:
        """Search English names and aliases by prefix, substring, and typo score."""
        normalised_query = normalise_text(query)
        if not normalised_query:
            return []
        if rarity:
            rarity = rarity.strip().upper()

        rows = self._fts_rows(normalised_query, rarity)
        if not rows:
            rows = self._substring_rows(normalised_query, rarity)
        if not rows:
            rows = self._all_rows(rarity)

        ranked = sorted(
            ((self._score(normalised_query, row), self._to_card(row)) for row in rows),
            key=lambda item: (-item[0], item[1].english_name.casefold(), item[1].display_code),
        )
        return [card for score, card in ranked if score >= 55][:limit]

    def _fts_rows(self, query: str, rarity: str | None) -> list[sqlite3.Row]:
        tokens = [token for token in query.split() if token]
        if not tokens:
            return []
        match_expression = " AND ".join(f'"{token}"*' for token in tokens)
        conditions = ["card_search MATCH ?"]
        values: list[object] = [match_expression]
        if rarity:
            conditions.append("p.rarity = ?")
            values.append(rarity)
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

    def _substring_rows(self, query: str, rarity: str | None) -> list[sqlite3.Row]:
        conditions = ["(normalised_name LIKE ? OR normalised_aliases LIKE ?)"]
        values: list[object] = [f"%{query}%", f"%{query}%"]
        if rarity:
            conditions.append("rarity = ?")
            values.append(rarity)
        return self.connection.execute(
            f"SELECT * FROM card_prints WHERE {' AND '.join(conditions)} LIMIT 120", values
        ).fetchall()

    def _all_rows(self, rarity: str | None) -> list[sqlite3.Row]:
        if rarity:
            return self.connection.execute("SELECT * FROM card_prints WHERE rarity = ?", (rarity,)).fetchall()
        return self.connection.execute("SELECT * FROM card_prints").fetchall()

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
