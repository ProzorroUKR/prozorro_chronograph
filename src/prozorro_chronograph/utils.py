# TODO: добавить parse_date() и ciso8601

from datetime import datetime, timedelta
from random import randint

from prozorro_chronograph.settings import (
    TZ,
    BIDDER_TIME,
    SERVICE_TIME,
    MIN_PAUSE,
    ROUNDING,
    WORKING_DAY_START,
)


def get_now():
    return datetime.now(TZ)


def randomize(dt):
    return dt + timedelta(seconds=randint(0, 1799))


def calc_auction_end_time(bids, start):
    end = start + bids * BIDDER_TIME + SERVICE_TIME + MIN_PAUSE
    seconds = (end - TZ.localize(datetime.combine(end, WORKING_DAY_START))).seconds
    roundTo = ROUNDING.seconds
    rounding = (seconds + roundTo - 1) // roundTo * roundTo
    return (end + timedelta(0, rounding - seconds, -end.microsecond)).astimezone(TZ)


def skipped_days(days):
    days_str = ""
    if days:
        days_str = f" Skipped {days} full days."
    return days_str
