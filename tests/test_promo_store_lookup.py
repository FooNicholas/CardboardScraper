"""Offline request/response regressions for serial-first promo price lookup."""

from dataclasses import replace

import httpx
import pytest

from scraperbot.connectors.base import StoreUnavailableError
from scraperbot.connectors.bigweb import BigWebConnector
from scraperbot.connectors.vanhappy import VanHappyConnector
from scraperbot.models import Availability, CardPrint, Finish


LEUHAN = CardPrint(
    set_code="D-PR", collector_number="953", rarity="PR",
    english_name="Guard Running Through The Earth, Leuhan",
    japanese_name="大地を駆ける守主 ルアン",
)


@pytest.mark.parametrize("number", ["001", "953", "1757"])
@pytest.mark.parametrize("japanese_name", [None, "大地を駆ける守主 ルアン"])
async def test_vanhappy_uses_serial_even_without_a_mapped_name(number, japanese_name):
    card = replace(LEUHAN, collector_number=number, japanese_name=japanese_name, english_name="")
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(200, text=f"""
          <div class="product-card">
            <p class="product-card__name"><a href="/view/item/promo">カード[D-PR/{number}]</a></p>
            <div class="product-card__price">￥280</div>
            <div class="product-card__stock">在庫 0 個</div>
          </div>
        """)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        offers = await VanHappyConnector(client).search(card)
    assert len(requests) == 1
    assert requests[0].url.path == "/view/search"
    assert requests[0].url.params["search_keyword"] == f"D-PR/{number}"
    assert [(o.price_yen, o.stock_count, o.availability) for o in offers] == [
        (280, 0, Availability.SOLD_OUT),
    ]


async def test_vanhappy_keeps_main_set_name_search():
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(200, text="")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = VanHappyConnector(client)
        await connector.search(replace(LEUHAN, set_code="DZ-BT01"))
        await connector.search(replace(LEUHAN, set_code="DZ-BT01", japanese_name=None))
    assert len(requests) == 1
    assert requests[0].url.params["search_keyword"] == LEUHAN.japanese_name


def test_vanhappy_promo_search_filters_near_serials_and_conflicting_finish():
    html = "".join(f"""
      <div class="product-card">
        <p class="product-card__name"><a href="/view/item/{i}">ルアン({finish})[{serial}]</a></p>
        <div class="product-card__price">￥420</div>
        <div class="product-card__stock">在庫 3 個</div>
      </div>
    """ for i, (serial, finish) in enumerate([
        ("D-PR/953", "H仕様"), ("D-PR/953", "通常仕様"),
        ("D-PR/9530", "H仕様"), ("D-PR/0953", "H仕様"), ("V-PR/953", "H仕様"),
    ]))
    offers = VanHappyConnector.parse_html(replace(LEUHAN, finish=Finish.HOLO), html)
    assert len(offers) == 1
    assert offers[0].finish == Finish.HOLO
    assert offers[0].finish_raw == "H仕様"
    assert offers[0].stock_count == 3


@pytest.mark.parametrize("number", ["001", "953", "1757"])
@pytest.mark.parametrize("japanese_name", [None, "大地を駆ける守主 ルアン"])
async def test_bigweb_discovers_dpr_and_queries_serial_without_rarity_requests(number, japanese_name):
    requests = []
    card = replace(LEUHAN, collector_number=number, japanese_name=japanese_name, english_name="")

    async def handler(request):
        requests.append(request)
        if request.url.path.endswith("cardsets.json"):
            return httpx.Response(200, json=[{"id": 144, "cardsets": [
                {"code": "V-PR", "id": 5759}, {"code": "D-PR", "id": 6856},
                {"code": "D-PR", "id": 7254, "is_separation": 1},
            ]}])
        assert request.url.path == "/products"
        assert dict(request.url.params) == {
            "game_id": "144", "cardsets": "6856", "is_box": "0", "name": f"D-PR/{number}",
        }
        return httpx.Response(200, json={"success": True, "pagenate": {"pageCount": 1}, "items": [
            {"id": 3318269, "name": "大地を駆ける守主 ルアン", "comment": f"D-PR/{number}",
             "price": 800, "stock_count": 1, "is_sold_out": False},
            {"id": 2, "name": "別のカード", "comment": f"D-PR/{number}0", "price": 10},
            {"id": 3, "name": "参照なし", "comment": "", "price": 10},
        ]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        offers = await BigWebConnector(client).search(card)
    assert len(requests) == 2
    assert [(o.price_yen, o.stock_count, o.availability) for o in offers] == [
        (800, 1, Availability.IN_STOCK),
    ]


async def test_bigweb_keeps_serial_filter_on_all_bounded_pages():
    requests = []

    async def handler(request):
        requests.append(request)
        assert request.url.params["name"] == "D-PR/953"
        page = int(request.url.params.get("page", "1"))
        return httpx.Response(200, json={"success": True, "pagenate": {"pageCount": 2}, "items": [
            {"id": page, "name": "ルアン(H仕様)", "comment": "D-PR/953", "price": 280,
             "stock_count": 0, "is_sold_out": True},
        ]})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = BigWebConnector(client)
        connector._cardsets = {"DPR": 6856}
        offers = await connector.search(replace(LEUHAN, rarity="", finish=Finish.HOLO))
    assert len(requests) == 2
    assert len(offers) == 2
    assert all(o.price_yen == 280 and o.availability == Availability.SOLD_OUT for o in offers)
    assert all(o.finish == Finish.HOLO for o in offers)


@pytest.mark.parametrize("status,success,page_count", [(200, True, 50), (200, False, 2), (429, False, 1)])
async def test_bigweb_never_expands_failed_or_overbroad_promo_search(status, success, page_count):
    requests = []

    async def handler(request):
        requests.append(request)
        return httpx.Response(status, json={
            "success": success, "items": [], "pagenate": {"pageCount": page_count},
        })

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        connector = BigWebConnector(client)
        connector._cardsets = {"DPR": 6856}
        with pytest.raises((StoreUnavailableError, httpx.HTTPStatusError)):
            await connector.search(LEUHAN)
    assert len(requests) == 1


def test_bigweb_rejects_missing_serial_and_conflicting_promo_finish():
    items = [
        {"id": 1, "name": "ルアン(H仕様)", "comment": "D-PR/953", "price": 800, "stock_count": 1},
        {"id": 2, "name": "ルアン(通常仕様)", "comment": "D-PR/953", "price": 80, "stock_count": 1},
        {"id": 3, "name": "ルアン", "comment": None, "cardset": {"slip": "D-PR"},
         "rarity": {"slip": "PR"}, "price": 1},
    ]
    offers = BigWebConnector.parse_items(replace(LEUHAN, finish=Finish.HOLO), items)
    assert len(offers) == 1
    assert offers[0].price_yen == 800
    assert offers[0].finish == Finish.HOLO
