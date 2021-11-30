from copy import deepcopy
from uuid import uuid4
from datetime import timedelta
from unittest.mock import patch
from freezegun import freeze_time

from prozorro_chronograph.utils import get_now
from prozorro_chronograph.scheduler import check_tender
from prozorro_chronograph.settings import INVALID_STATUSES

from .api_data import test_tender_data
from .base import BaseTenderTest


@freeze_time("2012-01-14")
class TestCheckTender(BaseTenderTest):
    async def test_check_tender_with_invalid_status(self):
        now_minus_1s = (get_now() - timedelta(seconds=1)).isoformat()
        tender = {
            "status": INVALID_STATUSES[0],
            "auctionPeriod":
                {"startDate": now_minus_1s}}
        check_tender_return = await check_tender(tender)
        assert check_tender_return == {}

    async def test_check_tender_with_not_full_tender_dict(self):
        tender = deepcopy(test_tender_data)
        check_tender_return = await check_tender(tender)
        assert check_tender_return == {}

    @patch("prozorro_chronograph.scheduler.SANDBOX_MODE", True)
    @patch("prozorro_chronograph.scheduler.skipped_days", return_value=" Skipped 2 full days.")
    @patch("prozorro_chronograph.utils.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.LOGGER")
    async def test_check_tender_with_without_lots(self, mock_logger, mock_randint, *args):
        tender = {
            "id": uuid4().hex,
            "submissionMethodDetails": {"quick": "value"},
            "auctionPeriod": {
                "shouldStartAfter": (get_now() + timedelta(days=2)).isoformat(),
                "startDate": (get_now() + timedelta(days=1)).isoformat()}}
        stream = 3
        auctionPeriod = get_now()
        skip_days = (auctionPeriod, 2, 4)
        with patch("prozorro_chronograph.scheduler.planning_auction",
                   side_effect=[Exception(), (auctionPeriod, stream, skip_days)]):
            check_tender_return = await check_tender(tender)
        mock_randint.assert_called_once_with(0, 1799)
        mock_logger.error.assert_called_once_with(
            "Error on planning tender '{}': {}".format(
                tender["id"],
                repr(Exception())
            )
        )
        mock_logger.info.assert_called_once_with(
            "{} auction for tender {} to {}. Stream {}.{}".format(
                "Replanned",
                tender["id"],
                (get_now() + timedelta(seconds=2)).isoformat(),
                stream,
                " Skipped 2 full days."
            )
        )
        assert check_tender_return == {'auctionPeriod': {'startDate': (get_now() + timedelta(seconds=2)).isoformat()}}

    @patch("prozorro_chronograph.scheduler.skipped_days", return_value=" Skipped 2 full days.")
    @patch("prozorro_chronograph.utils.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.LOGGER")
    async def test_check_tender_with_lots(self, mock_logger, mock_randint, *args):
        tender = {
            "id": uuid4().hex,
            "lots": [
                {"status": "active",
                 "id": uuid4().hex,
                 "submissionMethodDetails": {"quick": "value"},
                 "auctionPeriod": {
                     "shouldStartAfter": (get_now() + timedelta(days=2)).isoformat(),
                     "startDate": (get_now() + timedelta(days=1)).isoformat()
                 }},
                {"status": "complete",
                 "id": uuid4().hex,
                 "submissionMethodDetails": {"quick": "value"},
                 "auctionPeriod": {
                     "shouldStartAfter": (get_now() + timedelta(days=2)).isoformat(),
                     "startDate": (get_now() + timedelta(days=1)).isoformat()
                 }}
            ]
        }
        stream = 3
        auctionPeriod = get_now()
        skip_days = (auctionPeriod, 2, 4)
        with patch("prozorro_chronograph.scheduler.planning_auction",
                   side_effect=[Exception(), (auctionPeriod, stream, skip_days)]):
            check_tender_return = await check_tender(tender)
        mock_randint.assert_called_once_with(0, 1799)
        mock_logger.error.assert_called_once_with(
            "Error on planning tender '{}': {}".format(
                tender["id"],
                repr(Exception())
            )
        )
        mock_logger.info.assert_called_once_with(
            "{} auction for lot {} of tender {} to {}. Stream {}.{}".format(
                "Replanned",
                tender["lots"][0]["id"],
                tender["id"],
                (get_now() + timedelta(seconds=2)).isoformat(),
                stream,
                " Skipped 2 full days."
            ))
        assert check_tender_return == {'lots': [
            {'auctionPeriod': {'startDate': (get_now() + timedelta(seconds=2)).isoformat()}}, {}]}
