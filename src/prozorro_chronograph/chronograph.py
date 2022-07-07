import asyncio
import sentry_sdk
from aiohttp import web, ClientSession
from prozorro_crawler.main import main
from prozorro_chronograph.settings import (
    scheduler,
    SENTRY_DSN,
)
from prozorro_chronograph.api import create_app
from prozorro_chronograph.scheduler import schedule_next_check
from prozorro_chronograph.storage import init_database


async def data_handler(_: ClientSession, items: list) -> None:
    process_items_tasks = []
    for tender in items:
        next_check = tender.get("next_check")
        if next_check:
            process_items_tasks.append(
                schedule_next_check(
                    tender["id"],
                    next_check,
                )
            )
    if process_items_tasks:
        await asyncio.gather(*process_items_tasks)


async def run_services():
    app = create_app()
    app = web.AppRunner(app)
    await app.setup()
    site = web.TCPSite(app)

    await init_database()
    await site.start()
    scheduler.start()


if __name__ == "__main__":
    if SENTRY_DSN:
        sentry_sdk.init(dsn=SENTRY_DSN)
    main(
        data_handler,
        init_task=run_services,
        opt_fields=["next_check"]
    )
