import asyncio

from scraperbot.connectors.base import StoreConnector, StoreUnavailableError
from scraperbot.models import Availability, CardPrint, MatchConfidence, StoreOffer
from scraperbot.services.comparison import ComparisonService
from scraperbot.services.formatting import format_comparison, format_family_comparison


CARD = CardPrint("DZBT16", "FFR02", "FFR", "Exzabite Dragon", source="test")


class FixedConnector(StoreConnector):
    def __init__(self, store_id: str, outcome: list[StoreOffer] | Exception) -> None:
        self.store_id = store_id
        self.store_name = store_id.title()
        self.outcome = outcome
        self.calls = 0

    async def search(self, card: CardPrint) -> list[StoreOffer]:
        self.calls += 1
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


class FamilyConnector(StoreConnector):
    store_id = "family"
    store_name = "Family Store"

    async def search(self, card: CardPrint) -> list[StoreOffer]:
        price = 900 if card.collector_number == "001" else 400
        return [offer(self.store_id, price)]


def offer(
    store: str,
    price: int,
    availability: Availability = Availability.IN_STOCK,
    stock_count: int | None = None,
) -> StoreOffer:
    return StoreOffer(
        store_id=store,
        store_name=store.title(),
        raw_name="raw",
        price_yen=price,
        price_display=f"¥{price:,}",
        availability=availability,
        listing_url=f"https://example.test/{store}",
        match_confidence=MatchConfidence.EXACT_PRINT,
        stock_count=stock_count,
    )


def test_comparison_sorts_prices_and_keeps_partial_results() -> None:
    service = ComparisonService(
        [
            FixedConnector("expensive", [offer("expensive", 1800)]),
            FixedConnector("cheap", [offer("cheap", 900)]),
            FixedConnector("offline", StoreUnavailableError("not listed")),
        ]
    )
    result = asyncio.run(service.compare(CARD))
    assert [item.store_id for item in result.offers] == ["cheap", "expensive"]
    assert result.unavailable_stores == ("Offline",)
    rendered = format_comparison(result)
    assert "Exzabite Dragon" in rendered
    assert "¥900" in rendered


def test_comparison_uses_cache_until_refreshed() -> None:
    connector = FixedConnector("only", [offer("only", 1000)])
    service = ComparisonService([connector])
    asyncio.run(service.compare(CARD))
    asyncio.run(service.compare(CARD))
    assert connector.calls == 1
    asyncio.run(service.compare(CARD, refresh=True))
    assert connector.calls == 2


def test_comparison_reports_a_store_with_no_active_listing() -> None:
    service = ComparisonService([FixedConnector("empty", [])])
    result = asyncio.run(service.compare(CARD))
    assert result.no_active_listing_stores == ("Empty",)
    assert "sold out or not stocked" in format_comparison(result)


def test_comparison_labels_an_out_of_stock_price() -> None:
    result = asyncio.run(
        ComparisonService(
            [FixedConnector("store", [offer("store", 980, Availability.SOLD_OUT, stock_count=0)])]
        ).compare(CARD)
    )
    rendered = format_comparison(result)
    assert "¥980" in rendered
    assert "0 left" in rendered


def test_comparison_includes_a_listed_stock_count() -> None:
    result = asyncio.run(ComparisonService([FixedConnector("store", [offer("store", 420, stock_count=3)])]).compare(CARD))
    assert "3 left" in format_comparison(result)


def test_family_comparison_sorts_exact_print_offers_by_price() -> None:
    base = CardPrint("DZBT01", "001", "RRR", "Example Card", japanese_name="日本語名", source="test")
    reprint = CardPrint("DZBT02", "002", "FFR", "Example Card", japanese_name="日本語名", source="test")

    result = asyncio.run(ComparisonService([FamilyConnector()]).compare_family(base, [base, reprint]))

    assert [item.offer.price_yen for item in result.offers] == [400, 900]
    assert [item.card.collector_number for item in result.offers] == ["002", "001"]
    rendered = format_family_comparison(result)
    assert "DZBT02/002 · FFR" in rendered
    assert "¥400" in rendered
