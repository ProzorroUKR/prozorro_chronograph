from copy import deepcopy
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from aiohttp.client import ClientSession

from prozorro_chronograph.scheduler import recheck_tender, resync_tender
from prozorro_chronograph.settings import TZ
from .api_data import test_lots, test_bids, test_tender_data
from .base import BaseTenderTest, PUBLIC_API_HOST, working_days

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


@patch("prozorro_chronograph.scheduler.get_streams", AsyncMock(return_value=10))
@patch("prozorro_chronograph.scheduler.get_calendar", AsyncMock(return_value=working_days))
class TestTender3(BaseTenderTest):
    initial_data = test_tender_data_quick
    initial_bids = test_bids

    async def test_switch_to_auction(self, tender_id, scheduler):
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                await recheck_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert data["data"]["status"] == "active.auction"

    async def test_reschedule_auction(self, tender_id, scheduler, db, couch):
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                await recheck_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert data["data"]["status"] == "active.auction"
        if self.initial_lots:
            assert "auctionPeriod" not in data["data"]
            assert "auctionPeriod" in data["data"]["lots"][0]
            assert "shouldStartAfter" in data["data"]["lots"][0]["auctionPeriod"]
            assert "startDate" not in data["data"]["lots"][0]["auctionPeriod"]
            assert data["data"]["lots"][0]["auctionPeriod"]["shouldStartAfter"] >= \
                   data["data"]["lots"][0]["auctionPeriod"].get("startDate", "")
        else:
            assert "auctionPeriod" in data["data"]
            assert "shouldStartAfter" in data["data"]["auctionPeriod"]
            assert "startDate" not in data["data"]["auctionPeriod"]
            assert data["data"]["auctionPeriod"]["shouldStartAfter"] >= \
                   data["data"]["auctionPeriod"].get("startDate", "")

        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(return_value=db.plans)):
                    await resync_tender(tender_id)

        data = couch.get(tender_id)
        if self.initial_lots:
            assert "auctionPeriod" in data["lots"][0]
            auctionPeriod = data["lots"][0]["auctionPeriod"]["startDate"]
            data["lots"][0]["auctionPeriod"]["startDate"] = (datetime.now(TZ) - timedelta(hours=1)).isoformat()
        else:
            assert "auctionPeriod" in data
            auctionPeriod = data["auctionPeriod"]["startDate"]
            data["auctionPeriod"]["startDate"] = (datetime.now(TZ) - timedelta(hours=1)).isoformat()
        couch.save(data)

        async with ClientSession(cookies=self.cookies) as session:
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert data["data"]["status"] == "active.auction"

        if self.initial_lots:
            assert "auctionPeriod" not in data["data"]
            assert "auctionPeriod" in data["data"]["lots"][0]
            assert "shouldStartAfter" in data["data"]["lots"][0]["auctionPeriod"]
            assert "startDate" in data["data"]["lots"][0]["auctionPeriod"]
            assert data["data"]["lots"][0]["auctionPeriod"]["shouldStartAfter"] >= \
                   data["data"]["lots"][0]["auctionPeriod"]["startDate"]
        else:
            assert "auctionPeriod" in data["data"]
            assert "shouldStartAfter" in data["data"]["auctionPeriod"]
            assert "startDate" in data["data"]["auctionPeriod"]
            assert data["data"]["auctionPeriod"]["shouldStartAfter"] >= \
                   data["data"]["auctionPeriod"]["startDate"]

        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(return_value=db.plans)):
                    await resync_tender(tender_id)
                resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert resp.status == 200
        if self.initial_lots:
            assert "auctionPeriod" in data["data"]["lots"][0]
            assert data["data"]["lots"][0]["auctionPeriod"]["startDate"] > auctionPeriod
        else:
            assert "auctionPeriod" in data["data"]
            assert data["data"]["auctionPeriod"]["startDate"] > auctionPeriod


class TestTenderLot3(TestTender3):
    initial_lots = test_lots


class TestTender4(TestTenderLot3):
    sandbox = True


class TestTenderLot4(TestTender4):
    initial_lots = test_lots
