"""Runtime configuration kept separate from bot and web code."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv

from scraperbot.distribution import (
    DEFAULT_UPDATE_MANIFEST_URL,
    default_catalogue_database,
    is_packaged_application,
)


@dataclass(frozen=True, slots=True)
class Settings:
    """Settings for a local polling bot.

    Nothing is sent anywhere until a valid ``BOT_TOKEN`` is supplied through
    the environment (usually an untracked ``.env`` file).
    """

    bot_token: str | None
    catalogue_db: Path
    catalogue_update_manifest_url: str | None

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
        configured_database = os.getenv("CATALOGUE_DB")
        configured_manifest = os.getenv("CATALOGUE_UPDATE_MANIFEST_URL")
        return cls(
            bot_token=os.getenv("BOT_TOKEN") or None,
            catalogue_db=Path(configured_database).expanduser() if configured_database else default_catalogue_database(),
            # Source checkouts remain intentionally offline unless the curator
            # configures a release channel. Desktop downloads receive the
            # public project release channel by default.
            catalogue_update_manifest_url=(
                configured_manifest
                if configured_manifest is not None
                else DEFAULT_UPDATE_MANIFEST_URL if is_packaged_application() else None
            ),
        )

    def require_bot_token(self) -> str:
        if not self.bot_token:
            raise RuntimeError(
                "BOT_TOKEN is not set. Create a Telegram bot with BotFather and put its token in .env."
            )
        return self.bot_token
