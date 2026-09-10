"""Telegram-safe presentation of search and comparison results."""

from __future__ import annotations

from html import escape
from typing import Sequence

from scraperbot.models import Availability, CardPrint, ComparisonResult, Finish


def format_card_choices(cards: Sequence[CardPrint]) -> str:
    lines = ["Choose a card:"]
    for index, card in enumerate(cards, start=1):
        lines.append(f"{index}. {escape(card.english_name)} — {escape(card.display_code)}")
    return "\n".join(lines)


def format_comparison(result: ComparisonResult) -> str:
    card = result.card
    lines = [f"<b>{escape(card.english_name)}</b>", escape(card.display_code)]
    if result.offers:
        for offer in result.offers:
            store = escape(offer.store_name)
            condition = f" ({escape(offer.condition)})" if offer.condition else ""
            price = escape(offer.price_display)
            if offer.stock_count is not None:
                availability = f" — {offer.stock_count} left"
            elif offer.availability == Availability.SOLD_OUT:
                availability = " — ×"
            elif offer.availability == Availability.IN_STOCK:
                availability = " — ◯"
            else:
                availability = ""
            finish_label = offer.finish_raw or (
                "Holo" if offer.finish is Finish.HOLO else "Standard" if offer.finish is Finish.STANDARD else ""
            )
            finish = f" · {escape(finish_label)}" if finish_label else ""
            if offer.listing_url:
                lines.append(
                    f'<a href="{escape(offer.listing_url, quote=True)}">{store}</a>{condition}: {price}{availability}{finish}'
                )
            else:
                lines.append(f"{store}{condition}: {price}{availability}{finish}")
    else:
        lines.append("No matching offers found.")
    if result.no_active_listing_stores:
        lines.append(
            "No active listing (sold out or not stocked): "
            + escape(", ".join(result.no_active_listing_stores))
        )
    if result.unavailable_stores:
        lines.append(f"Not listed: {escape(', '.join(result.unavailable_stores))}")
    if result.failed_stores:
        lines.append(f"Temporarily unavailable: {escape(', '.join(result.failed_stores))}")
    return "\n".join(lines)
