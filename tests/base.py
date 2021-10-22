import asyncio
import base64
import json
import os
from copy import deepcopy
from datetime import timedelta
from unittest.mock import patch, MagicMock
import pytest
import standards
from aiohttp.client import ClientSession
from aiohttp.test_utils import TestClient, TestServer
from couchdb import Server
from motor.motor_asyncio import AsyncIOMotorClient

from prozorro_chronograph.api import create_app
from prozorro_chronograph.settings import scheduler
from prozorro_chronograph.storage import init_database
from prozorro_chronograph.utils import get_now
from .api_data import test_tender_data
from prozorro_crawler.settings import CRAWLER_USER_AGENT

PUBLIC_API_HOST = os.environ["PUBLIC_API_HOST"]
MONGODB_URL = os.environ["MONGODB_URL"]
MONGODB_DATABASE = os.environ["MONGODB_DATABASE"]
APSCHEDULER_DATABASE = os.environ["APSCHEDULER_DATABASE"]
COUCH_URL = os.environ["COUCH_URL"]

token = base64.b64encode(b"token:").decode("utf-8")
working_days = {}
holidays = standards.load("calendars/workdays_off.json")
for date_str in holidays:
    working_days[date_str] = True


@pytest.mark.asyncio
class BaseTest:
    @pytest.fixture
    def cli(self, event_loop):
        app = create_app()
        test_server = TestServer(app, loop=event_loop)
        test_client = TestClient(test_server, loop=event_loop)
        event_loop.run_until_complete(test_client.start_server())
        yield test_client
        event_loop.run_until_complete(test_client.close())

    @pytest.fixture
    def scheduler(self, event_loop):
        scheduler._eventloop = event_loop
        if not scheduler.running:
            scheduler.start()
        yield scheduler
        for job in scheduler.get_jobs():
            job.remove()
        scheduler.shutdown()

    @pytest.fixture
    def db(self, event_loop):
        mongo = AsyncIOMotorClient(MONGODB_URL)
        db = getattr(mongo, MONGODB_DATABASE)
        with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(return_value=db.config)):
            event_loop.run_until_complete(init_database())
        yield db
        event_loop.run_until_complete(db.plans.delete_many({}))
        event_loop.run_until_complete(db.config.delete_many({}))
        mongo.close()


class BaseTenderTest(BaseTest):
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Basic {token}",
        "User-Agent": CRAWLER_USER_AGENT
    }
    initial_lots = None
    initial_data = test_tender_data
    initial_bids = None
    sandbox = False
    cookies = None

    async def setup_cookies(self):
        async with ClientSession() as session:
            data = await session.options(f"{PUBLIC_API_HOST}/api/2.5/tenders")
            server_id_cookie = data.cookies["SERVER_ID"].value
        self.cookies = {"SERVER_ID": server_id_cookie}

    async def get_cookies(self):
        if self.cookies is None:
            await self.setup_cookies()
        return self.cookies

    async def create_tender(self):
        cookies = await self.get_cookies()
        session = ClientSession(cookies=cookies)
        resp = await session.post(
            f"{PUBLIC_API_HOST}/api/2.5/tenders",
            data=json.dumps({"data": self.initial_data}),
            headers=self.headers
        )
        tender = await resp.json()
        tender_id = tender["data"]["id"]
        if self.initial_lots:
            lots = []
            for i in self.initial_lots:
                response = await session.post(
                    f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}/lots",
                    data=json.dumps({"data": i}),
                    headers=self.headers
                )

                data = await response.json()
                assert response.status == 201
                lots.append(data["data"])
            self.initial_lots = lots
            response = await session.patch(
                f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}",
                data=json.dumps({"data": {"items": [
                    {"relatedLot": lots[i % len(lots)]["id"]} for i in range(len(tender["data"]["items"]))
                ]}}),
                headers=self.headers
            )
            assert response.status == 200
        if self.initial_bids:
            update_data = {
                "enquiryPeriod": {
                    "startDate": (get_now() + timedelta(days=-15)).isoformat(),
                    "endDate": (get_now() + timedelta(days=-8)).isoformat()
                },
                "tenderPeriod": {
                    "startDate": (get_now() + timedelta(days=-8)).isoformat(),
                    "endDate": (get_now() + timedelta(seconds=1)).isoformat()
                }
            }
            await self.config_tender(tender_id, update_data)
            headers = deepcopy(self.headers)
            token = base64.b64encode(b"chronograph:").decode("utf-8")
            headers["Authorization"] = f"Basic {token}"
            headers["User-Agent"] = CRAWLER_USER_AGENT
            for _ in range(100):
                response = await session.patch(
                    f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}",
                    data=json.dumps({"data": {"id": tender_id}}),
                    headers=headers
                )
                data = await response.json()
                if data["data"]["status"] == "active.tendering":
                    break
            bids = []
            for i in self.initial_bids:
                if self.initial_lots:
                    i = i.copy()
                    value = i.pop("value")
                    i["lotValues"] = [
                        {
                            "value": value,
                            "relatedLot": lot["id"],
                        }
                        for lot in self.initial_lots
                    ]
                response = await session.post(
                    f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}/bids",
                    data=json.dumps({"data": i}),
                    headers=self.headers
                )
                data = await response.json()
                bids.append(data["data"])
            self.initial_bids = bids
            await asyncio.sleep(1)
        return tender_id

    async def config_tender(self, tender_id, update_data):
        cookies = await self.get_cookies()
        async with ClientSession(cookies=cookies) as session:
            resp = await session.patch(
                f"{PUBLIC_API_HOST}/api/2.5/tenders/{tender_id}",
                data=json.dumps({"data": update_data}),
                headers=self.headers
            )
            data = await resp.json()
        assert resp.status == 200
        assert data["data"]["enquiryPeriod"] == update_data["enquiryPeriod"]
        assert data["data"]["tenderPeriod"] == update_data["tenderPeriod"]

    @pytest.fixture
    def tender_id(self, event_loop, couch):
        tender_id = event_loop.run_until_complete(self.create_tender())
        yield tender_id
        doc = couch.get(tender_id)
        couch.delete(doc)

    @pytest.fixture
    def couch(self):
        server = Server(COUCH_URL)
        db = server["openprocurement"]
        return db
