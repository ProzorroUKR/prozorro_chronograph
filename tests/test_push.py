from uuid import uuid4
from datetime import timedelta
from unittest.mock import patch, AsyncMock

from prozorro_chronograph.utils import get_now
from prozorro_chronograph.scheduler import push

from .base import BaseTenderTest


class TestTenderPush(BaseTenderTest):
    @patch("prozorro_chronograph.scheduler.asyncio.sleep")
    @patch("prozorro_chronograph.scheduler.get_feed_position", AsyncMock(return_value={"server_id": "value"}))
    @patch("prozorro_chronograph.scheduler.LOGGER.error")
    async def test_push_recheck_mode(self, mock_logger_error, *args):
        mode = "recheck"
        tender_id = uuid4().hex
        server_id = "value"
        return_recheck_tender = (get_now() + timedelta(minutes=1)).isoformat()
        with patch("prozorro_chronograph.scheduler.recheck_tender",
                   AsyncMock(side_effect=[Exception(), return_recheck_tender])) as mock_recheck_tender:
            await push(mode, tender_id, server_id)
        mock_logger_error.assert_called_once_with(f"Error on {mode} tender {tender_id}: {repr(Exception())}")
        mock_recheck_tender.assert_called_with(tender_id)

    @patch("prozorro_chronograph.scheduler.asyncio.sleep")
    @patch("prozorro_chronograph.scheduler.get_feed_position", AsyncMock(return_value={"server_id": "value"}))
    @patch("prozorro_chronograph.scheduler.LOGGER.error")
    async def test_push_resync_mode(self, mock_logger_error, *args):
        mode = "resync"
        tender_id = uuid4().hex
        server_id = "value"
        return_resync_tender = (get_now() + timedelta(minutes=1)).isoformat()
        with patch("prozorro_chronograph.scheduler.resync_tender",
                   AsyncMock(side_effect=[Exception(), return_resync_tender])) as mock_resync_tender:
            await push(mode, tender_id, server_id)
        mock_logger_error.assert_called_once_with(f"Error on {mode} tender {tender_id}: {repr(Exception())}")
        mock_resync_tender.assert_called_with(tender_id)

    @patch("prozorro_chronograph.scheduler.asyncio.sleep")
    @patch("prozorro_chronograph.scheduler.get_feed_position", AsyncMock(return_value={"server_id": "value"}))
    @patch("prozorro_chronograph.scheduler.SESSION.cookie_jar.update_cookies")
    async def test_push_resync_server_id_none_with_feed_position(self, mock_update_cookies, *args):
        mode = "resync"
        tender_id = uuid4().hex
        server_id = None
        return_resync_tender = (get_now() + timedelta(minutes=1)).isoformat()
        with patch("prozorro_chronograph.scheduler.resync_tender",
                   AsyncMock(return_value=return_resync_tender)) as mock_resync_tender:
            await push(mode, tender_id, server_id)
        mock_update_cookies.assert_called_with({"SERVER_ID": "value"})
        mock_resync_tender.assert_called_with(tender_id)

    @patch("prozorro_chronograph.scheduler.asyncio.sleep")
    @patch("prozorro_chronograph.scheduler.get_feed_position", AsyncMock(return_value=None))
    @patch("prozorro_chronograph.scheduler.SESSION.cookie_jar.update_cookies")
    async def test_push_resync_server_id_none_without_feed_position(self, mock_update_cookies, *args):
        mode = "resync"
        tender_id = uuid4().hex
        server_id = None
        return_resync_tender = (get_now() + timedelta(minutes=1)).isoformat()
        with patch("prozorro_chronograph.scheduler.resync_tender",
                   AsyncMock(return_value=return_resync_tender)) as mock_resync_tender:
            await push(mode, tender_id, server_id)
        mock_update_cookies.assert_called_with({"SERVER_ID": None})
        mock_resync_tender.assert_called_with(tender_id)
