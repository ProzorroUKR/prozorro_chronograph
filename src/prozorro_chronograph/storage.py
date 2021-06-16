from motor.motor_asyncio import AsyncIOMotorClient
from datetime import timedelta
import standards

from prozorro_chronograph.settings import (
    MONGODB_PLANS_COLLECTION,
    MONGODB_CONFIG_COLLECTION,
    MONGODB_DATABASE,
    MONGODB_URL,
    WORKING_DAY_START,
    TZ,
)
from prozorro_chronograph.utils import parse_date

DB_CONNECTION = None


def get_mongodb_collection(collection_name=MONGODB_PLANS_COLLECTION):
    global DB_CONNECTION
    DB_CONNECTION = DB_CONNECTION or AsyncIOMotorClient(MONGODB_URL)
    db = getattr(DB_CONNECTION, MONGODB_DATABASE)
    collection = getattr(db, collection_name)
    return collection


async def init_plans_collection():
    global DB_CONNECTION
    DB_CONNECTION = DB_CONNECTION or AsyncIOMotorClient(MONGODB_URL)
    db = getattr(DB_CONNECTION, MONGODB_DATABASE)
    db.plans.update_one({"_id": "init"}, {"$set": {"_id": "init"}}, upsert=True)


async def init_database():
    working_days = {}
    streams = 300
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


async def get_calendar():
    collection = get_mongodb_collection(MONGODB_CONFIG_COLLECTION)
    calendar = await collection.find_one({"_id": "config"})
    return calendar["working_days"]


async def set_holiday(day):
    collection = get_mongodb_collection(MONGODB_CONFIG_COLLECTION)
    key = parse_date(day).date().isoformat()
    await collection.update_one(
        {"_id": "config"}, {"$set": {f"working_days.{key}": True}}, upsert=True
    )


async def delete_holiday(day):
    collection = get_mongodb_collection(MONGODB_CONFIG_COLLECTION)
    key = parse_date(day).date().isoformat()
    await collection.update_one(
        {"_id": "config"}, {"$unset": {f"working_days.{key}": ""}}
    )


async def get_streams():
    collection = get_mongodb_collection(MONGODB_CONFIG_COLLECTION)
    config = await collection.find_one({"_id": "config"}, {"streams": 1})
    if not config or not config.get("streams", None):
        config = {"streams": 10}
    return config["streams"]


async def get_date(mode, date):
    plan_id = f"plan{mode}_{date.isoformat()}"
    collection = get_mongodb_collection(MONGODB_PLANS_COLLECTION)
    plan = await collection.find_one({"_id": plan_id})
    if plan is None:
        plan = {"_id": plan_id}
    plan_date_end = plan.get("time", WORKING_DAY_START.isoformat())
    plan_date = parse_date(date.isoformat() + "T" + plan_date_end, None)
    plan_date = plan_date.astimezone(TZ) if plan_date.tzinfo else TZ.localize(plan_date)
    return plan_date.time(), plan.get("streams_count", 1), plan


async def set_date(plan_id, end_time, stream_id, tender_id, lot_id, start_time, new_slot=True):
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
        for num, stream in enumerate(streams["streams"]):
            if stream["stream_id"] == stream_id:
                modified = False
                for slot in stream["slots"]:
                    if slot["time"] == start_time.isoformat():
                        slot["tender_id"] = tender_id
                        slot["lot_id"] = lot_id
                        modified = True
                        break
                if not modified:
                    stream["slots"].append(default_slot)
                break
        await collection.update_one(
            {"_id": plan_id, "streams.stream_id": stream_id},
            {"$set": {f"streams.$": stream}},
        )


def find_free_slot(plan: dict):
    streams_count = plan.get("streams_count", 0)
    for stream_id in range(streams_count):
        streams = plan.get("streams", [])
        if not streams:
            break
        for slot in streams[stream_id].get("slots", []):
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


def check_slot_to_be_free(lot_id, auction_time, lots, plan_time):
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


async def free_slots(tender_id, auction_time, lots):
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
