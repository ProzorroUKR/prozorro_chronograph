from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock

from prozorro_chronograph.scheduler import planning_auction, free_slots
from prozorro_chronograph.settings import TZ
from .api_data import test_tender_data
from .base import BaseTest, working_days

test_tender_data_quick = deepcopy(test_tender_data)
test_tender_data_quick.update({
    "enquiryPeriod": {
        "startDate": (datetime.now(TZ) + timedelta(days=-15)).isoformat(),
        "endDate": (datetime.now(TZ) + timedelta(days=-9)).isoformat()
    },
    "tenderPeriod": {
        "startDate": (datetime.now(TZ) + timedelta(days=-9)).isoformat(),
        "endDate": datetime.now(TZ).isoformat()
    }
})
test_tender_data_test_quick = deepcopy(test_tender_data_quick)
test_tender_data_test_quick["mode"] = "test"


@patch("prozorro_chronograph.scheduler.get_streams", AsyncMock(return_value=10))
@patch("prozorro_chronograph.scheduler.get_calendar", AsyncMock(return_value=working_days))
class TestTenderPlanning(BaseTest):
    async def test_auction_quick_planning(self, db):
        now = datetime.now(TZ)
        with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(return_value=db.plans)):
            auctionPeriodstartDate, *_ = await planning_auction(test_tender_data_test_quick, now, quick=True)
        assert now < auctionPeriodstartDate < now + timedelta(hours=1)

    async def test_auction_planning_overflow(self, db):
        now = datetime.now(TZ)
        with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(return_value=db.plans)):
            res, *_ = await planning_auction(test_tender_data_test_quick, now)
            startDate = res.date()
            count = 0
            while startDate == res.date():
                count += 1
                res, *_ = await planning_auction(test_tender_data_test_quick, now)
        assert count == 100

    async def test_auction_planning_free(self, db):
        await db.plans.delete_many({})

        now = datetime.now(TZ)
        with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(return_value=db.plans)):
            startDateTime, *_ = await planning_auction(test_tender_data_test_quick, now)
            await free_slots("", startDateTime, {})
            res, *_ = await planning_auction(test_tender_data_test_quick, now)
        assert res == startDateTime

    async def test_auction_planning_buffer(self, db):
        some_date = datetime(2015, 9, 21, 6, 30)
        date = some_date.date()
        ndate = (some_date + timedelta(days=1)).date()
        with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(return_value=db.plans)):
            res, *_ = await planning_auction(test_tender_data_test_quick, some_date)
            assert res.date() == date
            some_date = some_date.replace(hour=10)
            res, *_ = await planning_auction(test_tender_data_test_quick, some_date)
            assert res.date() != date
            assert res.date() == ndate
            some_date = some_date.replace(hour=16)
            res, *_ = await planning_auction(test_tender_data_test_quick, some_date)
            assert res.date() != date
            assert res.date() == ndate
