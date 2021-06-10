from aiohttp import web
from datetime import timedelta
from random import randint

from prozorro_chronograph.settings import SMOOTHING_MAX, SMOOTHING_MIN, scheduler
from prozorro_chronograph.utils import get_now
from prozorro_chronograph.scheduler import recheck_tender, resync_tender
from prozorro_chronograph.storage import get_calendar, set_holiday, delete_holiday

routes = web.RouteTableDef()


@routes.get("/resync/{tender_id}")
async def resync_view(request):
    tender_id = request.match_info["tender_id"]

    scheduler.add_job(
        resync_tender,
        run_date=get_now() + timedelta(milliseconds=randint(SMOOTHING_MIN, SMOOTHING_MAX)),
        misfire_grace_time=60 * 60,
        replace_existing=True,
        name="Resync from api",
        id=f"resync_api_{tender_id}",
        args=[tender_id],
    )
    return web.json_response(None)


@routes.get("/recheck/{tender_id}")
async def recheck_view(request):
    tender_id = request.match_info["tender_id"]

    scheduler.add_job(
        recheck_tender,
        run_date=get_now() + timedelta(milliseconds=randint(SMOOTHING_MIN, SMOOTHING_MAX)),
        misfire_grace_time=60 * 60,
        replace_existing=True,
        name="Recheck from api",
        id=f"recheck_api_{tender_id}",
        args=[tender_id],
    )
    return web.json_response(None)


@routes.get("/jobs")
async def jobs(request):
    jobs = {i.id: i.next_run_time.isoformat() for i in scheduler.get_jobs()}
    return web.json_response({"jobs": jobs})


@routes.get("/calendar")
async def calendar_view(request):
    working_days = await get_calendar()
    return web.json_response({"working_days": working_days})


@routes.post("/calendar/{date}")
async def set_holiday_view(request):
    date = request.match_info["date"]
    await set_holiday(date)
    return web.json_response(None)


@routes.delete("/calendar/{date}")
async def delete_holiday_view(request):
    date = request.match_info["date"]
    await delete_holiday(date)
    return web.json_response(None)


def create_app():
    app = web.Application()
    app.add_routes(routes=routes)
    return app
