from uuid import uuid4
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from freezegun import freeze_time
import json

from prozorro_chronograph.utils import get_now
from prozorro_chronograph.scheduler import recheck_tender, push
from prozorro_chronograph.settings import TZ, URL_SUFFIX, BASE_URL, SMOOTHING_MAX, SMOOTHING_MIN, INVALID_STATUSES

from .base import BaseTenderTest


@freeze_time("2012-01-14")
class TestRecheckTender(BaseTenderTest):
    @patch("prozorro_chronograph.scheduler.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.scheduler.add_job")
    async def test_recheck_tender_with_patch_200_next_check_past(self,  mock_add_job, mock_randint):
        tender_id = uuid4().hex
        now_minus_1s = (get_now() - timedelta(seconds=1)).isoformat()
        response = MagicMock(
            status=200,
            text=AsyncMock(return_value=json.dumps({"data": {"next_check": now_minus_1s}}))
        )
        with patch("prozorro_chronograph.scheduler.SESSION.patch", AsyncMock(return_value=response)):
            recheck_tender_return = await recheck_tender(tender_id)
        mock_randint.assert_called_once_with(SMOOTHING_MIN, SMOOTHING_MAX)
        mock_add_job.assert_called_once_with(
            push,
            "date",
            run_date=get_now() + timedelta(seconds=2),
            timezone=TZ,
            id=f"recheck_{tender_id}",
            name=f"Recheck {tender_id}",
            misfire_grace_time=60 * 60,
            replace_existing=True,
            args=["recheck", tender_id],
        )
        assert recheck_tender_return == now_minus_1s

    @patch("prozorro_chronograph.scheduler.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.scheduler.add_job")
    async def test_recheck_tender_with_patch_200_next_check_future(self, mock_add_job, mock_randint):
        tender_id = uuid4().hex
        now_plus_1s = (datetime.now(TZ) + timedelta(seconds=1)).isoformat()
        response = MagicMock(
            status=200,
            text=AsyncMock(return_value=json.dumps({"data": {"next_check": now_plus_1s}}))
        )
        with patch("prozorro_chronograph.scheduler.SESSION.patch", AsyncMock(return_value=response)):
            recheck_tender_return = await recheck_tender(tender_id)
        mock_randint.assert_called_once_with(SMOOTHING_MIN, SMOOTHING_MAX)
        mock_add_job.assert_called_once_with(
            push,
            "date",
            run_date=get_now() + timedelta(seconds=1) + timedelta(seconds=2),
            timezone=TZ,
            id=f"recheck_{tender_id}",
            name=f"Recheck {tender_id}",
            misfire_grace_time=60 * 60,
            replace_existing=True,
            args=["recheck", tender_id],
        )
        assert recheck_tender_return == now_plus_1s

    @patch("prozorro_chronograph.scheduler.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.scheduler.add_job")
    @patch("prozorro_chronograph.scheduler.LOGGER.error")
    async def test_recheck_tender_with_patch_429(self, mock_logger_error, mock_add_job, mock_randint):
        tender_id = uuid4().hex
        url = f"{BASE_URL}/{tender_id}{URL_SUFFIX}"
        response = MagicMock(status=429, text=AsyncMock(return_value="text_patch_response"))
        with patch("prozorro_chronograph.scheduler.SESSION.patch", AsyncMock(return_value=response)):
            recheck_tender_return = await recheck_tender(tender_id)
        mock_logger_error.assert_called_once_with(
            f"Error too many requests {response.status} on getting tender '{url}': text_patch_response")
        mock_randint.assert_called_once_with(SMOOTHING_MIN, SMOOTHING_MAX)
        mock_add_job.assert_called_once_with(
            push,
            "date",
            run_date=get_now() + timedelta(minutes=1) + timedelta(seconds=2),
            timezone=TZ,
            id=f"recheck_{tender_id}",
            name=f"Recheck {tender_id}",
            misfire_grace_time=60 * 60,
            replace_existing=True,
            args=["recheck", tender_id],
        )
        assert recheck_tender_return == (get_now() + timedelta(minutes=1)).isoformat()

    @patch("prozorro_chronograph.scheduler.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.scheduler.add_job")
    @patch("prozorro_chronograph.scheduler.LOGGER.error")
    async def test_recheck_tender_with_patch_409(self, mock_logger_error, mock_add_job, mock_randint):
        tender_id = uuid4().hex
        url = f"{BASE_URL}/{tender_id}{URL_SUFFIX}"
        response = MagicMock(status=409, text=AsyncMock(return_value="text_patch_response"))
        with patch("prozorro_chronograph.scheduler.SESSION.patch", AsyncMock(return_value=response)):
            recheck_tender_return = await recheck_tender(tender_id)
        mock_logger_error.assert_called_once_with(
            f"Error {response.status} on checking tender '{url}': text_patch_response")
        mock_randint.assert_called_once_with(SMOOTHING_MIN, SMOOTHING_MAX)
        mock_add_job.assert_called_once_with(
            push,
            "date",
            run_date=get_now() + timedelta(minutes=1) + timedelta(seconds=2),
            timezone=TZ,
            id=f"recheck_{tender_id}",
            name=f"Recheck {tender_id}",
            misfire_grace_time=60 * 60,
            replace_existing=True,
            args=["recheck", tender_id],
        )
        assert recheck_tender_return == (get_now() + timedelta(minutes=1)).isoformat()

    @patch("prozorro_chronograph.scheduler.LOGGER")
    async def test_recheck_tender_with_patch_422_and_get_200_with_invalid_statuses(self, mock_logger):
        tender_id = uuid4().hex
        url = f"{BASE_URL}/{tender_id}{URL_SUFFIX}"
        patch_response = MagicMock(status=422, text=AsyncMock(return_value="text_patch_response"))
        with patch("prozorro_chronograph.scheduler.SESSION.patch", AsyncMock(return_value=patch_response)):
            get_response = MagicMock(
                status=200,
                text=AsyncMock(return_value=json.dumps(
                    {"data": {
                        "id": tender_id,
                        "status": INVALID_STATUSES[0]
                    }})))
            with patch("prozorro_chronograph.scheduler.SESSION.get", AsyncMock(return_value=get_response)):
                recheck_tender_return = await recheck_tender(tender_id)
        mock_logger.error.assert_called_once_with(
            f"Error {patch_response.status} on checking tender '{url}': text_patch_response")
        mock_logger.info.assert_called_once_with(
            f"Next check won't be set for tender {tender_id} with status {INVALID_STATUSES[0]}")
        assert recheck_tender_return is None

    @patch("prozorro_chronograph.scheduler.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.scheduler.add_job")
    @patch("prozorro_chronograph.scheduler.LOGGER.error")
    async def test_recheck_tender_with_patch_422_and_get_200_with_not_invalid_status(self, mock_logger_error, mock_add_job, mock_randint):
        tender_id = uuid4().hex
        url = f"{BASE_URL}/{tender_id}{URL_SUFFIX}"
        patch_response = MagicMock(status=422, text=AsyncMock(return_value="text_patch_response"))
        with patch("prozorro_chronograph.scheduler.SESSION.patch", AsyncMock(return_value=patch_response)):
            get_response = MagicMock(
                status=200,
                text=AsyncMock(return_value=json.dumps(
                    {"data": {
                        "id": tender_id,
                        "status": "successful"
                    }})))
            with patch("prozorro_chronograph.scheduler.SESSION.get", AsyncMock(return_value=get_response)):
                recheck_tender_return = await recheck_tender(tender_id)
        mock_logger_error.assert_called_once_with(f"Error {patch_response.status} on checking tender '{url}': text_patch_response")
        mock_randint.assert_called_once_with(SMOOTHING_MIN, SMOOTHING_MAX)
        mock_add_job.assert_called_once_with(
            push,
            "date",
            run_date=get_now() + timedelta(minutes=1) + timedelta(seconds=2),
            timezone=TZ,
            id=f"recheck_{tender_id}",
            name=f"Recheck {tender_id}",
            misfire_grace_time=60 * 60,
            replace_existing=True,
            args=["recheck", tender_id], )
        assert recheck_tender_return == (get_now() + timedelta(minutes=1)).isoformat()

    @patch("prozorro_chronograph.scheduler.LOGGER.error")
    async def test_recheck_tender_with_patch_422_and_get_404(self, mock_logger_error):
        tender_id = uuid4().hex
        url = f"{BASE_URL}/{tender_id}{URL_SUFFIX}"
        patch_response = MagicMock(status=422, text=AsyncMock(return_value="text_patch_response"))
        with patch("prozorro_chronograph.scheduler.SESSION.patch", AsyncMock(return_value=patch_response)):
            get_response = MagicMock(status=404, text=AsyncMock(return_value="text_get_response"))
            with patch("prozorro_chronograph.scheduler.SESSION.get", AsyncMock(return_value=get_response)):
                recheck_tender_return = await recheck_tender(tender_id)
        mock_logger_error.assert_called_once_with(
            f"Error {patch_response.status} on checking tender '{url}': text_patch_response")
        assert recheck_tender_return == (get_now() + timedelta(minutes=1)).isoformat()
