"""Telegram-safe presentation of search and comparison results."""

from __future__ import annotations

from html import escape
from typing import Sequence

from scraperbot.models import CardPrint, ComparisonResult


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
            price = escape(offer.price_display)
            if offer.listing_url:
                lines.append(f'<a href="{escape(offer.listing_url, quote=True)}">{store}</a>: {price}')
            else:
                lines.append(f"{store}: {price}")
    else:
        lines.append("No matching offers found.")
    if result.unavailable_stores:
        lines.append(f"Not listed: {escape(', '.join(result.unavailable_stores))}")
    if result.failed_stores:
        lines.append(f"Temporarily unavailable: {escape(', '.join(result.failed_stores))}")
    return "\n".join(lines)
