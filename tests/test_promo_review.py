import json
from pathlib import Path
import pytest

from scraperbot.catalogue.promo_review import apply_yuyutei_promo_review, export_yuyutei_promo_review
from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import EnglishNameMapping, JapaneseCardPrint, PromoCatalogueEntry


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
                        "japanese_name": "大地を駆ける守主 ルアン",
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


def _export_approved(database, output):
    export_yuyutei_promo_review(database, output)
    payload = json.loads(output.read_text())
    entry = next(e for e in payload['entries'] if e['collector_number'] == '953')
    entry.update(status='approved', english_name='Leuhan')
    return payload, entry


def test_export_uses_canonical_identity_and_shows_conflicting_evidence(tmp_path):
    database, output = tmp_path / 'db.sqlite3', tmp_path / 'review.json'
    _seed_unmapped_yuyutei_promos(database)
    with CatalogueRepository(database) as c:
        c.connection.execute("UPDATE promo_catalogue_entries SET japanese_name='Wrong retailer name' WHERE collector_number='953'")
        c.connection.commit()
        c.import_japanese_many([
            JapaneseCardPrint('DBT01', '001', 'RRR', '大地を駆ける守主 ルアン', 'https://jp/main'),
            JapaneseCardPrint('DSS11', '001', 'R', '大地を駆ける守主 ルアン', 'https://jp/special'),
        ])
        c.apply_name_mappings([
            EnglishNameMapping('DBT01', '001', 'RRR', 'Leuhan', 'official-english', 'https://en/main'),
            EnglishNameMapping('DSS11', '001', 'R', 'Another spelling', 'fandom', 'https://fandom/card'),
        ])
    export_yuyutei_promo_review(database, output)
    payload = json.loads(output.read_text())
    entry = payload['entries'][0]
    assert payload['schema_version'] == 2
    assert entry['japanese_name'] == '大地を駆ける守主 ルアン'
    assert entry['retailer_japanese_name'] == 'Wrong retailer name'
    assert entry['reason'] == 'conflicting_candidates'
    assert {candidate['english_name'] for candidate in entry['candidates']} == {'Leuhan', 'Another spelling'}
    assert entry['english_name'] is None
    assert entry['status'] == 'needs_review'
    assert payload['entries'][1]['candidates'] == []


def test_export_refuses_to_overwrite_existing_reviews(tmp_path):
    database, output = tmp_path / 'db.sqlite3', tmp_path / 'review.json'
    _seed_unmapped_yuyutei_promos(database)
    output.write_text('precious existing review')
    with pytest.raises(FileExistsError):
        export_yuyutei_promo_review(database, output)
    assert output.read_text() == 'precious existing review'


@pytest.mark.parametrize('field,value,reason', [
    ('english_name', None, 'invalid_english_name'),
    ('english_name', 123, 'invalid_english_name'),
    ('english_name', '  ', 'invalid_english_name'),
    ('japanese_name', None, 'stale_or_missing_japanese_identity'),
    ('japanese_name', 'Wrong old name', 'stale_or_missing_japanese_identity'),
    ('japanese_source_url', 'https://old-source', 'stale_japanese_source'),
    ('aliases', [None], 'invalid_aliases'),
    ('source_url', 123, 'invalid_source_url'),
])
def test_rejects_invalid_or_stale_approved_records(tmp_path, field, value, reason):
    database, output = tmp_path / 'db.sqlite3', tmp_path / 'review.json'
    _seed_unmapped_yuyutei_promos(database)
    payload, entry = _export_approved(database, output)
    entry[field] = value
    output.write_text(json.dumps(payload))
    result = apply_yuyutei_promo_review(database, output)
    assert result.approved_records == 0
    assert result.issues[0].reason == reason
    with CatalogueRepository(database) as c:
        assert c.lookup_japanese_serial('DPR953').source == 'japanese-serial-only'


def test_rejects_review_when_database_identity_changed_after_export(tmp_path):
    database, output = tmp_path / 'db.sqlite3', tmp_path / 'review.json'
    _seed_unmapped_yuyutei_promos(database)
    payload, _ = _export_approved(database, output)
    output.write_text(json.dumps(payload))
    with CatalogueRepository(database) as c:
        c.import_japanese_many([JapaneseCardPrint('DPR', '953', 'PR', 'New official identity', 'https://jp/new')])
    result = apply_yuyutei_promo_review(database, output)
    assert result.issues[0].reason == 'stale_or_missing_japanese_identity'
    assert result.mapping_result.mapped == 0


def test_rejects_duplicate_approvals_without_last_record_winning(tmp_path):
    database, output = tmp_path / 'db.sqlite3', tmp_path / 'review.json'
    _seed_unmapped_yuyutei_promos(database)
    payload, entry = _export_approved(database, output)
    payload['entries'].append({**entry, 'set_code': 'D-PR', 'english_name': 'Conflict'})
    output.write_text(json.dumps(payload))
    result = apply_yuyutei_promo_review(database, output)
    assert result.approved_records == 0
    assert [issue.reason for issue in result.issues] == ['duplicate_approval', 'duplicate_approval']


def test_approved_review_does_not_overwrite_later_mapping_or_map_unapproved_serials(tmp_path):
    database, output = tmp_path / 'db.sqlite3', tmp_path / 'review.json'
    _seed_unmapped_yuyutei_promos(database)
    with CatalogueRepository(database) as c:
        c.import_japanese_many([JapaneseCardPrint('DPR', '954', 'PR', '大地を駆ける守主 ルアン', 'https://jp/954')])
    payload, entry = _export_approved(database, output)
    output.write_text(json.dumps(payload))
    result = apply_yuyutei_promo_review(database, output)
    assert result.mapping_result.mapped == 1
    assert result.mapping_result.derived == 0
    with CatalogueRepository(database) as c:
        assert c.lookup_japanese_serial('DPR954').source == 'japanese-serial-only'
    entry['english_name'] = 'Wrong replacement'
    output.write_text(json.dumps(payload))
    result = apply_yuyutei_promo_review(database, output)
    assert result.issues[0].reason == 'already_mapped'
    with CatalogueRepository(database) as c:
        assert c.lookup_japanese_serial('DPR953').english_name == 'Leuhan'


def test_utility_status_uses_canonical_name_not_retailer_name(tmp_path):
    database, output = tmp_path / 'db.sqlite3', tmp_path / 'review.json'
    _seed_unmapped_yuyutei_promos(database)
    with CatalogueRepository(database) as c:
        c.connection.execute("UPDATE promo_catalogue_entries SET japanese_name='Playable-looking title' WHERE collector_number='1101'")
        c.connection.commit()
    export_yuyutei_promo_review(database, output)
    payload = json.loads(output.read_text())
    entry = next(e for e in payload['entries'] if e['collector_number'] == '1101')
    assert entry['status'] == 'held'
    entry.update(status='approved', english_name='Do not map')
    output.write_text(json.dumps(payload))
    assert apply_yuyutei_promo_review(database, output).issues[0].reason == 'serial_only_utility'


def test_official_identity_conflict_blocks_approval(tmp_path):
    database, output = tmp_path / 'db.sqlite3', tmp_path / 'review.json'
    _seed_unmapped_yuyutei_promos(database)
    payload, _ = _export_approved(database, output)
    output.write_text(json.dumps(payload))
    with CatalogueRepository(database) as c:
        c.connection.execute(
            "INSERT INTO official_promo_identities (collector_number,japanese_name,source_url,distribution) VALUES (?,?,?,?)",
            ('953', 'Different official identity', 'https://jp/official', 'Promo'),
        )
        c.connection.commit()
    result = apply_yuyutei_promo_review(database, output)
    assert result.issues[0].reason == 'official_identity_conflict'
    assert result.mapping_result.mapped == 0


def test_unknown_schema_is_rejected_before_applying_any_records(tmp_path):
    database, output = tmp_path / 'db.sqlite3', tmp_path / 'review.json'
    _seed_unmapped_yuyutei_promos(database)
    payload, _ = _export_approved(database, output)
    payload['schema_version'] = 999
    output.write_text(json.dumps(payload))
    with pytest.raises(ValueError, match='schema version'):
        apply_yuyutei_promo_review(database, output)
