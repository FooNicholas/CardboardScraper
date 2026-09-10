import sqlite3
from pathlib import Path

from scraperbot.catalogue.japanese_source import OfficialJapaneseCardSource
from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.connectors.yuyutei import YuyuTeiConnector
from scraperbot.models import CardPrint, EnglishNameMapping, Finish, JapaneseCardPrint


def test_official_japanese_source_splits_a_holo_suffix_from_the_card_name() -> None:
    cards = OfficialJapaneseCardSource.parse_card_entries(
        """<div id="cardlist-container"><ul><li>
        <a href="/cardlist/?cardno=D-PR/999"><div class="number">D-PR/999</div>
        <h5>焔の巫女 シンディ（H仕様）<span>furigana</span></h5></a>
        </li></ul></div>"""
    )

    assert len(cards) == 1
    assert cards[0].japanese_name == "焔の巫女 シンディ"
    assert cards[0].finish is Finish.HOLO
    assert cards[0].finish_raw == "H仕様"


def test_finish_is_saved_on_a_mapped_japanese_print(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    with CatalogueRepository(database) as catalogue:
        catalogue.import_japanese_many(
            [
                JapaneseCardPrint(
                    "D-PR",
                    "999",
                    "PR",
                    "焔の巫女 シンディ",
                    "https://official.test/999",
                    finish=Finish.HOLO,
                    finish_raw="H仕様",
                )
            ]
        )
        catalogue.apply_name_mappings(
            [
                EnglishNameMapping(
                    "D-PR",
                    "999",
                    "PR",
                    "Blaze Maiden, Cindy",
                    "fandom",
                    "https://fandom.test/cindy",
                )
            ]
        )

        card = catalogue.search("cindy", japanese_only=True)[0]

    assert card.finish is Finish.HOLO
    assert card.finish_raw == "H仕様"
    assert card.display_code == "DPR/999 · PR · H仕様"


def test_yuyutei_excludes_a_declared_standard_listing_for_a_holo_print() -> None:
    card = CardPrint(
        "D-PR",
        "999",
        "PR",
        "Blaze Maiden, Cindy",
        japanese_name="焔の巫女 シンディ",
        finish=Finish.HOLO,
        finish_raw="H仕様",
    )
    html = """
    <div class="col-md"><span>D-PR/999</span><h4>焔の巫女 シンディ（ノーマル仕様）</h4>
    <strong>100 円</strong><label class="cart_sell_zaiko">在庫 : ◯</label></div>
    <div class="col-md"><span>D-PR/999</span><h4>焔の巫女 シンディ（H仕様）</h4>
    <strong>500 円</strong><label class="cart_sell_zaiko">在庫 : ◯</label></div>
    """

    offers = YuyuTeiConnector.parse_html(card, html)

    assert len(offers) == 1
    assert offers[0].price_yen == 500
    assert offers[0].finish is Finish.HOLO
    assert offers[0].finish_raw == "H仕様"


def test_existing_catalogue_schema_migrates_finish_columns(tmp_path: Path) -> None:
    database = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(database) as connection:
        connection.executescript(
            """
            CREATE TABLE card_prints (
                id INTEGER PRIMARY KEY, set_code TEXT NOT NULL, collector_number TEXT NOT NULL,
                rarity TEXT NOT NULL, english_name TEXT NOT NULL, japanese_name TEXT,
                aliases_json TEXT NOT NULL DEFAULT '[]', normalised_name TEXT NOT NULL,
                normalised_aliases TEXT NOT NULL DEFAULT '', source TEXT NOT NULL, source_url TEXT,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(set_code, collector_number, rarity)
            );
            CREATE TABLE japanese_prints (
                id INTEGER PRIMARY KEY, set_code TEXT NOT NULL, collector_number TEXT NOT NULL,
                rarity TEXT NOT NULL DEFAULT '', japanese_name TEXT NOT NULL, source_url TEXT NOT NULL,
                imported_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(set_code, collector_number)
            );
            """
        )
    with CatalogueRepository(database) as catalogue:
        card_columns = {row["name"] for row in catalogue.connection.execute("PRAGMA table_info(card_prints)")}
        japanese_columns = {row["name"] for row in catalogue.connection.execute("PRAGMA table_info(japanese_prints)")}

    assert {"finish", "finish_raw"}.issubset(card_columns)
    assert {"finish", "finish_raw"}.issubset(japanese_columns)
