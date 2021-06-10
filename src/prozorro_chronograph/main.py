import asyncio
from aiohttp import web
from prozorro_crawler.main import main

from prozorro_chronograph.settings import scheduler
from prozorro_chronograph.api import create_app
from prozorro_chronograph.scheduler import process_listing
from prozorro_chronograph.storage import init_database


async def data_handler(session, items):
    server_id_cookie = getattr(
        session.cookie_jar.filter_cookies().get("SERVER_ID"), "value", None
    )
    process_items_tasks = (process_listing(server_id_cookie, item) for item in items)
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
