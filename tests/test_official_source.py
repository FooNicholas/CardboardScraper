from scraperbot.catalogue.official_source import OfficialEnglishCardSource


def test_parse_expansions_and_official_card_entries() -> None:
    expansions = OfficialEnglishCardSource.parse_expansions(
        '''<div class="product-item"><a href="/cardlist/cardsearch/?expansion=42">
        <div class="title">[VGE-D-BT06] Booster Pack 06</div></a></div>'''
    )
    assert expansions[0].id == 42
    assert expansions[0].set_code == "D-BT06"

    cards = OfficialEnglishCardSource.parse_card_entries(
        '''<div id="cardlist-container"><ul>
        <li><a href="/cardlist/?cardno=D-BT06/010EN"><div class="number">D-BT06/010EN</div>
        <h5>Youthberk &quot;Skyfall Arms&quot;</h5></a></li>
        <li><a href="/cardlist/?cardno=D-BT06/FFR10EN"><div class="number">D-BT06/FFR10EN</div>
        <h5>Youthberk &quot;Skyfall Arms&quot;</h5></a></li>
        </ul></div>'''
    )
    assert [(card.collector_number, card.rarity) for card in cards] == [("010", ""), ("FFR10", "FFR")]
    assert cards[1].english_name == 'Youthberk "Skyfall Arms"'
    assert cards[1].source_url == "https://en.cf-vanguard.com/cardlist/?cardno=D-BT06/FFR10EN"


def test_parse_page_count_defaults_to_one() -> None:
    assert OfficialEnglishCardSource.parse_page_count("var max_page = 3;") == 3
    assert OfficialEnglishCardSource.parse_page_count("no pagination") == 1


def test_parse_card_entries_accepts_lazy_loaded_fragments() -> None:
    cards = OfficialEnglishCardSource.parse_card_entries(
        '''<li class="ex-item"><a href="/cardlist/?cardno=DZ-BT15/025EN">
        <div class="number">DZ-BT15/025EN</div><h5>Example Card</h5></a></li>'''
    )
    assert [(card.set_code, card.collector_number) for card in cards] == [("DZBT15", "025")]
