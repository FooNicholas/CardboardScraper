"""Runtime configuration kept separate from bot and web code."""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from dotenv import load_dotenv


@dataclass(frozen=True, slots=True)
class Settings:
    """Settings for a local polling bot.

    Nothing is sent anywhere until a valid ``BOT_TOKEN`` is supplied through
    the environment (usually an untracked ``.env`` file).
    """

    bot_token: str | None
    catalogue_db: Path

    @classmethod
    def from_environment(cls) -> "Settings":
        load_dotenv()
        return cls(
            bot_token=os.getenv("BOT_TOKEN") or None,
            catalogue_db=Path(os.getenv("CATALOGUE_DB", "data/catalogue.sqlite3")),
        )

    def require_bot_token(self) -> str:
        if not self.bot_token:
            raise RuntimeError(
                "BOT_TOKEN is not set. Create a Telegram bot with BotFather and put its token in .env."
            )
        return self.bot_token
