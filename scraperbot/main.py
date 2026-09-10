"""Local entry point for the Telegram price-comparison bot."""

from __future__ import annotations

from telegram import Update
from telegram.ext import Application, ApplicationBuilder

from scraperbot.bot import TelegramPriceBot
from scraperbot.catalogue.repository import CatalogueRepository
from scraperbot.config import Settings
from scraperbot.connectors.bigweb import BigWebConnector
from scraperbot.connectors.cardrush import CardRushConnector
from scraperbot.connectors.vanhappy import VanHappyConnector
from scraperbot.connectors.yuyutei import YuyuTeiConnector
from scraperbot.services.comparison import ComparisonService


def build_application(settings: Settings | None = None) -> Application:
    """Assemble the local polling application without making network calls."""
    settings = settings or Settings.from_environment()
    catalogue = CatalogueRepository(settings.catalogue_db)
    bot = TelegramPriceBot(
        catalogue,
        ComparisonService((YuyuTeiConnector(), BigWebConnector(), CardRushConnector(), VanHappyConnector())),
    )
    application = ApplicationBuilder().token(settings.require_bot_token()).build()
    for handler in bot.handlers():
        application.add_handler(handler)
    application.bot_data["catalogue"] = catalogue
    return application


def run() -> None:
    """Run locally with Telegram long polling; no hosting configuration is needed."""
    application = build_application()
    application.run_polling(allowed_updates=Update.ALL_TYPES)
