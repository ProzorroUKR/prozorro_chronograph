# TODO: request_id_middleware (либа квинты) заменить либо адаптировать, чтобы у запросов были X-Request-ID (X-Client-Request-ID)
# TODO: add_logging_context and context_unpack или изменить подход
# TODO: Добавить аннотации

import json
import asyncio
from aiohttp import ClientSession
from random import randint
from datetime import datetime, timedelta
from iso8601 import parse_date
from prozorro_crawler.storage import get_feed_position

from prozorro_chronograph.storage import (
    get_calendar,
    get_streams,
    get_date,
    set_date,
    find_free_slot,
    free_slots,
)
from prozorro_chronograph.settings import (
    TZ,
    PUBLIC_API_HOST,
    CHRONOGRAPH_HOST,
    API_TOKEN,
    SANDBOX_MODE,
    WORKING_DAY_START,
    WORKING_DAY_END,
    LOGGER,
    scheduler,
    SMOOTHING_MIN,
    SMOOTHING_MAX,
    SMOOTHING_REMIN,
)
from prozorro_chronograph.utils import (
    get_now,
    randomize,
    calc_auction_end_time,
    skipped_days,
)

SESSION = ClientSession()


async def push(url, params, server_id=None):
    # TODO Сделать вызов нужной функции без запроса

    tx = ty = 1
    while True:
        if server_id is None and not url.startswith(CHRONOGRAPH_HOST):
            feed_position = await get_feed_position()
            server_id = feed_position.get("server_id")

        SESSION.cookie_jar.update_cookies({"SERVER_ID": server_id})
        await SESSION.options(url)
        response = await SESSION.get(url, params=params)
        if response.status == 200:
            break
        server_id = None

        await asyncio.sleep(tx)
        tx, ty = ty, tx + ty


async def planning_auction(tender, start, quick=False, lot_id=None):
    tender_id = tender.get("id", "")
    mode = tender.get("mode", "")
    calendar = await get_calendar()
    streams = await get_streams()
    skipped_days = 0
    if quick:
        quick_start = calc_auction_end_time(0, start)
        return (quick_start, 0, skipped_days)
    start += timedelta(hours=1)
    if start.time() < WORKING_DAY_START:
        nextDate = start.date()
    else:
        nextDate = start.date() + timedelta(days=1)
    new_slot = True
    while True:
        if calendar.get(nextDate.isoformat()) or nextDate.weekday() in [
            5,
            6,
        ]:  # skip Saturday and Sunday
            nextDate += timedelta(days=1)
            continue
        dayStart, stream, plan = await get_date(mode, nextDate)
        freeSlot = find_free_slot(plan)
        if freeSlot:
            startDate, stream = freeSlot
            start, end, dayStart, new_slot = (
                startDate,
                startDate,
                startDate.time(),
                False,
            )
            break
        if dayStart >= WORKING_DAY_END and stream >= streams:
            nextDate += timedelta(days=1)
            skipped_days += 1
            continue
        if dayStart >= WORKING_DAY_END and stream < streams:
            stream += 1
            dayStart = WORKING_DAY_START
        start = TZ.localize(datetime.combine(nextDate, dayStart))
        end = start + timedelta(minutes=30)
        if dayStart == WORKING_DAY_START and end > TZ.localize(
            datetime.combine(nextDate, WORKING_DAY_END)
        ):
            break
        elif end <= TZ.localize(datetime.combine(nextDate, WORKING_DAY_END)):
            break
        nextDate += timedelta(days=1)
        skipped_days += 1
    await set_date(
        plan_id=plan["_id"],
        end_time=end.time(),
        stream_id=stream,
        tender_id=tender_id,
        lot_id=lot_id,
        start_time=dayStart,
        new_slot=new_slot,
    )
    return start, stream, skipped_days


async def check_auction(tender):
    auction_time = tender.get("auctionPeriod", {}).get("startDate") and parse_date(
        tender.get("auctionPeriod", {}).get("startDate"), TZ
    )
    lots = dict(
        [
            (i["id"], parse_date(i.get("auctionPeriod", {}).get("startDate"), TZ))
            for i in tender.get("lots", [])
            if i.get("auctionPeriod", {}).get("startDate")
        ]
    )

    # TODO: remove it
    # (1f03319183514180ab7f7361ec908fe1: key=lot_id, 2022-01-03T11:30:00: datetime, plantest_2021-04-23: plan_id)
    await free_slots(tender["id"], auction_time, lots)


async def check_tender(tender) -> dict:
    now = get_now()
    quick = SANDBOX_MODE and "quick" in tender.get("submissionMethodDetails", "")
    if (
        not tender.get("lots")
        and "shouldStartAfter" in tender.get("auctionPeriod", {})
        and tender["auctionPeriod"]["shouldStartAfter"]
        > tender["auctionPeriod"].get("startDate", "")
    ):
        period = tender.get("auctionPeriod")
        shouldStartAfter = max(
            parse_date(period.get("shouldStartAfter"), TZ).astimezone(TZ), now
        )
        planned = False
        while not planned:
            try:
                auctionPeriod, stream, skip_days = await planning_auction(
                    tender, shouldStartAfter, quick
                )
                planned = True
            except Exception as e:
                planned = False
                LOGGER.error(
                    "Error on planning tender '{}': {}".format(
                        tender.get("id", ""), repr(e)
                    )
                )
        auctionPeriod = randomize(auctionPeriod).isoformat()
        planned = "replanned" if period.get("startDate") else "planned"
        LOGGER.info(
            "{} auction for tender {} to {}. Stream {}.{}".format(
                planned.title(),
                tender["id"],
                auctionPeriod,
                stream,
                skipped_days(skip_days),
            )
        )
        return {"auctionPeriod": {"startDate": auctionPeriod}}
    elif tender.get("lots"):
        lots = []
        for lot in tender.get("lots", []):
            if (
                lot["status"] != "active"
                or "shouldStartAfter" not in lot.get("auctionPeriod", {})
                or lot["auctionPeriod"]["shouldStartAfter"]
                < lot["auctionPeriod"].get("startDate", "")
            ):
                lots.append({})
                continue
            period = lot.get("auctionPeriod")
            shouldStartAfter = max(
                parse_date(period.get("shouldStartAfter"), TZ).astimezone(TZ), now
            )
            lot_id = lot["id"]
            planned = False
            while not planned:
                try:
                    auctionPeriod, stream, skip_days = await planning_auction(
                        tender, shouldStartAfter, quick, lot_id
                    )
                    planned = True
                except Exception as e:
                    planned = False
                    LOGGER.error(
                        "Error on planning tender '{}': {}".format(
                            tender.get("id", ""), repr(e)
                        )
                    )
            auctionPeriod = randomize(auctionPeriod).isoformat()
            planned = "replanned" if period.get("startDate") else "planned"
            lots.append({"auctionPeriod": {"startDate": auctionPeriod}})
            LOGGER.info(
                "{} auction for lot {} of tender {} to {}. Stream {}.{}".format(
                    planned.title(),
                    lot_id,
                    tender["id"],
                    auctionPeriod,
                    stream,
                    skipped_days(skip_days),
                ),
            )
        if any(lots):
            return {"lots": lots}
    return {}


async def process_listing(server_id_cookie, tender):
    run_date = get_now()
    # TODO: Добавить условие когда нужно проверять аукцион, а когда нет
    await check_auction(tender)
    tid = tender.get("id")
    next_check = tender.get("next_check")

    if next_check:
        check_args = dict(
            timezone=TZ,
            id=f"recheck_{tid}",
            name=f"Recheck {tid}",
            misfire_grace_time=60 * 60,
            replace_existing=True,
            args=[CHRONOGRAPH_HOST + "/recheck/" + tid, None, server_id_cookie],
        )
        next_check = parse_date(next_check, TZ).astimezone(TZ)
        recheck_job = scheduler.get_job(f"recheck_{tid}")
        if next_check < run_date:
            scheduler.add_job(
                push,
                "date",
                run_date=run_date + timedelta(seconds=randint(SMOOTHING_MIN, SMOOTHING_MAX)),
                **check_args,
            )
        elif not recheck_job or recheck_job.next_run_time != next_check:
            scheduler.add_job(
                push,
                "date",
                run_date=next_check + timedelta(seconds=randint(SMOOTHING_MIN, SMOOTHING_MAX)),
                **check_args,
            )
    if any(
        [
            "shouldStartAfter" in i.get("auctionPeriod", {})
            and parse_date(i["auctionPeriod"]["shouldStartAfter"], TZ).astimezone(TZ)
            > parse_date(i["auctionPeriod"].get("startDate", "0001"), TZ)
            for i in tender.get("lots", [])
        ]
    ) or (
        "shouldStartAfter" in tender.get("auctionPeriod", {})
        and parse_date(tender["auctionPeriod"]["shouldStartAfter"], TZ).astimezone(TZ)
        > parse_date(tender["auctionPeriod"].get("startDate", "0001"), TZ)
    ):
        resync_job = scheduler.get_job(f"resync_{tid}")
        if not resync_job or resync_job.next_run_time > run_date + timedelta(minutes=1):
            scheduler.add_job(
                push,
                "date",
                run_date=run_date + timedelta(seconds=randint(SMOOTHING_MIN, SMOOTHING_MAX)),
                id=f"resync_{tid}",
                name=f"Resync {tid}",
                misfire_grace_time=60 * 60,
                args=[CHRONOGRAPH_HOST + "/resync/" + tid, None, server_id_cookie],
                replace_existing=True,
            )
    await asyncio.sleep(1)


async def recheck_tender(tender_id):
    url = PUBLIC_API_HOST + "/api/2.5/tenders/" + tender_id
    next_check = None
    recheck_url = CHRONOGRAPH_HOST + "/recheck/" + tender_id
    await SESSION.options(url)
    response = await SESSION.patch(
        url,
        json={"data": {"id": tender_id}},
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_TOKEN}",
        },
    )
    data = await response.text()

    if response.status == 429:
        # TODO: Исправить, ситуацию, когда при рестарте apscheduler запускает все джобы сразу
        #  и сервер отвечает too many requests
        LOGGER.error(
            "Error too mant requests {} on getting tender '{}': {}".format(
                response.status, url, data
            ),
        )
    elif response.status != 200:
        LOGGER.error(
            "Error {} on checking tender '{}': {}".format(response.status, url, data)
        )
        if response.status not in (403, 404, 410):
            next_check = get_now() + timedelta(minutes=1)
    elif response.status == 200:
        data = json.loads(data)
        if data["data"].get("next_check"):
            next_check = parse_date(data["data"]["next_check"], TZ).astimezone(TZ)

    if next_check:
        check_args = dict(
            timezone=TZ,
            id=f"recheck_{tender_id}",
            name=f"Recheck {tender_id}",
            misfire_grace_time=60 * 60,
            replace_existing=True,
            args=[recheck_url, None],
        )
        if next_check < get_now():
            scheduler.add_job(
                push,
                "date",
                run_date=get_now() + timedelta(seconds=randint(SMOOTHING_MIN, SMOOTHING_MAX)),
                **check_args,
            )
        else:
            scheduler.add_job(
                push,
                "date",
                run_date=next_check + timedelta(seconds=randint(SMOOTHING_MIN, SMOOTHING_MAX)),
                **check_args,
            )
    return next_check and next_check.isoformat()


async def resync_tender(tender_id):
    url = PUBLIC_API_HOST + "/api/2.5/tenders/" + tender_id
    next_check = None
    recheck_url = CHRONOGRAPH_HOST + "/recheck/" + tender_id
    resync_url = CHRONOGRAPH_HOST + "/resync/" + tender_id
    next_check = None
    next_sync = None

    await SESSION.options(url)
    response = await SESSION.get(
        url,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {API_TOKEN}",
        },
    )
    data = await response.text()

    if response.status == 429:
        # TODO: Исправить, ситуацию, когда при рестарте apscheduler запускает все джобы сразу
        #  и сервер отвечает too many requests
        LOGGER.error(
            "Error too mant requests {} on getting tender '{}': {}".format(
                response.status, url, data
            ),
        )
    elif response.status != 200:
        LOGGER.error(
            "Error {} on getting tender '{}': {}".format(response.status, url, data),
        )
        if response.status in (404, 410):
            return
        next_sync = get_now() + timedelta(
            seconds=randint(SMOOTHING_REMIN, SMOOTHING_MAX)
        )
    else:
        data = json.loads(data)
        tender = data["data"]
        changes = await check_tender(tender)
        if changes:
            await SESSION.options(url)
            response = await SESSION.patch(
                url,
                json={"data": changes},
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {API_TOKEN}",
                },
            )
            data = await response.text()

            if response.status == 429:
                # TODO: Исправить, ситуацию, когда при рестарте apscheduler запускает все джобы сразу
                #  и сервер отвечает too many requests
                LOGGER.error(
                    "Error too mant requests {} on getting tender '{}': {}".format(
                        response.status, url, data
                    ),
                )
            elif response.status != 200:
                LOGGER.error(
                    "Error {} on updating tender '{}' with '{}': {}".format(
                        response.status, url, {"data": changes}, data
                    ),
                )
                next_sync = get_now() + timedelta(
                    seconds=randint(SMOOTHING_REMIN, SMOOTHING_MAX)
                )
            else:
                data = json.loads(data)
                if data and data["data"].get("next_check"):
                    next_check = parse_date(data["data"]["next_check"], TZ).astimezone(
                        TZ
                    )
    if next_check:
        check_args = dict(
            timezone=TZ,
            id=f"recheck_{tender_id}",
            name=f"Recheck {tender_id}",
            misfire_grace_time=60 * 60,
            replace_existing=True,
            args=[recheck_url, None],
        )
        if next_check < get_now():
            scheduler.add_job(
                push,
                "date",
                run_date=get_now() + timedelta(seconds=randint(SMOOTHING_MIN, SMOOTHING_MAX)),
                **check_args,
            )
        else:
            scheduler.add_job(
                push,
                "date",
                run_date=next_check + timedelta(seconds=randint(SMOOTHING_MIN, SMOOTHING_MAX)),
                **check_args,
            )
    if next_sync:
        scheduler.add_job(
            push,
            "date",
            run_date=next_sync + timedelta(seconds=randint(SMOOTHING_MIN, SMOOTHING_MAX)),
            timezone=TZ,
            id=tender_id,
            name=f"Resync {tender_id}",
            misfire_grace_time=60 * 60,
            replace_existing=True,
            args=[resync_url, None],
        )
    return next_sync and next_sync.isoformat()
