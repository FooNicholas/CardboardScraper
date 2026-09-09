from scraperbot.catalogue.fandom_source import FandomMappingSource


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
