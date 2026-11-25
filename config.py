import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    bot_token: str
    admin_ids: list[int]
    database_url: str
    port: int
    gemini_api_key: str | None


def load_config() -> Config:
    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("Не задан BOT_TOKEN в переменных окружения")

    raw_admins = os.getenv("ADMIN_ID", "").strip()
    admin_ids = [int(x.strip()) for x in raw_admins.split(",") if x.strip().isdigit()]
    if not admin_ids:
        raise ValueError("Не задан корректный ADMIN_ID в переменных окружения")

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise ValueError("Не задан DATABASE_URL в переменных окружения")

    port = int(os.getenv("PORT", "8080"))
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip() or None

    return Config(
        bot_token=token,
        admin_ids=admin_ids,
        database_url=database_url,
        port=port,
        gemini_api_key=gemini_api_key,
    )
