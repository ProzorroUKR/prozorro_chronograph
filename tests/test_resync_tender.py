from uuid import uuid4
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock, AsyncMock
from freezegun import freeze_time
import json

from prozorro_chronograph.utils import get_now
from prozorro_chronograph.scheduler import resync_tender, push
from prozorro_chronograph.settings import TZ, URL_SUFFIX, BASE_URL, SMOOTHING_MAX, SMOOTHING_MIN

from .base import BaseTenderTest


@freeze_time("2012-01-14")
class TestResyncTender(BaseTenderTest):
    @patch("prozorro_chronograph.scheduler.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.LOGGER.error")
    async def test_resync_tender_with_get_429(self, mock_logger_error, mock_randint):
        tender_id = uuid4().hex
        url = f"{BASE_URL}/{tender_id}{URL_SUFFIX}"
        response = MagicMock(status=429, text=AsyncMock(return_value="text_get_response"))
        with patch("prozorro_chronograph.scheduler.SESSION.get", AsyncMock(return_value=response)):
            resync_tender_return = await resync_tender(tender_id)
        mock_randint.assert_called_with(SMOOTHING_MIN, SMOOTHING_MAX)
        mock_logger_error.assert_called_once_with(
            f"Error too many requests {response.status} on getting tender '{url}': text_get_response")
        assert resync_tender_return == (get_now() + timedelta(seconds=2)).isoformat()

    @patch("prozorro_chronograph.scheduler.LOGGER.error")
    async def test_resync_tender_with_get_404(self, mock_logger_error):
        tender_id = uuid4().hex
        url = f"{BASE_URL}/{tender_id}{URL_SUFFIX}"
        response = MagicMock(status=404, text=AsyncMock(return_value="text_get_response"))
        with patch("prozorro_chronograph.scheduler.SESSION.get", AsyncMock(return_value=response)):
                    resync_tender_return = await resync_tender(tender_id)
        mock_logger_error.assert_called_once_with(
            f"Error {response.status} on getting tender '{url}': text_get_response")
        assert resync_tender_return is None

    @patch("prozorro_chronograph.scheduler.LOGGER.error")
    async def test_resync_tender_with_get_412(self, mock_logger_error):
        tender_id = uuid4().hex
        url = f"{BASE_URL}/{tender_id}{URL_SUFFIX}"
        response = MagicMock(status=412, text=AsyncMock(return_value="text_get_response"))
        with patch("prozorro_chronograph.scheduler.SESSION.get", AsyncMock(return_value=response)):
            resync_tender_return = await resync_tender(tender_id)
        mock_logger_error.assert_called_once_with(
            f"Error {response.status} on getting tender '{url}': text_get_response")
        assert resync_tender_return == "repeat"

    @patch("prozorro_chronograph.scheduler.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.scheduler.add_job")
    @patch("prozorro_chronograph.scheduler.LOGGER.error")
    async def test_resync_tender_with_get_422(self, mock_logger_error, mock_add_job, mock_randint):
        tender_id = uuid4().hex
        url = f"{BASE_URL}/{tender_id}{URL_SUFFIX}"
        response = MagicMock(status=422, text=AsyncMock(return_value="text_get_response"))
        with patch("prozorro_chronograph.scheduler.SESSION.get", AsyncMock(return_value=response)):
            resync_tender_return = await resync_tender(tender_id)
        mock_logger_error.assert_called_once_with(
            f"Error {response.status} on getting tender '{url}': text_get_response")
        mock_randint.assert_called_with(SMOOTHING_MIN, SMOOTHING_MAX)
        mock_add_job.assert_called_once_with(
            push,
            "date",
            run_date=get_now() + timedelta(seconds=2) + timedelta(seconds=2),
            timezone=TZ,
            id=f"{tender_id}",
            name=f"Resync {tender_id}",
            misfire_grace_time=60 * 60,
            replace_existing=True,
            args=["resync", tender_id], )
        assert resync_tender_return == (get_now() + timedelta(seconds=2)).isoformat()

    @patch("prozorro_chronograph.scheduler.check_tender", AsyncMock(return_value={}))
    async def test_resync_tender_with_get_200_with_check_tender_none(self):
        tender_id = uuid4().hex
        now_plus_1s = (datetime.now(TZ) + timedelta(seconds=1)).isoformat()
        response = MagicMock(
            status=200,
            text=AsyncMock(return_value=json.dumps({"data": {"next_check": now_plus_1s}}))
        )
        with patch("prozorro_chronograph.scheduler.SESSION.get", AsyncMock(return_value=response)):
            resync_tender_return = await resync_tender(tender_id)
        assert resync_tender_return is None

    @patch("prozorro_chronograph.scheduler.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.LOGGER.error")
    async def test_resync_tender_with_get_200_patch_429(self, mock_logger_error, mock_randint):
        tender_id = uuid4().hex
        url = f"{BASE_URL}/{tender_id}{URL_SUFFIX}"
        now_plus_1s = (datetime.now(TZ) + timedelta(seconds=1)).isoformat()
        response_get = MagicMock(
            status=200,
            text=AsyncMock(return_value=json.dumps({"data": {"next_check": now_plus_1s}}))
        )
        check_tender_return = AsyncMock(return_value={"auctionPeriod": {"startDate": now_plus_1s}})
        with patch("prozorro_chronograph.scheduler.SESSION.get", AsyncMock(return_value=response_get)):
            with patch("prozorro_chronograph.scheduler.check_tender", check_tender_return):
                response_patch = MagicMock(status=429, text=AsyncMock(return_value="text_patch_response"))
                with patch("prozorro_chronograph.scheduler.SESSION.patch", AsyncMock(return_value=response_patch)):
                    resync_tender_return = await resync_tender(tender_id)
        mock_randint.assert_called_with(SMOOTHING_MIN, SMOOTHING_MAX)
        mock_logger_error.assert_called_once_with(
            f"Error too many requests {response_patch.status} on getting tender '{url}': text_patch_response")
        assert resync_tender_return == (get_now() + timedelta(seconds=2)).isoformat()

    @patch("prozorro_chronograph.scheduler.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.LOGGER.error")
    async def test_resync_tender_with_get_200_patch_409(self, mock_logger_error, mock_randint):
        tender_id = uuid4().hex
        url = f"{BASE_URL}/{tender_id}{URL_SUFFIX}"
        now_plus_1s = (datetime.now(TZ) + timedelta(seconds=1)).isoformat()
        response_get = MagicMock(
            status=200,
            text=AsyncMock(return_value=json.dumps({"data": {"next_check": now_plus_1s}}))
        )
        with patch("prozorro_chronograph.scheduler.SESSION.get", AsyncMock(return_value=response_get)):
            check_tender_return = MagicMock(return_value={"auctionPeriod": {"startDate": now_plus_1s}})
            with patch("prozorro_chronograph.scheduler.check_tender", AsyncMock(return_value=check_tender_return)):
                response_patch = MagicMock(status=409, text=AsyncMock(return_value="text_patch_response"))
                with patch("prozorro_chronograph.scheduler.SESSION.patch", AsyncMock(return_value=response_patch)):
                    resync_tender_return = await resync_tender(tender_id)
        mock_randint.assert_called_with(SMOOTHING_MIN, SMOOTHING_MAX)
        mock_logger_error.assert_called_once_with(
            "Error {} on updating tender '{}' with '{}': {}".format(
                        response_patch.status, url, {"data": check_tender_return}, "text_patch_response"
            )
        )
        assert resync_tender_return == (get_now() + timedelta(seconds=2)).isoformat()

    @patch("prozorro_chronograph.scheduler.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.scheduler.add_job")
    async def test_resync_tender_with_get_200_patch_200_next_check_feture(self, mock_add_job, mock_randint):
        tender_id = uuid4().hex
        now_plus_1s = (get_now() + timedelta(seconds=1)).isoformat()
        response_get = MagicMock(
            status=200,
            text=AsyncMock(return_value=json.dumps({"data": {"next_check": now_plus_1s}}))
        )
        with patch("prozorro_chronograph.scheduler.SESSION.get", AsyncMock(return_value=response_get)):
            check_tender_return = MagicMock(return_value={"auctionPeriod": {"startDate": now_plus_1s}})
            with patch("prozorro_chronograph.scheduler.check_tender",
                       AsyncMock(return_value=check_tender_return)):
                response_patch = MagicMock(
                    status=200,
                    text=AsyncMock(return_value=json.dumps({"data": {"next_check": now_plus_1s}}))
                )
                with patch("prozorro_chronograph.scheduler.SESSION.patch",
                           AsyncMock(return_value=response_patch)):
                    resync_tender_return = await resync_tender(tender_id)
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
        assert resync_tender_return is None

    @patch("prozorro_chronograph.scheduler.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.scheduler.add_job")
    async def test_resync_tender_with_get_200_patch_200_next_check_back(self, mock_add_job, mock_randint):
        tender_id = uuid4().hex
        now_minus_1s = (get_now() - timedelta(seconds=1)).isoformat()
        response_get = MagicMock(
            status=200,
            text=AsyncMock(return_value=json.dumps({"data": {"next_check": now_minus_1s}}))
        )
        with patch("prozorro_chronograph.scheduler.SESSION.get", AsyncMock(return_value=response_get)):
            check_tender_return = MagicMock(return_value={"auctionPeriod": {"startDate": now_minus_1s}})
            with patch("prozorro_chronograph.scheduler.check_tender", AsyncMock(return_value=check_tender_return)):
                response_patch = MagicMock(
                    status=200,
                    text=AsyncMock(return_value=json.dumps({"data": {"next_check": now_minus_1s}}))
                )
                with patch("prozorro_chronograph.scheduler.SESSION.patch", AsyncMock(return_value=response_patch)):
                    resync_tender_return = await resync_tender(tender_id)
        mock_randint.assert_called_with(SMOOTHING_MIN, SMOOTHING_MAX)
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
        assert resync_tender_return is None
