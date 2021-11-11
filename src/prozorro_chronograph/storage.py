from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorCollection
from datetime import timedelta, datetime, time
import standards
from typing import Tuple

from prozorro_chronograph.settings import (
    MONGODB_PLANS_COLLECTION,
    MONGODB_CONFIG_COLLECTION,
    MONGODB_DATABASE,
    MONGODB_URL,
    WORKING_DAY_START,
    TZ,
    STREAMS,
    LOGGER,
)
from prozorro_chronograph.utils import parse_date

DB_CONNECTION = None


def get_mongodb_collection(collection_name: str = MONGODB_PLANS_COLLECTION) -> AsyncIOMotorCollection:
    global DB_CONNECTION
    DB_CONNECTION = DB_CONNECTION or AsyncIOMotorClient(MONGODB_URL)
    db = getattr(DB_CONNECTION, MONGODB_DATABASE)
    collection = getattr(db, collection_name)
    return collection


async def init_plans_collection() -> None:
    global DB_CONNECTION
    DB_CONNECTION = DB_CONNECTION or AsyncIOMotorClient(MONGODB_URL)
    db = getattr(DB_CONNECTION, MONGODB_DATABASE)
    db.plans.update_one({"_id": "init"}, {"$set": {"_id": "init"}}, upsert=True)


async def init_database() -> None:
    working_days = {}
    streams = STREAMS
    collection = get_mongodb_collection(MONGODB_CONFIG_COLLECTION)

    holidays = standards.load("calendars/workdays_off.json")
    for date_str in holidays:
        working_days[date_str] = True

    existing_doc = await collection.find_one({"_id": "config"})
    if existing_doc is not None:
        working_days = {**existing_doc["working_days"], **working_days}
        streams = existing_doc["streams"]
    await collection.update_one(
        {"_id": "config"},
        {"$set": {"working_days": working_days, "streams": streams}},
        upsert=True,
    )


async def get_calendar() -> dict:
    collection = get_mongodb_collection(MONGODB_CONFIG_COLLECTION)
    calendar = await collection.find_one({"_id": "config"})
    return calendar["working_days"]


async def set_holiday(day: str) -> None:
    collection = get_mongodb_collection(MONGODB_CONFIG_COLLECTION)
    key = parse_date(day).date().isoformat()
    await collection.update_one(
        {"_id": "config"}, {"$set": {f"working_days.{key}": True}}, upsert=True
    )


async def delete_holiday(day: str) -> None:
    collection = get_mongodb_collection(MONGODB_CONFIG_COLLECTION)
    key = parse_date(day).date().isoformat()
    await collection.update_one(
        {"_id": "config"}, {"$unset": {f"working_days.{key}": ""}}
    )


async def get_streams() -> int:
    collection = get_mongodb_collection(MONGODB_CONFIG_COLLECTION)
    config = await collection.find_one({"_id": "config"}, {"streams": 1})
    if not config or not config.get("streams", None):
        config = {"streams": 10}
    return config["streams"]


async def get_date(mode: str, date: datetime) -> Tuple[time, int, dict]:
    plan_id = f"plan{mode}_{date.isoformat()}"
    collection = get_mongodb_collection(MONGODB_PLANS_COLLECTION)
    plan = await collection.find_one({"_id": plan_id})
    if plan is None:
        plan = {"_id": plan_id}
    plan_date_end = plan.get("time", WORKING_DAY_START.isoformat())
    plan_date = parse_date(date.isoformat() + "T" + plan_date_end, None)
    plan_date = plan_date.astimezone(TZ) if plan_date.tzinfo else TZ.localize(plan_date)
    return plan_date.time(), plan.get("streams_count", 1), plan


async def set_date(
        plan_id: str,
        end_time: time,
        stream_id: int,
        tender_id: str,
        lot_id: str,
        start_time: time,
        new_slot: bool = True) -> None:
    collection = get_mongodb_collection(MONGODB_PLANS_COLLECTION)

    if new_slot:
        time = end_time.isoformat()
        await collection.update_one(
            {"_id": plan_id},
            {"$set": {"time": time, "streams_count": stream_id}},
            upsert=True,
        )
    streams = await collection.find_one(
        {"_id": plan_id, "streams.stream_id": stream_id}
    )
    default_slot = {
        "tender_id": tender_id,
        "lot_id": lot_id,
        "time": start_time.isoformat(),
    }
    if streams is None:
        new_stream = {"stream_id": stream_id, "slots": [default_slot]}
        await collection.update_one(
            {"_id": plan_id}, {"$push": {"streams": new_stream}}
        )
    else:
        LOGGER.info(f"Finding slot for {tender_id}")
        for num, stream in enumerate(streams["streams"]):
            if stream["stream_id"] == stream_id:
                modified = False
                LOGGER.info(f"Finding slot for {tender_id} in {stream['slots']}")
                for slot in stream["slots"]:
                    if slot["time"] == start_time.isoformat():
                        slot["tender_id"] = tender_id
                        slot["lot_id"] = lot_id
                        modified = True
                        LOGGER.info(f"Slot was found {slot} for tender: {tender_id}")
                        break
                if not modified:
                    LOGGER.info(f"Slot was not found for tender: {tender_id} setting default {default_slot}")
                    stream["slots"].append(default_slot)
                break
        LOGGER.info(f"Setting tender {tender_id} in stream {stream_id}, with value {stream}")
        await collection.update_one(
            {"_id": plan_id, "streams.stream_id": stream_id},
            {"$set": {f"streams.$": stream}},
        )


def find_free_slot(plan: dict) -> Tuple[datetime, int]:
    streams_count = plan.get("streams_count", 0)
    for stream_id in range(streams_count):
        streams = plan.get("streams", [])
        if not streams:
            LOGGER.info(f"Plan {plan['_id']} have no streams")
            break
        for slot in streams[stream_id].get("slots", []):
            LOGGER.info(f"Checking slot {slot}")
            if slot["tender_id"] is None:
                plan_date = parse_date(
                    plan["_id"].split("_")[1] + "T" + slot["time"], None
                )
                plan_date = (
                    plan_date.astimezone(TZ)
                    if plan_date.tzinfo
                    else TZ.localize(plan_date)
                )
                current_stream = plan["streams"][stream_id]["stream_id"]
                return plan_date, current_stream
    LOGGER.info(f"Slot was not found")


def check_slot_to_be_free(lot_id: str, auction_time: datetime, lots: dict, plan_time: datetime) -> bool:
    if not lot_id and (
        not auction_time
        or not plan_time < auction_time < plan_time + timedelta(minutes=30)
    ):
        return True
    elif lot_id and (
        not lots.get(lot_id)
        or lots.get(lot_id)
        and not plan_time < lots.get(lot_id) < plan_time + timedelta(minutes=30)
    ):
        return True
    return False


async def free_slots(tender_id: str, auction_time: datetime, lots: dict) -> None:
    collection = get_mongodb_collection(MONGODB_PLANS_COLLECTION)

    async for doc in collection.aggregate(
        [
            {"$match": {"streams.slots.tender_id": tender_id}},
            {"$unwind": "$streams"},
            {"$match": {"streams.slots.tender_id": tender_id}},
            {"$project": {"streams": 1}},
        ],
    ):
        streams = doc["streams"]
        plan_id = doc["_id"]
        stream_id = streams["stream_id"]
        for slot in streams["slots"]:
            if slot["tender_id"] is not None and slot["tender_id"].startswith(tender_id):
                plan_time = doc["_id"].split("_")[1] + "T" + slot["time"]
                plan_time = TZ.localize(parse_date(plan_time, None))
                if check_slot_to_be_free(
                    lot_id=slot["lot_id"],
                    auction_time=auction_time,
                    lots=lots,
                    plan_time=plan_time,
                ):
                    slot["tender_id"] = None
                    slot["lot_id"] = None
        await collection.update_one(
            {"_id": plan_id, "streams.stream_id": stream_id},
            {"$set": {"streams.$.slots": streams["slots"]}},
        )
