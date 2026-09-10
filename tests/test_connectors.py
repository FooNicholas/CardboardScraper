from scraperbot.connectors.bigweb import BigWebConnector
from scraperbot.connectors.cardrush import CardRushConnector
from scraperbot.connectors.vanhappy import VanHappyConnector
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

DRAEGFORCE = CardPrint(
    set_code="DZBT14",
    collector_number="001",
    rarity="RRR",
    english_name='Youthberk "Drægforce Arms: Fantôme"',
    japanese_name="ユースベルク“龍吼燎騎・幻影”",
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
    assert offers[0].stock_count == 1
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
    assert offers[0].stock_count == 4
    assert offers[0].listing_url == "https://yuyu-tei.jp/sell/vg/card/dzbt16/999"


def test_yuyutei_marks_an_explicit_zero_stock_listing_sold_out() -> None:
    html = """
    <div class="col-md"><span>DZ-BT16/FFR02</span><h4>エグザサベイト・ドラゴン</h4>
    <strong>1,280 円</strong><span>在庫：0 点</span></div>
    """
    offer = YuyuTeiConnector.parse_html(CARD, html)[0]
    assert offer.availability == Availability.SOLD_OUT
    assert offer.price_display == "¥1,280"
    assert offer.price_yen == 1280
    assert offer.stock_count == 0


def test_yuyutei_marks_a_circle_stock_indicator_in_stock() -> None:
    html = """
    <div class="col-md"><span>DZ-BT16/FFR02</span><h4>エグザサベイト・ドラゴン</h4>
    <strong>420 円</strong><label class="cart_sell_zaiko">在庫 : ◯</label></div>
    """
    offer = YuyuTeiConnector.parse_html(CARD, html)[0]
    assert offer.availability == Availability.IN_STOCK
    assert offer.price_yen == 420
    assert offer.price_display == "¥420"
    assert offer.stock_count is None


def test_yuyutei_does_not_label_an_unknown_stock_state_sold_out() -> None:
    html = """
    <div class="col-md"><span>DZ-BT16/FFR02</span><h4>エグザサベイト・ドラゴン</h4>
    <strong>420 円</strong></div>
    """
    offer = YuyuTeiConnector.parse_html(CARD, html)[0]
    assert offer.availability == Availability.UNKNOWN
    assert offer.price_yen == 420
    assert offer.price_display == "¥420"


def test_yuyutei_marks_a_cross_stock_indicator_out_of_stock_and_keeps_its_price() -> None:
    html = """
    <div class="col-md"><div class="card-product sold-out"><span>DZ-BT16/FFR02</span>
    <h4>エグザサベイト・ドラゴン</h4><strong>980 円</strong>
    <label class="cart_sell_zaiko">在庫 : ×</label></div></div>
    """
    offer = YuyuTeiConnector.parse_html(CARD, html)[0]
    assert offer.availability == Availability.SOLD_OUT
    assert offer.price_yen == 980
    assert offer.price_display == "¥980"
    assert offer.stock_count is None


def test_bigweb_keeps_the_displayed_price_for_an_out_of_stock_print() -> None:
    offers = BigWebConnector.parse_items(
        CARD,
        [
            {
                "id": 3576107,
                "name": "エグザサベイト・ドラゴン",
                "comment": "DZ-BT16/FFR02",
                "stock_count": 0,
                "is_sold_out": True,
                "price": 980,
            }
        ],
    )
    assert offers[0].availability == Availability.SOLD_OUT
    assert offers[0].price_yen == 980
    assert offers[0].price_display == "¥980"
    assert offers[0].stock_count == 0


def test_cardrush_matches_exact_prints_and_retains_condition_stock_and_oos_price() -> None:
    html = """
    <ul>
      <li><a href="/product/53085"><p>ユースベルク龍吼燎騎・幻影【RRR】{DZ-BT14/001}</p>
      <p>380円（税込）</p><p>在庫数 48枚</p></a></li>
      <li><a href="/product/53488"><p>〔状態A-〕ユースベルク龍吼燎騎・幻影【RRR】{DZ-BT14/001}</p>
      <p>350円（税込）</p><p>在庫数 6枚</p></a></li>
      <li><a href="/product/54724"><p>〔状態B〕ユースベルク龍吼燎騎・幻影【RRR】{DZ-BT14/001}</p>
      <p>280円（税込）</p><p>×</p></a></li>
      <li><a href="/product/53262"><p>ユースベルク龍吼燎騎・幻影【FFR】{DZ-BT14/FFR01}</p>
      <p>3,980円（税込）</p><p>在庫数 2枚</p></a></li>
    </ul>
    """
    offers = CardRushConnector.parse_html(DRAEGFORCE, html)
    assert [(offer.price_yen, offer.availability, offer.stock_count, offer.condition) for offer in offers] == [
        (380, Availability.IN_STOCK, 48, None),
        (350, Availability.IN_STOCK, 6, "A-"),
        (280, Availability.SOLD_OUT, None, "B"),
    ]
    assert offers[0].listing_url == "https://www.cardrush-vanguard.jp/product/53085"


def test_vanhappy_matches_exact_prints_and_reports_stock_and_sold_out_prices() -> None:
    html = """
    <div class="product-card">
      <p class="product-card__name"><a href="/view/item/28712">ユースベルク“龍吼燎騎・幻影”「RRR」[DZ-BT14/001]《ドラゴンエンパイア》</a></p>
      <div class="product-card__price"><span>￥320</span></div><div class="product-card__stock">在庫 23 個</div>
      <button>カートに入れる</button>
    </div>
    <div class="product-card">
      <div class="product-card__badges"><span class="product-card__badge--soldout">SOLD OUT</span></div>
      <p class="product-card__name"><a href="/view/item/28713">ユースベルク“龍吼燎騎・幻影”「RRR」[DZ-BT14/001]《ドラゴンエンパイア》</a></p>
      <div class="product-card__price"><span>￥280</span></div><div class="product-card__stock">在庫 0 個</div>
      <button disabled>売り切れ</button>
    </div>
    <div class="product-card">
      <div class="product-card__badges"><span class="product-card__badge--soldout">SOLD OUT</span></div>
      <p class="product-card__name"><a href="/view/item/28889">ユースベルク“龍吼燎騎・幻影”「FFR」[DZ-BT14/FFR01]《ドラゴンエンパイア》</a></p>
      <div class="product-card__price"><span>￥3,980</span></div><div class="product-card__stock">在庫 0 個</div>
      <button disabled>売り切れ</button>
    </div>
    <div class="product-card">
      <div class="product-card__badges"><span class="product-card__badge--soldout">SOLD OUT</span></div>
      <p class="product-card__name"><a href="/view/item/28995">ユースベルク“龍吼燎騎・幻影”「SR」[DZ-BT14/SR01]《ドラゴンエンパイア》</a></p>
      <div class="product-card__price"><span>￥920</span></div><div class="product-card__stock">在庫 0 個</div>
      <button disabled>売り切れ</button>
    </div>
    """
    offers = VanHappyConnector.parse_html(DRAEGFORCE, html)
    assert [(offer.price_yen, offer.availability, offer.stock_count) for offer in offers] == [
        (320, Availability.IN_STOCK, 23),
        (280, Availability.SOLD_OUT, 0),
    ]
    assert offers[0].listing_url == "https://www.van-happy.com/view/item/28712"
