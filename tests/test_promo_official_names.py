from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.catalogue.promo_mapping_repair import repair_promo_mappings
from scraperbot.models import JapaneseCardPrint, EnglishNameMapping


def test_playable_promo_uses_fandom_main_set_name_and_keeps_holo(tmp_path):
    database = tmp_path / 'catalogue.sqlite3'
    with CatalogueRepository(database) as c:
        c.import_japanese_many([
            JapaneseCardPrint('DBT01','001','RRR','同じカード','https://jp/main'),
            JapaneseCardPrint('DPR','001','PR','同じカード','https://jp/promo',finish_raw='H仕様'),
            JapaneseCardPrint('DPR','002','PR','エネルギー','https://jp/energy'),
            JapaneseCardPrint('DBT01','002','C','エネルギー','https://jp/main-energy'),
        ])
        c.apply_name_mappings([
            EnglishNameMapping('DBT01','001','RRR','Playable Card','fandom','https://fandom/main'),
            EnglishNameMapping('DBT01','002','C','Energy','fandom','https://fandom/energy'),
        ])
    repair_promo_mappings(database)
    with CatalogueRepository(database) as c:
        card = c.lookup_japanese_serial('DPR001')
        assert card.english_name == 'Playable Card'
        assert card.finish_raw == 'H仕様'
        assert card.source == 'fandom-name-match-provisional'
        assert any(p.set_code == 'DPR' for p in c.search('Playable Card',japanese_only=True))
        assert c.lookup_japanese_serial('DPR002').source == 'japanese-serial-only'


def test_conflicting_fandom_names_stay_unmapped(tmp_path):
    with CatalogueRepository(tmp_path / 'catalogue.sqlite3') as c:
        c.import_japanese_many([
            JapaneseCardPrint('DBT01','001','RRR','同じカード','https://jp/1'),
            JapaneseCardPrint('DSS11','001','R','同じカード','https://jp/2'),
            JapaneseCardPrint('DPR','001','PR','同じカード','https://jp/pr'),
        ])
        c.apply_name_mappings([
            EnglishNameMapping('DBT01','001','RRR','One Name','fandom','https://fandom/1'),
            EnglishNameMapping('DSS11','001','R','Conflicting Name','fandom','https://fandom/2'),
        ])
        assert c.unambiguous_fandom_name_mappings(('DPR',)) == []
