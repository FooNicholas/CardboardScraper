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
