import asyncio
import sentry_sdk
from aiohttp import web, ClientSession
from prozorro_crawler.main import main
from prozorro_chronograph.settings import (
    scheduler,
    SENTRY_DSN,
    TZ,
    LOGGER,
)
from prozorro_chronograph.api import create_app
from prozorro_chronograph.scheduler import schedule_auction_planner, check_auction
from prozorro_chronograph.storage import init_database
from prozorro_chronograph.utils import parse_date


async def process_tender(tender):
    LOGGER.info(f"Start processing tender: {tender['id']}")
    await check_auction(tender)
    if any(
        "shouldStartAfter" in i.get("auctionPeriod", {})
        and parse_date(i["auctionPeriod"]["shouldStartAfter"], TZ).astimezone(TZ)
        > parse_date(i["auctionPeriod"].get("startDate", "0001-01-03"), TZ)
        for i in tender.get("lots", [])
    ) or (
        "shouldStartAfter" in tender.get("auctionPeriod", {})
        and parse_date(tender["auctionPeriod"]["shouldStartAfter"], TZ).astimezone(TZ)
        > parse_date(tender["auctionPeriod"].get("startDate", "0001-01-03"), TZ)
    ):
        await schedule_auction_planner(tender["id"])


async def data_handler(_: ClientSession, items: list) -> None:
    process_items_tasks = []
    for tender in items:
        process_items_tasks.append(
            process_tender(tender["id"])
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
        opt_fields=["status", "auctionPeriod", "lots", "next_check"],
    )
