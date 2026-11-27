import asyncio
import logging
import os
from aiohttp import web
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from db import Database
from handlers import router
from pg_storage import PostgresStorage

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def parse_admin_ids() -> list[int]:
    raw = os.getenv("ADMIN_IDS") or os.getenv("ADMIN_ID") or ""
    ids = []
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit():
            ids.append(int(part))
    return ids


async def start_health_server() -> web.AppRunner:
    """Мини-вебсервер для Render и аптаймеров (UptimeRobot / cron-job)."""
    async def health(_request: web.Request) -> web.Response:
        return web.Response(text="OK")

    app = web.Application()
    app.router.add_get("/", health)
    app.router.add_head("/", health)

    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.getenv("PORT", "10000"))
    site = web.TCPSite(runner, host="0.0.0.0", port=port)
    await site.start()
    logger.info("Health-сервер запущен на порту %s", port)
    return runner


async def main() -> None:
    bot_token = os.getenv("BOT_TOKEN", "").strip()
    database_url = os.getenv("DATABASE_URL", "").strip()
    gemini_api_key = os.getenv("GEMINI_API_KEY", "").strip() or None
    admin_ids = parse_admin_ids()

    if not bot_token:
        raise RuntimeError("Не задан BOT_TOKEN в переменных окружения Render!")
    if not database_url:
        raise RuntimeError("Не задан DATABASE_URL в переменных окружения Render!")

    db = Database(database_url)
    if hasattr(db, "connect"):
        await db.connect()
    elif hasattr(db, "init"):
        await db.init()

    storage = PostgresStorage(database_url)
    bot = Bot(
        token=bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    dp = Dispatcher(storage=storage)
    dp.include_router(router)

    # Передаём зависимости в хендлеры
    dp["db"] = db
    dp["admin_ids"] = admin_ids
    dp["gemini_api_key"] = gemini_api_key

    runner = await start_health_server()
    try:
        logger.info("Бот запущен и готов к работе.")
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    finally:
        await runner.cleanup()
        await storage.close()
        if hasattr(db, "close"):
            await db.close()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
