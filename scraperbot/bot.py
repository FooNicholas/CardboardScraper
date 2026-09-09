"""Natural-language Telegram interaction for the local card catalogue."""

from __future__ import annotations

from html import escape
from typing import Final
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import CallbackQueryHandler, CommandHandler, ContextTypes, MessageHandler, filters

from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.models import CardPrint
from scraperbot.query import parse_name_query
from scraperbot.services.comparison import ComparisonService
from scraperbot.services.formatting import format_card_choices, format_comparison


MAX_CHOICES: Final = 8


def choice_keyboard(cards: list[CardPrint]) -> InlineKeyboardMarkup:
    """Build compact buttons without exposing a card number as an input field."""
    rows = []
    for card in cards:
        assert card.id is not None
        name = card.english_name
        label = f"{name[:54]}{'…' if len(name) > 54 else ''} — {card.display_code}"
        rows.append([InlineKeyboardButton(label, callback_data=f"card:{card.id}")])
    return InlineKeyboardMarkup(rows)


class TelegramPriceBot:
    """Handlers for card-name search, selection, and concurrent comparison."""

    def __init__(self, catalogue: CatalogueRepository, comparison: ComparisonService) -> None:
        self.catalogue = catalogue
        self.comparison = comparison

    def handlers(self) -> list[object]:
        return [
            CommandHandler("start", self.start),
            CommandHandler(("price", "compare"), self.price),
            CommandHandler("sites", self.sites),
            CallbackQueryHandler(self.select_card, pattern=r"^card:\d+$"),
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.free_text),
        ]

    async def start(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message:
            await update.effective_message.reply_text(
                "Send an English card name, even a partial one.\n"
                "Examples: /price Youthberk, /price chronojet ffr\n\n"
                "I will show matching Japanese-market prints, then compare the supported stores."
            )

    async def sites(self, update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message:
            names = ", ".join(connector.store_name for connector in self.comparison.connectors)
            await update.effective_message.reply_text(f"Currently comparing: {names}.")

    async def price(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        await self._search_and_present(update, context, " ".join(context.args))

    async def free_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.effective_message and update.effective_message.text:
            await self._search_and_present(update, context, update.effective_message.text)

    async def _search_and_present(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE, raw_query: str
    ) -> None:
        message = update.effective_message
        query, rarity = parse_name_query(raw_query)
        if not message:
            return
        if not query:
            await message.reply_text("Try a card name, such as: /price Youthberk")
            return

        cards = self.catalogue.search(query, rarity=rarity, limit=MAX_CHOICES, japanese_only=True)
        if not cards:
            suffix = f" with rarity {rarity}" if rarity else ""
            await message.reply_text(
                f"No Japanese-market card print matched “{query}”{suffix}. "
                "Try a shorter spelling or refresh the catalogue."
            )
            return

        if len(cards) == 1:
            await self._compare_and_reply(message, cards[0])
            return

        context.user_data["candidate_print_ids"] = [card.id for card in cards if card.id is not None]
        await message.reply_html(format_card_choices(cards), reply_markup=choice_keyboard(cards))

    async def select_card(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        callback = update.callback_query
        if not callback or not callback.data:
            return
        selected_id = int(callback.data.removeprefix("card:"))
        allowed_ids = set(context.user_data.get("candidate_print_ids", []))
        if selected_id not in allowed_ids:
            await callback.answer("That search selection has expired. Please search again.", show_alert=True)
            return
        card = self.catalogue.get(selected_id, japanese_only=True)
        if not card:
            await callback.answer("That card is no longer in the local catalogue.", show_alert=True)
            return
        await callback.answer()
        await callback.edit_message_text("Checking stores…")
        await self._compare_and_reply(callback.message, card, replace=True)

    async def _compare_and_reply(self, message: object, card: CardPrint, *, replace: bool = False) -> None:
        if not hasattr(message, "reply_text"):
            return
        progress = None
        if not replace:
            progress = await message.reply_text("Checking stores…")
        try:
            result = await self.comparison.compare(card)
            body = format_comparison(result)
            target = message if replace else progress
            assert target is not None
            await target.edit_text(body, parse_mode=ParseMode.HTML, disable_web_page_preview=True)
        except Exception:
            target = message if replace else progress
            assert target is not None
            await target.edit_text(
                f"I could not compare <b>{escape(card.english_name)}</b> right now. Please try again shortly.",
                parse_mode=ParseMode.HTML,
            )
