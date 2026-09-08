from scraperbot.connectors.bigweb import BigWebConnector
from scraperbot.connectors.yuyutei import YuyuTeiConnector
from scraperbot.models import Availability, CardPrint


CARD = CardPrint(
    set_code="DZBT16",
    collector_number="FFR02",
    rarity="FFR",
    english_name="Exzabite Dragon",
    japanese_name="エグザサベイト・ドラゴン",
    source="test",
)


def test_bigweb_matches_public_api_print_reference() -> None:
    offers = BigWebConnector.parse_items(
        CARD,
        [
            {
                "id": 3576107,
                "name": "エグザサベイト・ドラゴン",
                "comment": "DZ-BT16/FFR02 秋葉原店で展示中",
                "stock_count": 1,
                "is_sold_out": False,
                "price": 1200,
                "condition": {"name": "Near Mint"},
            },
            {
                "id": 3576108,
                "name": "別のカード",
                "comment": "DZ-BT16/FFR03",
                "stock_count": 1,
                "is_sold_out": False,
                "price": 400,
            },
        ],
    )
    assert len(offers) == 1
    assert offers[0].price_yen == 1200
    assert offers[0].availability == Availability.IN_STOCK
    assert offers[0].listing_url.endswith("3576107")


def test_yuyutei_matches_print_reference_without_translating() -> None:
    html = """
    <div class="col-md">
      <a href="/sell/vg/card/dzbt16/999"><img></a>
      <span>DZ-BT16/FFR02</span>
      <a href="/sell/vg/card/dzbt16/999"><h4>エグザサベイト・ドラゴン</h4></a>
      <strong>1,280 円</strong><span>在庫 : 4 点</span>
    </div>
    <div class="col-md"><span>DZ-BT16/FFR03</span><h4>別のカード</h4><strong>500 円</strong></div>
    """
    offers = YuyuTeiConnector.parse_html(CARD, html)
    assert len(offers) == 1
    assert offers[0].raw_name == "エグザサベイト・ドラゴン"
    assert offers[0].price_yen == 1280
    assert offers[0].listing_url == "https://yuyu-tei.jp/sell/vg/card/dzbt16/999"
