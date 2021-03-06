import json
import asyncio
from aiohttp import ClientSession
from random import randint
from datetime import datetime, timedelta
from typing import Tuple
from prozorro_crawler.settings import CRAWLER_USER_AGENT

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
    BASE_URL,
    URL_SUFFIX,
    API_TOKEN,
    SANDBOX_MODE,
    WORKING_DAY_START,
    WORKING_DAY_END,
    LOGGER,
    scheduler,
    SMOOTHING_MIN,
    SMOOTHING_MAX,
    SMOOTHING_REMIN,
    INVALID_STATUSES,
)
from prozorro_chronograph.utils import (
    get_now,
    randomize,
    calc_auction_end_time,
    skipped_days,
    parse_date,
)

SESSION = ClientSession(
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {API_TOKEN}",
        "User-Agent": CRAWLER_USER_AGENT
    }
)


class RetryError(Exception):
    pass


async def push(mode: str, tender_id: str, server_id: str = None) -> None:
    tx = ty = 1
    while True:
        try:
            if mode == "recheck":
                await recheck_tender(tender_id)
            elif mode == "resync":
                await resync_tender(tender_id)
            else:
                LOGGER.error(f"Unexpected mode {mode}")
                break
        except RetryError:
            pass
        except Exception as e:
            LOGGER.error(f"Error on {mode} tender {tender_id}: {repr(e)}")
        else:
            break
        await asyncio.sleep(tx)
        tx, ty = ty, tx + ty


async def planning_auction(
        tender: dict,
        start: datetime,
        quick: bool = False,
        lot_id: str = None) -> Tuple[datetime, int, int]:
    tender_id = tender.get("id", "")
    mode = tender.get("mode", "")
    calendar = await get_calendar()
    streams = await get_streams()
    skipped_days = 0
    if quick:
        quick_start = calc_auction_end_time(0, start)
        return quick_start, 0, skipped_days
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
        LOGGER.info(f"Finding free slot for {tender_id}. "
                    f"Number of streams in plan {stream}. "
                    f"Max streams: {streams}. "
                    f"Plan got streams: {plan.get('streams_count', None)}. "
                    f"Day of start is: {dayStart}")
        freeSlot = find_free_slot(plan)
        LOGGER.info(f"Free slot was found for tender {tender_id}, slot: {freeSlot}")
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
    LOGGER.info(f"Setting date for {tender_id} in {plan['_id']}. In {stream} stream.")
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


async def check_auction(tender: dict) -> None:
    auction_time = tender.get("auctionPeriod", {}).get("startDate") and parse_date(
        tender.get("auctionPeriod", {}).get("startDate")
    )
    try:
        lots = dict(
            [
                (i["id"], parse_date(i.get("auctionPeriod", {}).get("startDate")))
                for i in tender.get("lots", [])
                if i.get("auctionPeriod", {}).get("startDate")
            ]
        )
    except Exception as e:
        LOGGER.error(
            "Error on checking tender auctionPeriod '{}': {}".format(
                tender.get("id", ""), repr(e)
            )
        )
        return

    await free_slots(tender["id"], auction_time, lots)


async def check_tender(tender: dict) -> dict:
    if tender.get("status", None) in INVALID_STATUSES:
        return {}

    now = get_now()
    quick = SANDBOX_MODE and "quick" in tender.get("submissionMethodDetails", "")
    LOGGER.info(f"Checking tender`s {tender['id']} auctionPeriod: {tender.get('auctionPeriod', {})}")
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


async def schedule_next_check(tender_id, next_check):
    LOGGER.info(f"Start processing tender: {tender_id}")
    job_id = f"recheck_{tender_id}"
    now = get_now()
    next_check = parse_date(next_check, TZ).astimezone(TZ)
    run_date = now if now > next_check else next_check
    scheduler.add_job(
        push,
        "date",
        timezone=TZ,
        id=job_id,
        name=f"Recheck {tender_id}",
        run_date=run_date + timedelta(seconds=randint(SMOOTHING_MIN, SMOOTHING_MAX)),
        misfire_grace_time=60 * 60,
        replace_existing=True,
        args=["recheck", tender_id],
    )


async def schedule_auction_planner(tender_id):
    run_date = get_now() + timedelta(seconds=randint(SMOOTHING_MIN, SMOOTHING_MAX))
    scheduler.add_job(
        push,
        "date",
        run_date=run_date,
        id=f"resync_{tender_id}",
        name=f"Resync {tender_id}",
        misfire_grace_time=60 * 60,
        args=["resync", tender_id],
        replace_existing=True,
    )
    LOGGER.info(f"Set resync job for tender {tender_id} at {run_date.isoformat()}")


async def process_listing(server_id_cookie: str, tender: dict) -> None:
    LOGGER.info(f"Start processing tender: {tender['id']}")
    run_date = get_now()
    await check_auction(tender)
    tid = tender.get("id")
    next_check = tender.get("next_check")

    if next_check:
        # moves to `schedule_next_check`
        check_args = dict(
            timezone=TZ,
            id=f"recheck_{tid}",
            name=f"Recheck {tid}",
            misfire_grace_time=60 * 60,
            replace_existing=True,
            args=["recheck", tid, server_id_cookie],
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
            > parse_date(i["auctionPeriod"].get("startDate", "0001-01-03"), TZ)
            for i in tender.get("lots", [])
        ]
    ) or (
        "shouldStartAfter" in tender.get("auctionPeriod", {})
        and parse_date(tender["auctionPeriod"]["shouldStartAfter"], TZ).astimezone(TZ)
        > parse_date(tender["auctionPeriod"].get("startDate", "0001-01-03"), TZ)
    ):
        # moves to `schedule_auction_planner`
        resync_job = scheduler.get_job(f"resync_{tid}")
        if not resync_job or resync_job.next_run_time > run_date + timedelta(minutes=1):
            scheduler.add_job(
                push,
                "date",
                run_date=run_date + timedelta(seconds=randint(SMOOTHING_MIN, SMOOTHING_MAX)),
                id=f"resync_{tid}",
                name=f"Resync {tid}",
                misfire_grace_time=60 * 60,
                args=["resync", tid, server_id_cookie],
                replace_existing=True,
            )
            LOGGER.info(f"Set resync job for tender {tid}")
        else:
            LOGGER.info(f"Resync job for tender {tid} already exists, don't set new")
    else:
        LOGGER.info(f"Tender {tid} don't need to resync")
    await asyncio.sleep(1)


async def recheck_tender(tender_id: str) -> datetime:
    url = f"{BASE_URL}/{tender_id}{URL_SUFFIX}"
    next_check = None
    response = await SESSION.patch(
        url,
        json={"data": {"id": tender_id}},
    )
    data = await response.text()

    if response.status == 429:
        LOGGER.error(f"Error too many requests {response.status} on getting tender '{url}'")
        next_check = get_now() + timedelta(minutes=1)
    elif response.status != 200:
        LOGGER.error("Error {} on checking tender '{}': {}".format(response.status, url, data))
        if response.status == 422:
            next_check = get_now() + timedelta(minutes=1)
            response = await SESSION.get(url)
            data = await response.text()
            if response.status == 200:
                data = json.loads(data)
                if data["data"]["status"] in INVALID_STATUSES:
                    status = data["data"]["status"]
                    tender_id = data["data"]["id"]
                    LOGGER.info(f"Next check won't be set for tender {tender_id} with status {status}")
                    next_check = None
        elif response.status not in (403, 404, 410):
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
            args=["recheck", tender_id],
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


async def resync_tender(tender_id: str):
    LOGGER.info(f"Start resyncing tender {tender_id}")
    url = f"{BASE_URL}/{tender_id}{URL_SUFFIX}"
    next_check = None
    next_sync = None

    response = await SESSION.get(url)
    data = await response.text()

    if response.status == 429:
        LOGGER.error(
            "Error too many requests {} on getting tender '{}': {}".format(
                response.status, url, data
            ),
        )
        next_sync = get_now() + timedelta(
            seconds=randint(SMOOTHING_REMIN, SMOOTHING_MAX)
        )
    elif response.status != 200:
        LOGGER.error(
            "Error {} on getting tender '{}': {}".format(response.status, url, data),
        )
        if response.status in (404, 410):
            return
        elif response.status == 412:
            raise RetryError()
        next_sync = get_now() + timedelta(
            seconds=randint(SMOOTHING_REMIN, SMOOTHING_MAX)
        )
    else:
        data = json.loads(data)
        tender = data["data"]
        changes = await check_tender(tender)
        LOGGER.info(f"Changes to patch for tender {tender['id']}: {changes}")
        if changes:
            response = await SESSION.patch(
                url,
                json={"data": changes},
            )
            data = await response.text()

            if response.status == 429:
                LOGGER.error(
                    "Error too many requests {} on getting tender '{}': {}".format(
                        response.status, url, data
                    ),
                )
                next_sync = get_now() + timedelta(
                    seconds=randint(SMOOTHING_REMIN, SMOOTHING_MAX)
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
            args=["recheck", tender_id],
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
            id=f"resync_{tender_id}",
            name=f"Resync {tender_id}",
            misfire_grace_time=60 * 60,
            replace_existing=True,
            args=["resync", tender_id],
        )
    return next_sync and next_sync.isoformat()
