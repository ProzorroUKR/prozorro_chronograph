import asyncio
from aiohttp import web, ClientSession
from prozorro_crawler.main import main

from prozorro_chronograph.settings import scheduler, PUBLIC_API_HOST, INVALID_STATUSES, LOGGER
from prozorro_chronograph.api import create_app
from prozorro_chronograph.scheduler import process_listing
from prozorro_chronograph.storage import init_database


async def data_handler(session: ClientSession, items: list) -> None:
    server_id_cookie = getattr(
        session.cookie_jar.filter_cookies(PUBLIC_API_HOST).get("SERVER_ID"), "value", None
    )
    process_items_tasks = []
    for item in items:
        status = item.get("status", None)
        tender_id = item.get("id", None)
        if item.get("status", None) not in INVALID_STATUSES:
            coroutine = process_listing(server_id_cookie, item)
            process_items_tasks.append(coroutine)
        else:
            LOGGER.info(f"Skip tender {tender_id} with status {status}")
    await asyncio.gather(*process_items_tasks)


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    app = create_app()

    app = web.AppRunner(app)
    loop.run_until_complete(app.setup())
    site = web.TCPSite(app)

    loop.run_until_complete(init_database())
    loop.run_until_complete(site.start())
    scheduler.start()

    main(data_handler)
