import asyncio
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock
from aiohttp.client import ClientSession
from iso8601 import parse_date

from prozorro_chronograph.scheduler import recheck_tender, resync_tender, process_listing
from prozorro_chronograph.settings import TZ
from prozorro_chronograph.storage import set_holiday, delete_holiday, get_calendar
from .api_data import test_lots
from .base import BaseTenderTest, PUBLIC_API_HOST


class TestClass(BaseTenderTest):
    async def test_wait_for_enquiryPeriod(self, tender_id, scheduler):
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                await recheck_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert resp.status == 200
        assert data["data"]["status"] == "active.enquiries"

    async def test_switch_to_tendering_enquiryPeriod(self, tender_id, scheduler):
        now = datetime.now(TZ)
        update_data = {
            "enquiryPeriod": {
                "startDate": (now + timedelta(days=-15)).isoformat(),
                "endDate": (now + timedelta(days=-9)).isoformat()
            },
            "tenderPeriod": {
                "startDate": (now + timedelta(days=-9)).isoformat(),
                "endDate": (now + timedelta(days=5)).isoformat(),
            }
        }
        await self.config_tender(tender_id, update_data)
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                await recheck_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()

        assert data["data"]["status"] == "active.tendering"

    async def test_switch_to_tendering_tenderPeriod(self, tender_id, scheduler):
        now = datetime.now(TZ)
        update_tender = {
            "enquiryPeriod": {
                "startDate": (now + timedelta(days=-15)).isoformat(),
                "endDate": (now + timedelta(days=-9)).isoformat()
            },
            "tenderPeriod": {
                "startDate": (now + timedelta(days=-9)).isoformat(),
                "endDate": now.isoformat()
            }
        }
        await self.config_tender(tender_id, update_tender)

        for _ in range(100):
            async with ClientSession(cookies=self.cookies) as session:
                with patch("prozorro_chronograph.scheduler.SESSION", session):
                    await recheck_tender(tender_id)
                resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
                data = await resp.json()

            if data["data"]["status"] == "active.tendering":
                break
            await asyncio.sleep(0.1)
        assert data["data"]["status"] == "active.tendering"

    async def test_wait_for_tenderPeriod(self, tender_id, scheduler):
        now = datetime.now(TZ)
        update_data = {
            "enquiryPeriod": {
                "startDate": (now + timedelta(days=-15)).isoformat(),
                "endDate": (now + timedelta(days=6)).isoformat()
            },
            "tenderPeriod": {
                "startDate": (now + timedelta(days=6)).isoformat(),
                "endDate": (now + timedelta(days=15)).isoformat()
            }
        }
        await self.config_tender(tender_id, update_data)
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                await recheck_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()

        assert data["data"]["status"] == "active.enquiries"

    async def test_set_auctionPeriod_jobs(self, tender_id, scheduler, db):
        now = datetime.now(TZ)
        update_data = {
            "enquiryPeriod": {
                "startDate": (now + timedelta(days=-15)).isoformat(),
                "endDate": (now + timedelta(days=-9)).isoformat()
            },
            "tenderPeriod": {
                "startDate": (now + timedelta(days=-9)).isoformat(),
                "endDate": (now + timedelta(days=1)).isoformat()
            }
        }
        await self.config_tender(tender_id, update_data)
        async with ClientSession(cookies=self.cookies) as session:
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()

        with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(return_value=db.plans)):
            await process_listing(None, data["data"])
        job = scheduler.get_job(f"recheck_{tender_id}")
        assert job is not None

        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                await recheck_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()

        with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(return_value=db.plans)):
            await process_listing(None, data["data"])
        async with ClientSession(cookies=self.cookies) as session:
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert resp.status == 200
        assert data["data"]["status"] == "active.tendering"

        if self.initial_lots:
            assert "auctionPeriod" in data["data"]["lots"][0]
        else:
            assert "auctionPeriod" in data["data"]

        side_effects = [db.config, db.config, db.plans, db.plans]
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(side_effect=side_effects)):
                    await resync_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert resp.status == 200
        assert data["data"]["status"] == "active.tendering"
        if data["data"].get("lots", None) is not None:
            assert "auctionPeriod" in data["data"]["lots"][0]
        else:
            assert "auctionPeriod" in data["data"]

    async def test_set_auctionPeriod_nextday(self, tender_id, db, scheduler):
        now = datetime.now(TZ)
        update_data = {
            "enquiryPeriod": {
                "startDate": (now + timedelta(days=-15)).isoformat(),
                "endDate": (now + timedelta(days=-9)).isoformat()
            },
            "tenderPeriod": {
                "startDate": now.isoformat(),
                "endDate": (now + timedelta(days=14 - now.weekday())).replace(hour=13).isoformat()
            }
        }
        await self.config_tender(tender_id, update_data)
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                await recheck_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()

        assert data["data"]["status"] == "active.tendering"

        side_effects = [db.config, db.config, db.plans, db.plans]
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(side_effect=side_effects)):
                    await resync_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert data["data"]["status"] == "active.tendering"
        if data["data"].get("lots", None) is not None:
            assert "auctionPeriod" in data["data"]["lots"][0]
            assert parse_date(data["data"]["lots"][0]["auctionPeriod"]["startDate"], TZ).weekday() == 1
        else:
            assert "auctionPeriod" in data["data"]
            assert parse_date(data["data"]["auctionPeriod"]["startDate"], TZ).weekday() == 1

        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                await recheck_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        job = scheduler.get_job(f"recheck_{tender_id}")
        assert job is not None
        assert parse_date(job.next_run_time.isoformat(), TZ).utctimetuple() >= \
               parse_date(data["data"]["tenderPeriod"]["endDate"]).utctimetuple()
        assert parse_date(job.next_run_time.isoformat(), TZ).utctimetuple() <= \
               (parse_date(data["data"]["tenderPeriod"]["endDate"]) + timedelta(minutes=5)).utctimetuple()

    async def test_set_auctionPeriod_skip_weekend(self, tender_id, db, scheduler):
        now = datetime.now(TZ)
        update_data = {
            "enquiryPeriod": {
                "startDate": (now + timedelta(days=-15)).isoformat(),
                "endDate": (now + timedelta(days=-9)).isoformat()
            },
            "tenderPeriod": {
                "startDate": now.isoformat(),
                "endDate": (now + timedelta(days=13 - now.weekday())).isoformat()
            }
        }
        await self.config_tender(tender_id, update_data)
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                await recheck_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert data["data"]["status"] == "active.tendering"

        side_effects = [db.config, db.config, db.plans, db.plans]
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(side_effect=side_effects)):
                    await resync_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert data["data"]["status"] == "active.tendering"
        if data["data"].get("lots", None) is not None:
            assert "auctionPeriod" in data["data"]["lots"][0]
            assert parse_date(data["data"]["lots"][0]["auctionPeriod"]["startDate"], TZ).weekday() == 0
        else:
            assert "auctionPeriod" in data["data"]
            assert parse_date(data["data"]["auctionPeriod"]["startDate"], TZ).weekday() == 0

    async def test_set_auctionPeriod_skip_holidays(self, tender_id, db, scheduler):
        now = datetime.now(TZ)
        today = now.date()
        for i in range(10):
            date = today + timedelta(days=i)
            with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(return_value=db.config)):
                await set_holiday(date.isoformat())
        with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(return_value=db.config)):
            calendar = await get_calendar()
        now = datetime.now(TZ)
        update_data = {
            "enquiryPeriod": {
                "startDate": (now + timedelta(days=-15)).isoformat(),
                "endDate": (now + timedelta(days=-9)).isoformat()
            },
            "tenderPeriod": {
                "startDate": now.isoformat(),
                "endDate": (now + timedelta(days=6)).isoformat()
            }
        }
        await self.config_tender(tender_id, update_data)
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                await recheck_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert data["data"]["status"] == "active.tendering"

        side_effects = [db.config, db.config, db.plans, db.plans]

        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(side_effect=side_effects)):
                    await resync_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert data["data"]["status"] == "active.tendering"
        if data["data"].get("lots", None) is not None:
            assert "auctionPeriod" in data["data"]["lots"][0]
            auctionPeriodstart = parse_date(data["data"]["lots"][0]["auctionPeriod"]["startDate"], TZ)
        else:
            assert "auctionPeriod" in data["data"]
            auctionPeriodstart = parse_date(data["data"]["auctionPeriod"]["startDate"], TZ)
        assert auctionPeriodstart.date().isoformat() not in calendar
        assert auctionPeriodstart.date() > date

        for i in range(10):
            date = today + timedelta(days=i)
            with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(return_value=db.config)):
                await delete_holiday(date.isoformat())

    async def test_set_auctionPeriod_today(self, tender_id, db, scheduler):
        now = datetime.now(TZ)
        update_data = {
            "enquiryPeriod": {
                "startDate": (now + timedelta(days=-15)).isoformat(),
                "endDate": (now + timedelta(days=-9)).isoformat()
            },
            "tenderPeriod": {
                "startDate": now.isoformat(),
                "endDate": (
                        now + timedelta(days=14 - now.weekday())
                ).replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            }
        }
        await self.config_tender(tender_id, update_data)
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                await recheck_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert data["data"]["status"] == "active.tendering"

        side_effects = [db.config, db.config, db.plans, db.plans]
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(side_effect=side_effects)):
                    await resync_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert data["data"]["status"] == "active.tendering"
        if data["data"].get("lots", None) is not None:
            assert "auctionPeriod" in data["data"]["lots"][0]
            assert parse_date(data["data"]["lots"][0]["auctionPeriod"]["startDate"], TZ).weekday() == 0
        else:
            assert "auctionPeriod" in data["data"]
            assert parse_date(data["data"]["auctionPeriod"]["startDate"], TZ).weekday() == 0

    async def test_switch_to_unsuccessful(self, tender_id, db, scheduler):
        now = datetime.now(TZ)
        update_data = {
            "enquiryPeriod": {
                "startDate": (now + timedelta(days=-15)).isoformat(),
                "endDate": (now + timedelta(days=-9)).isoformat()
            },
            "tenderPeriod": {
                "startDate": (now + timedelta(days=-9)).isoformat(),
                "endDate": now.isoformat()
            }
        }
        await self.config_tender(tender_id, update_data)
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                await recheck_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert data["data"]["status"] == "active.tendering"
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.scheduler.SESSION", session):
                await recheck_tender(tender_id)
            resp = await session.get(f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}")
            data = await resp.json()
        assert data["data"]["status"] == "unsuccessful"


class TestTenderLots(TestClass):
    initial_lots = test_lots
