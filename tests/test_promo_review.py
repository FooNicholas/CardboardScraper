import json
from pathlib import Path

from scraperbot.catalogue.promo_review import apply_yuyutei_promo_review, export_yuyutei_promo_review
from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import JapaneseCardPrint, PromoCatalogueEntry


def _seed_unmapped_yuyutei_promos(database: Path) -> None:
    with CatalogueRepository(database) as catalogue:
        catalogue.import_japanese_many(
            [
                JapaneseCardPrint("D-PR", "953", "PR", "大地を駆ける守主 ルアン", "https://jp/dpr953"),
                JapaneseCardPrint("D-PR", "1101", "PR", "エネルギー", "https://jp/dpr1101"),
                JapaneseCardPrint("D-PR", "1200", "PR", "Not Listed", "https://jp/dpr1200"),
            ]
        )
        catalogue.upsert_promo_catalogue_entries(
            [
                PromoCatalogueEntry(
                    "yuyutei", "dpromo-1000", "D-PR", "953", "大地を駆ける守主 ルアン",
                    "https://yuyu.test/953", "https://yuyu.test/dpromo-1000", "10042"
                ),
                PromoCatalogueEntry(
                    "yuyutei", "dpromo-1200", "D-PR", "1101", "エネルギー",
                    "https://yuyu.test/1101", "https://yuyu.test/dpromo-1200", "10019"
                ),
            ]
        )


def test_promo_review_export_is_scoped_to_actual_yuyutei_entries(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    output = tmp_path / "review.json"
    _seed_unmapped_yuyutei_promos(database)

    result = export_yuyutei_promo_review(database, output)
    payload = json.loads(output.read_text(encoding="utf-8"))

    assert result.entries == 2
    assert result.held_utility_entries == 1
    assert [(entry["collector_number"], entry["status"]) for entry in payload["entries"]] == [
        ("953", "needs_review"),
        ("1101", "held"),
    ]


def test_promo_review_apply_records_only_explicit_approved_yuyutei_entries(tmp_path: Path) -> None:
    database = tmp_path / "catalogue.sqlite3"
    review = tmp_path / "review.json"
    _seed_unmapped_yuyutei_promos(database)
    review.write_text(
        json.dumps(
            {
                "entries": [
                    {
                        "set_code": "D-PR",
                        "collector_number": "953",
                        "status": "approved",
                        "english_name": "Guard Running Through The Earth, Leuhan",
                        "aliases": ["Leuhan"],
                        "source_url": "https://fandom.test/leuhan",
                    },
                    {
                        "set_code": "D-PR",
                        "collector_number": "1200",
                        "status": "approved",
                        "english_name": "Out of Scope",
                        "aliases": [],
                    },
                    {
                        "set_code": "D-PR",
                        "collector_number": "1101",
                        "status": "approved",
                        "english_name": "Energy",
                        "aliases": [],
                    },
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = apply_yuyutei_promo_review(database, review)

    assert result.approved_records == 1
    assert result.ignored_records == 2
    with CatalogueRepository(database) as catalogue:
        card = catalogue.search("leuhan", japanese_only=True)[0]
        assert card.collector_number == "953"
        assert card.source == "promo-review-reviewed"
