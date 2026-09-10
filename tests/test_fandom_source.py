from scraperbot.catalogue.fandom_source import FandomMappingSource
from scraperbot.models import CardPrint


def test_parse_fandom_card_table_to_provisional_mappings() -> None:
    mappings = FandomMappingSource.parse_mappings(
        '''<table class="wikitable"><tr><th>Card No.</th><th>Name</th><th>Rarity</th></tr>
        <tr><td>DZ-BT16/002</td><td><a>Exacerbate Dragon</a></td><td>RRR</td></tr>
        <tr><td>DZ-BT16/FFR02</td><td><a>Exacerbate Dragon</a></td><td>FFR</td></tr>
        <tr><td>DZ-BT16/???</td><td>Unconfirmed</td><td></td></tr></table>''',
        "DZ-BT16",
        source_url="https://cardfight.fandom.com/wiki/DZ_Booster_Set_16",
    )
    assert [(mapping.collector_number, mapping.rarity, mapping.english_name) for mapping in mappings] == [
        ("002", "RRR", "Exacerbate Dragon"),
        ("FFR02", "FFR", "Exacerbate Dragon"),
    ]
    assert all(mapping.status == "provisional" for mapping in mappings)


def test_fandom_search_term_restores_set_code_hyphens() -> None:
    assert FandomMappingSource._search_term("DZBT16") == "DZ-BT16"
    assert FandomMappingSource._search_term("DTTD04") == "D-TTD04"
    assert FandomMappingSource._search_term("DPR") == "D-PR"
    assert FandomMappingSource._search_term("PR") == "PR"


def test_fandom_has_curated_promo_list_pages() -> None:
    assert FandomMappingSource.known_list_pages == {
        "CP": "List of D Promo Cards",
        "DPR": "List of D Promo Cards",
    }


def test_parse_fandom_promo_list_to_mappings() -> None:
    mappings = FandomMappingSource.parse_list_mappings(
        '''<ul>
        <li>D-PR/006 - <a title="Blazing Spear Dragon">Blazing Spear Dragon</a></li>
        <li>D-PR/007 - <a title="Direful Doll, Violetta">Direful Doll, Violetta</a></li>
        <li>CP/001 - <a title="Other">Other</a></li>
        </ul>''',
        "D-PR",
        source_url="https://cardfight.fandom.com/wiki/List_of_D_Promo_Cards",
    )
    assert [(mapping.collector_number, mapping.english_name) for mapping in mappings] == [
        ("006", "Blazing Spear Dragon"),
        ("007", "Direful Doll, Violetta"),
    ]


def test_card_page_cross_print_mapping_connects_different_japanese_and_english_codes() -> None:
    card = CardPrint(
        "DZ-BT12",
        "Re07",
        "RE",
        "The Nebula Knight's Path to Reach for the Stars",
        source="official-english",
    )
    html = """
    <table class="sets"><tr><th>Card Set(s)</th></tr><tr><td><ul>
      <li><a>D Promo Cards</a> - D-PR/1247 2025</li>
      <li><a>Chasm of Lost Souls</a> - DZ-BT12/Re07EN (Re) 2026</li>
    </ul></td></tr></table>
    """
    assert FandomMappingSource.parse_card_set_references(html) == [
        ("DPR", "1247"),
        ("DZBT12", "RE07"),
    ]
    mappings = FandomMappingSource.cross_print_mappings_from_page(card, html)
    assert [(mapping.set_code, mapping.collector_number, mapping.english_name) for mapping in mappings] == [
        ("DPR", "1247", "The Nebula Knight's Path to Reach for the Stars"),
    ]
