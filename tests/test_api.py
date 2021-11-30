from datetime import timedelta
from unittest.mock import patch, MagicMock
from freezegun import freeze_time

from prozorro_chronograph.utils import get_now
from prozorro_chronograph.scheduler import recheck_tender, resync_tender
from prozorro_chronograph.settings import TZ, SMOOTHING_MAX, SMOOTHING_MIN
from .base import BaseTest, working_days


class TestSimple(BaseTest):
    async def test_list_jobs(self, cli):
        response = await cli.get("/jobs")
        assert response.status == 200
        data = await response.json()
        assert "jobs" in data
        assert len(data["jobs"]) == 0

    @freeze_time("2012-01-14")
    @patch("prozorro_chronograph.api.randint", return_value=20)
    @patch("prozorro_chronograph.api.scheduler.add_job")
    async def test_resync_one(self, mock_add_job, mock_randint, cli):
        response = await cli.get("/resync/all")
        data = await response.json()
        assert response.status == 200
        assert data is None
        mock_randint.assert_called_once_with(SMOOTHING_MIN, SMOOTHING_MAX)
        mock_add_job.assert_called_once_with(
            resync_tender,
            run_date=get_now() + timedelta(milliseconds=20),
            misfire_grace_time=3600,
            replace_existing=True,
            name='Resync from api',
            id='resync_api_all',
            args=['all']
        )

    @freeze_time("2012-01-14")
    @patch("prozorro_chronograph.api.randint", return_value=20)
    @patch("prozorro_chronograph.api.scheduler.add_job")
    async def test_recheck_one(self, mock_add_job, mock_randint, cli):
        response = await cli.get("/recheck/all")
        assert response.status == 200
        data = await response.json()
        assert data is None
        mock_randint.assert_called_once_with(SMOOTHING_MIN, SMOOTHING_MAX)
        mock_add_job.assert_called_once_with(
            recheck_tender,
            run_date=get_now() + timedelta(milliseconds=20),
            misfire_grace_time=3600,
            replace_existing=True,
            name='Recheck from api',
            id='recheck_api_all',
            args=['all']
        )


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
