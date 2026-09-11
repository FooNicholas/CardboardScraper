import asyncio
import json

import httpx

from scraperbot.connectors.bigweb import BigWebConnector
from scraperbot.connectors.cardrush import CardRushConnector
from scraperbot.connectors.amenitydream import AmenityDreamConnector
from scraperbot.connectors.avalon import AvalonConnector
from scraperbot.connectors.cardmax import CardMaxConnector
from scraperbot.connectors.clabo import CLaboConnector
from scraperbot.connectors.fullahead import FullAheadConnector
from scraperbot.connectors.manasource import ManaSourceConnector
from scraperbot.connectors.manzokuya import ManzokuyaConnector
from scraperbot.connectors.olta import OltaConnector
from scraperbot.connectors.torecolo import TorecoloConnector
from scraperbot.connectors.realize import RealizeConnector
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


def test_yuyutei_uses_the_saved_promo_page_for_dpr_prints() -> None:
    card = CardPrint(
        set_code="D-PR",
        collector_number="953",
        rarity="PR",
        english_name="Leuhan",
        japanese_name="大地を駆ける守主 ルアン",
        source="test",
    )
    requested_urls: list[str] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        requested_urls.append(str(request.url))
        return httpx.Response(
            200,
            text="""
            <div class=\"col-md\"><span>D-PR/953</span><h4>大地を駆ける守主 ルアン</h4>
            <strong>420 円</strong><label class=\"cart_sell_zaiko\">在庫 : ◯</label></div>
            """,
        )

    async def run() -> list[object]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            return await YuyuTeiConnector(
                client,
                promo_page_url=lambda _: "https://yuyu-tei.jp/sell/vg/s/dpromo-1000",
            ).search(card)

    offers = asyncio.run(run())
    assert requested_urls == ["https://yuyu-tei.jp/sell/vg/s/dpromo-1000"]
    assert len(offers) == 1
    assert offers[0].price_yen == 420


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


def test_cardrush_uses_the_japanese_promo_serial_as_its_search_keyword() -> None:
    card = CardPrint(
        set_code="D-PR",
        collector_number="953",
        rarity="PR",
        english_name="Leuhan",
        japanese_name="大地を駆ける守主 ルアン",
        source="test",
    )
    keywords: list[str | None] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        keywords.append(request.url.params.get("keyword"))
        return httpx.Response(
            200,
            text="""
            <li><a href="/product/37230"><p>大地を駆ける守主ルアン【PR】{
            <span class="result-emphasis"><b>D-PR/953</b></span>}</p>
            <p>280円（税込）</p><p>×</p></a></li>
            """,
        )

    async def run() -> list[object]:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await CardRushConnector(client).search(card)

    offers = asyncio.run(run())
    assert keywords == ["D-PR/953"]
    assert len(offers) == 1
    assert offers[0].availability == Availability.SOLD_OUT
    assert offers[0].price_yen == 280


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


def test_olta_matches_exact_prints_and_keeps_sold_out_prices() -> None:
    card = CardPrint(
        set_code="DZ-BT09",
        collector_number="006",
        rarity="RRR",
        english_name="Finile",
        japanese_name="ダイアフルドール ふぃんりー",
        source="test",
    )
    offers = OltaConnector.parse_items(
        card,
        [
            {
                "name": "ダイアフルドール ふぃんりー[RRR][DZ-BT09/006]",
                "code": "494485",
                "productSkus": [
                    {
                        "skuCode": "condition-a-494485",
                        "price": 1290,
                        "stock": 5,
                        "noStockPurchasable": False,
                        "productVariationValues": [{"variationValueName": "A+"}],
                    },
                    {
                        "skuCode": "condition-b-494485",
                        "price": 980,
                        "stock": 0,
                        "noStockPurchasable": False,
                        "productVariationValues": [{"variationValueName": "A-"}],
                    },
                ],
            },
            {
                "name": "別のカード[RRR][DZ-BT09/007]",
                "code": "other",
                "productSkus": [{"skuCode": "other", "price": 100, "stock": 1}],
            },
        ],
    )
    assert [(offer.price_yen, offer.availability, offer.stock_count) for offer in offers] == [
        (1290, Availability.IN_STOCK, 5),
        (980, Availability.SOLD_OUT, 0),
    ]
    assert [offer.condition for offer in offers] == ["A+", "A-"]
    assert offers[0].listing_url == "https://olta-tcg.com/VG/product/detail/494485"


def test_manzokuya_matches_serial_and_reports_numeric_circle_and_sold_out_stock() -> None:
    html = """
    <ul>
      <li><a href="/products/detail/238590"><img alt="!★パラ★ [ FFR ] DZ-BT16/FFR14 主峰の伝説・エスタシオン“華馳弩樹”"></a>
        <p>￥1,680 (税込)</p><p>在庫: 3</p><button>カートに入れる</button></li>
      <li><a href="/products/detail/238591"><img alt="[FFR] DZ-BT16/FFR14 主峰の伝説・エスタシオン“華馳弩樹”"></a>
        <p>￥1,580 (税込)</p><p>在庫: ◯</p><button>カートに入れる</button></li>
      <li><a href="/products/detail/238592"><img alt="[FFR] DZ-BT16/FFR14 主峰の伝説・エスタシオン“華馳弩樹”"></a>
        <p>SOLD OUT</p><p>￥1,180 (税込)</p><button disabled>ただいま品切れ中です。</button></li>
      <li><a href="/products/detail/other"><img alt="[FFR] DZ-BT16/FFR13 別のカード"></a><p>￥100</p></li>
    </ul>
    """
    card = CardPrint(
        set_code="DZ-BT16",
        collector_number="FFR14",
        rarity="FFR",
        english_name="Estacion",
        japanese_name="主峰の伝説・エスタシオン“華馳弩樹”",
        source="test",
    )
    offers = ManzokuyaConnector.parse_html(card, html)
    assert [(offer.price_yen, offer.availability, offer.stock_count) for offer in offers] == [
        (1680, Availability.IN_STOCK, 3),
        (1580, Availability.IN_STOCK, None),
        (1180, Availability.SOLD_OUT, 0),
    ]
    assert offers[0].listing_url == "https://shopmanzokuya.com/products/detail/238590"


def test_mana_source_matches_serial_and_retains_a_sold_out_offer_without_price() -> None:
    html = """
    <ul>
      <li><a href="/product/195805"><p>【FFR】主峰の伝説・エスタシオン “華馳弩樹” DZ-BT16/FFR14</p>
        <p>1,680円 (税込)</p><p>在庫数 2個</p></a></li>
      <li><a href="/product/195806"><p>【FFR】主峰の伝説・エスタシオン “華馳弩樹” DZ-BT16/FFR14</p>
        <p>在庫なし</p></a></li>
      <li><a href="/product/other"><p>【FFR】別のカード DZ-BT16/FFR13</p><p>100円</p></a></li>
    </ul>
    """
    card = CardPrint(
        set_code="DZ-BT16",
        collector_number="FFR14",
        rarity="FFR",
        english_name="Estacion",
        japanese_name="主峰の伝説・エスタシオン“華馳弩樹”",
        source="test",
    )
    offers = ManaSourceConnector.parse_html(card, html)
    assert [(offer.price_yen, offer.availability, offer.stock_count) for offer in offers] == [
        (1680, Availability.IN_STOCK, 2),
        (None, Availability.SOLD_OUT, None),
    ]
    assert offers[1].price_display == "Price unavailable"
    assert offers[0].listing_url == "https://www.manasource.net/product/195805"


def test_amenity_dream_matches_exact_serial_and_reports_stock() -> None:
    html = """
    <ul><li><a href="/product/136258"><img alt="【FFR】エグザサベイト・ドラゴン"><p>
    VAN_DZ-BT16/FFR02_FFR</p><p>1,680円 (税込)</p><p>在庫数 2点</p></a><button>カートに入れる</button></li>
    <li><a href="/product/other"><img alt="別のカード"><p>DZ-BT16/FFR03</p><p>100円</p></a></li></ul>
    """
    offers = AmenityDreamConnector.parse_html(CARD, html)
    assert len(offers) == 1
    assert (offers[0].price_yen, offers[0].availability, offers[0].stock_count) == (1680, Availability.IN_STOCK, 2)
    assert offers[0].listing_url == "https://www.amenitydream.com/product/136258"


def test_fullahead_matches_exact_serial_and_uses_detail_stock() -> None:
    search_html = """
    <div class="indexItemBox"><div><a href="/shop/shopdetail.html?brandcode=1"><img alt="DZ-BT16/FFR02 エグザサベイト・ドラゴン FFR"></a><strong>1,280円</strong></div>
    <div><a href="/shop/shopdetail.html?brandcode=2"><img alt="DZ-BT16/FFR03 別のカード"></a><strong>100円</strong></div></div>
    """
    offers = FullAheadConnector.parse_html(CARD, search_html)
    assert len(offers) == 1
    assert offers[0].availability == Availability.UNKNOWN
    detailed = FullAheadConnector._with_detail_stock(offers[0], '<span class="M_item-stock-smallstock">残りあと1点</span><a class="add_cart">cart</a>')
    assert (detailed.price_yen, detailed.availability, detailed.stock_count) == (1280, Availability.IN_STOCK, 1)


def test_torecolo_matches_its_hyphenated_product_code_and_keeps_oos_price() -> None:
    html = """
    <dl class="block-thumbnail-t--goods"><a href="/shop/g/gDZ-BT16-FFR02/" title="エグザサベイト・ドラゴン FFR"></a>
    <div>1,200円（税込）</div><p>在庫 <span>3</span></p></dl>
    <dl class="block-thumbnail-t--goods"><a href="/shop/g/gDZ-BT16-FFR03/" title="別のカード"></a><div>100円</div><p>在庫 1</p></dl>
    <dl class="block-thumbnail-t--goods"><a href="/shop/g/gDZ-BT16-FFR02/" title="エグザサベイト・ドラゴン FFR"></a><div>980円</div><p>在庫 0</p><span>売切れ</span></dl>
    """
    offers = TorecoloConnector.parse_html(CARD, html)
    assert [(offer.price_yen, offer.availability, offer.stock_count) for offer in offers] == [
        (1200, Availability.IN_STOCK, 3),
        (980, Availability.SOLD_OUT, 0),
    ]
    assert offers[0].listing_url == "https://www.torecolo.jp/shop/g/gDZ-BT16-FFR02/"


def test_cardmax_matches_exact_serial_and_uses_detail_stock() -> None:
    search_html = """
    <table><tr><td><a href="/shop/shopdetail.html?brandcode=1"><img alt="DZBT16 エグザサベイト・ドラゴン(FFR)(DZBT16/FFR02)"></a></td><td>1,280円</td></tr>
    <tr><td><a href="/shop/shopdetail.html?brandcode=2">別のカード (DZBT16/FFR03)</a></td><td>100円</td></tr></table>
    """
    offers = CardMaxConnector.parse_html(CARD, search_html)
    assert len(offers) == 1
    detailed = CardMaxConnector._with_detail_stock(offers[0], '<span class="M_item-stock-smallstock">残りあと2個</span>')
    assert (detailed.price_yen, detailed.availability, detailed.stock_count) == (1280, Availability.IN_STOCK, 2)


def test_avalon_matches_exact_serial_and_uses_detail_stock() -> None:
    search_html = """
    <ul class="product"><li><a href="?pid=1">DZ-BT16/FFR02 エグザサベイト・ドラゴン FFR</a><span class="price">1,280円(税込1,408円)</span></li>
    <li><a href="?pid=2">DZ-BT16/FFR03 別のカード</a><span class="price">100円</span></li></ul>
    """
    offers = AvalonConnector.parse_html(CARD, search_html)
    assert len(offers) == 1
    detailed = AvalonConnector._with_detail_stock(offers[0], "<td class='mark'>在庫6つです！</td>")
    assert (detailed.price_yen, detailed.availability, detailed.stock_count) == (1280, Availability.IN_STOCK, 6)


def test_clabo_matches_exact_serial_and_retains_sold_out_price() -> None:
    html = """
    <div class="list_item_cell"><a href="/product/1"><p class="item_name"><span class="goods_name">【VG】エグザサベイト・ドラゴン【FFR】DZ-BT16/FFR02</span></p>
    <span class="figure">1,280円</span><p class="stock soldout">在庫なし</p></a></div>
    <div class="list_item_cell"><a href="/product/2"><span class="goods_name">別のカード DZ-BT16/FFR03</span><span>100円</span></a></div>
    """
    offers = CLaboConnector.parse_html(CARD, html)
    assert len(offers) == 1
    assert (offers[0].price_yen, offers[0].availability, offers[0].stock_count) == (1280, Availability.SOLD_OUT, None)


def test_realize_matches_exact_serial_and_uses_detail_stock() -> None:
    search_html = """
    <li class="productlist-unit"><a href="?pid=1"><img alt="ヴァンガード DZ-BT16/FFR02 エグザサベイト・ドラゴン FFR"></a><span class="price">1,280円</span></li>
    <li class="productlist-unit"><a href="?pid=2"><img alt="ヴァンガード DZ-BT16/FFR03 別のカード"></a><span class="price">100円</span></li>
    """
    offers = RealizeConnector.parse_html(CARD, search_html)
    assert len(offers) == 1
    detailed = RealizeConnector._with_detail_stock(offers[0], '"stock_num":14,"sales_price":1280')
    assert (detailed.price_yen, detailed.availability, detailed.stock_count) == (1280, Availability.IN_STOCK, 14)


def test_new_store_connectors_search_by_hyphenated_japanese_serial() -> None:
    requests: dict[str, str | None] = {}

    async def handler(request: httpx.Request) -> httpx.Response:
        requests[request.url.host] = request.url.params.get("keyword") or request.url.params.get("name")
        if request.url.host == "olta-tcg.com":
            assert json.loads(request.content)["variables"]["where"]["name"]["contains"] == "DZ-BT16/FFR02"
            return httpx.Response(200, json={"data": {"productFaces": {"items": []}}})
        return httpx.Response(200, text="")

    async def run() -> None:
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await OltaConnector(client).search(CARD)
            await ManzokuyaConnector(client).search(CARD)
            await ManaSourceConnector(client).search(CARD)
            await AmenityDreamConnector(client).search(CARD)
            await TorecoloConnector(client).search(CARD)

    asyncio.run(run())
    assert requests == {
        "olta-tcg.com": None,
        "shopmanzokuya.com": "DZ-BT16/FFR02",
        "www.manasource.net": "DZ-BT16/FFR02",
        "www.amenitydream.com": "DZ-BT16/FFR02",
        "www.torecolo.jp": "DZ-BT16-FFR02",
    }
