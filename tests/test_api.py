from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from prozorro_chronograph.settings import TZ, SMOOTHING_MAX
from .base import BaseTest, working_days


class TestSimple(BaseTest):
    async def test_list_jobs(self, cli):
        response = await cli.get("/jobs")
        assert response.status == 200
        data = await response.json()
        assert "jobs" in data
        assert len(data["jobs"]) == 0

    async def test_resync_one(self, cli, scheduler):
        now = datetime.now(TZ)
        response = await cli.get("/resync/all")
        assert response.status == 200
        data = await response.json()
        assert data is None

        job = scheduler.get_job("resync_api_all")
        assert job is not None
        assert job.next_run_time <= now + timedelta(milliseconds=SMOOTHING_MAX)

    async def test_recheck_one(self, cli, scheduler):
        now = datetime.now(TZ)
        response = await cli.get("/recheck/all")
        assert response.status == 200
        data = await response.json()
        assert data is None

        job = scheduler.get_job("recheck_api_all")
        assert job is not None
        assert job.next_run_time <= now + timedelta(milliseconds=SMOOTHING_MAX)

    async def test_calendar(self, cli, db):
        with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(return_value=db.config)):
            response = await cli.get("/calendar")
        data = await response.json()
        assert data == {"working_days": working_days}

    async def test_calendar_entry(self, cli, db):
        with patch("prozorro_chronograph.storage.get_mongodb_collection", MagicMock(return_value=db.config)):
            response = await cli.get("/calendar")
            data = await response.json()
            assert "2021-05-11" not in data["working_days"]

            response = await cli.post("/calendar/2021-05-11")
            assert response.status == 200
            data = await response.json()
            assert data is None

            response = await cli.get("/calendar")
            data = await response.json()
            assert "2021-05-11" in data["working_days"]

            response = await cli.delete("/calendar/2021-05-11")
            assert response.status == 200
            data = await response.json()
            assert data is None

            response = await cli.get("/calendar")
            data = await response.json()
            assert "2021-05-11" not in data["working_days"]
