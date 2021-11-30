from uuid import uuid4
from unittest.mock import patch, AsyncMock
from aiohttp.client import ClientSession

from prozorro_chronograph.settings import INVALID_STATUSES
from prozorro_chronograph.main import data_handler

from .base import BaseTenderTest


class TestDataHandler(BaseTenderTest):
    @patch("prozorro_chronograph.main.asyncio.gather", side_effect=AsyncMock())
    @patch("prozorro_chronograph.main.process_listing")
    async def test_data_handler(self, mock_process_listing, mock_syncio_gather):
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.main.ClientSession", session) as mock_session:
                items = [{"status": "active"}]
                await data_handler(mock_session, items)
        mock_process_listing.assert_called_once_with(None, {"status": "active"})
        mock_syncio_gather.assert_has_calls(mock_process_listing)

    @patch("prozorro_chronograph.main.asyncio.gather", side_effect=AsyncMock())
    @patch("prozorro_chronograph.main.LOGGER.info")
    async def test_data_handler_with_invalid_status(self, mock_info, mock_syncio_gather):
        async with ClientSession(cookies=self.cookies) as session:
            with patch("prozorro_chronograph.main.ClientSession", session) as mock_session:
                tender_id = uuid4().hex
                items = [{
                    "status": INVALID_STATUSES[0],
                    "id": tender_id
                }]
                await data_handler(mock_session, items)
        mock_info.assert_called_once_with(f"Skip tender {tender_id} with status {INVALID_STATUSES[0]}")
        mock_syncio_gather.assert_called_once_with()
