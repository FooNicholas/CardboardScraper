import pytest

from scraperbot.catalogue.yuyutei_promo_source import YuyuTeiPromoCatalogueSource


PROMO_PAGE = """
<div class="col-md"><div class="card-product">
  <a href="/sell/vg/card/dpromo-1200/10019"><img alt="D-PR/1101 PR エネルギー"></a>
  <span>D-PR/1101</span><a href="/sell/vg/card/dpromo-1200/10019"><h4>エネルギー</h4></a>
  <input class="cart_cid" value="10019">
</div></div>
<div class="col-md"><div class="card-product">
  <a href="https://yuyu-tei.jp/sell/vg/card/dpromo-1200/10020"><img alt="D-PR/1102 PR Card"></a>
  <span>D-PR/1102</span><a href="https://yuyu-tei.jp/sell/vg/card/dpromo-1200/10020"><h4>カード名</h4></a>
  <input class="cart_cid" value="10020">
</div></div>
<div class="col-md"><div class="card-product">
  <a href="/sell/vg/card/dzbt16/10001"><img alt="DZ-BT16/001 R Ignore"></a>
  <span>DZ-BT16/001</span><a href="/sell/vg/card/dzbt16/10001"><h4>Ignore</h4></a>
</div></div>
"""

PROMO_PAGE_CONTROLS = """
<input type="checkbox" name="vers[]" value="dpromo-1800">
<input type="checkbox" name="vers[]" value="dpromo-100">
<input type="checkbox" name="vers[]" value="dpromo-1200">
<input type="checkbox" name="vers[]" value="promo-100">
<input type="checkbox" name="vers[]" value="dpromo-other">
"""


def test_yuyutei_promo_parser_extracts_exact_dpr_entries() -> None:
    source = YuyuTeiPromoCatalogueSource()
    page_url = source.page_url("dpromo-1200")

    entries = source.parse_entries("dpromo-1200", page_url, PROMO_PAGE)

    assert [(entry.set_code, entry.collector_number, entry.japanese_name) for entry in entries] == [
        ("DPR", "1101", "エネルギー"),
        ("DPR", "1102", "カード名"),
    ]
    assert entries[0].listing_url == "https://yuyu-tei.jp/sell/vg/card/dpromo-1200/10019"
    assert entries[0].product_id == "10019"


def test_yuyutei_promo_page_slug_is_constrained() -> None:
    with pytest.raises(ValueError):
        YuyuTeiPromoCatalogueSource().page_url("https://example.test/not-a-promo-page")


def test_yuyutei_promo_page_discovery_uses_only_numeric_dpromo_controls() -> None:
    assert YuyuTeiPromoCatalogueSource.parse_page_slugs(PROMO_PAGE_CONTROLS) == [
        "dpromo-100",
        "dpromo-1200",
        "dpromo-1800",
    ]
