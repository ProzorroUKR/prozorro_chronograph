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
import pytest


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

    async def test_check_tender_without_tender_id(self):
        tender = deepcopy(test_tender_data)
        with pytest.raises(KeyError) as e:
            await check_tender(tender)
        assert "'id'" == str(e.value)

    async def test_check_tender_with_not_full_tender_dict(self, caplog):
        tender = deepcopy(test_tender_data)
        tender["id"] = uuid4().hex
        check_tender_return = await check_tender(tender)
        assert f"Checking tender`s {tender['id']} auctionPeriod: {{}}" == caplog.messages[0]
        assert len(caplog.messages) == 1
        assert check_tender_return == {}

    @patch("prozorro_chronograph.scheduler.SANDBOX_MODE", True)
    @patch("prozorro_chronograph.scheduler.skipped_days", return_value=" Skipped 2 full days.")
    @patch("prozorro_chronograph.utils.randint", return_value=2)
    async def test_check_tender_without_lots(self, mock_randint, _, caplog):
        tender = {
            "id": uuid4().hex,
            "submissionMethodDetails": {"quick": "value"},
            "auctionPeriod": {
                "shouldStartAfter": (get_now() + timedelta(days=2)).isoformat(),
                "startDate": (get_now() + timedelta(days=1)).isoformat()}}
        stream = 3
        auction_period = get_now()
        skip_days = (auction_period, 2, 4)
        with patch("prozorro_chronograph.scheduler.planning_auction",
                   side_effect=[Exception(), (auction_period, stream, skip_days)]):
            check_tender_return = await check_tender(tender)
        mock_randint.assert_called_once_with(0, 1799)
        assert f"Checking tender`s {tender['id']} auctionPeriod: {tender['auctionPeriod']}" == caplog.messages[0]
        assert "Error on planning tender '{}': {}".format(tender["id"], repr(Exception())) == caplog.messages[1]
        assert "{} auction for tender {} to {}. Stream {}.{}".format(
                "Replanned",
                tender["id"],
                (get_now() + timedelta(seconds=2)).isoformat(),
                stream,
                " Skipped 2 full days."
            ) == caplog.messages[2]
        assert len(caplog.messages) == 3
        assert check_tender_return == {'auctionPeriod': {'startDate': (get_now() + timedelta(seconds=2)).isoformat()}}

    @patch("prozorro_chronograph.scheduler.skipped_days", return_value=" Skipped 2 full days.")
    @patch("prozorro_chronograph.utils.randint", return_value=2)
    async def test_check_tender_with_lots(self, mock_randint, _, caplog):
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
        auction_period = get_now()
        skip_days = (auction_period, 2, 4)
        with patch("prozorro_chronograph.scheduler.planning_auction",
                   side_effect=[Exception(), (auction_period, stream, skip_days)]):
            check_tender_return = await check_tender(tender)
        mock_randint.assert_called_once_with(0, 1799)
        assert f"Checking tender`s {tender['id']} auctionPeriod: {{}}" == caplog.messages[0]
        assert "Error on planning tender '{}': {}".format(
                tender["id"],
                repr(Exception())
            ) in caplog.messages[1]
        assert "{} auction for lot {} of tender {} to {}. Stream {}.{}".format(
                "Replanned",
                tender["lots"][0]["id"],
                tender["id"],
                (get_now() + timedelta(seconds=2)).isoformat(),
                stream,
                " Skipped 2 full days.") in caplog.messages[2]
        assert len(caplog.messages) == 3
        assert check_tender_return == {'lots': [
            {'auctionPeriod': {'startDate': (get_now() + timedelta(seconds=2)).isoformat()}}, {}]}
