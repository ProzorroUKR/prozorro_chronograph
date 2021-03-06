from datetime import datetime, timedelta
from random import randint
from ciso8601 import parse_datetime
from pytz import timezone, utc
from typing import Optional

from prozorro_chronograph.settings import (
    TZ,
    BIDDER_TIME,
    SERVICE_TIME,
    MIN_PAUSE,
    ROUNDING,
    WORKING_DAY_START,
)


def get_now() -> datetime:
    return datetime.now(TZ)


def randomize(dt: datetime) -> datetime:
    return dt + timedelta(seconds=randint(0, 1799))


def calc_auction_end_time(bids: int, start: datetime) -> datetime:
    end = start + bids * BIDDER_TIME + SERVICE_TIME + MIN_PAUSE
    seconds = (end - TZ.localize(datetime.combine(end, WORKING_DAY_START))).seconds
    roundTo = ROUNDING.seconds
    rounding = (seconds + roundTo - 1) // roundTo * roundTo
    return (end + timedelta(0, rounding - seconds, -end.microsecond)).astimezone(TZ)


def skipped_days(days: int) -> str:
    days_str = ""
    if days:
        days_str = f" Skipped {days} full days."
    return days_str


def parse_date(value: str, default_timezone: Optional[timezone] = utc) -> datetime:
    date = parse_datetime(value)
    if not date.tzinfo and default_timezone is not None:
        date = default_timezone.localize(date)
    return date
