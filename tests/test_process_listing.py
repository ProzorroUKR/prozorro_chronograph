from uuid import uuid4
from datetime import timedelta
from unittest.mock import patch, Mock
from freezegun import freeze_time

from prozorro_chronograph.utils import get_now
from prozorro_chronograph.scheduler import process_listing, push
from prozorro_chronograph.settings import TZ

from .base import BaseTenderTest


class TestTenderProcessListing(BaseTenderTest):
    @freeze_time("2012-01-14")
    @patch("prozorro_chronograph.scheduler.check_auction")
    @patch("prozorro_chronograph.scheduler.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.asyncio.sleep")
    @patch("prozorro_chronograph.scheduler.scheduler.add_job")
    async def test_process_listing_without_next_check(self, mock_add_job, mock_sleep, _, __, caplog):
        tender = {
            "id": uuid4().hex,
            "submissionMethodDetails": {"quick": "value"},
            "auctionPeriod": {
                "shouldStartAfter": (get_now() + timedelta(days=2)).isoformat(),
                "startDate": (get_now() + timedelta(days=1)).isoformat()
            }
        }
        server_id_cookie = "value"
        await process_listing(server_id_cookie, tender)
        mock_add_job.assert_called_once_with(
            push,
            "date",
            run_date=get_now() + timedelta(seconds=2),
            id=f'resync_{tender["id"]}',
            name=f'Resync {tender["id"]}',
            misfire_grace_time=60 * 60,
            args=["resync", tender["id"], server_id_cookie],
            replace_existing=True,
        )
        assert f'Start processing tender: {tender["id"]}' in caplog.messages[0]
        assert f'Set resync job for tender {tender["id"]}' in caplog.messages[1]
        assert len(caplog.messages) == 2
        mock_sleep.assert_called_once_with(1)

    @freeze_time("2012-01-14")
    @patch("prozorro_chronograph.scheduler.check_auction")
    @patch("prozorro_chronograph.scheduler.randint", Mock(return_value=2))
    @patch("prozorro_chronograph.scheduler.asyncio.sleep")
    @patch("prozorro_chronograph.scheduler.scheduler.add_job")
    async def test_process_listing_with_next_check(self, mock_add_job, mock_sleep, _, caplog):
        next_check = get_now() - timedelta(days=2)
        tenant_id = uuid4().hex
        tender = {
            "id": tenant_id,
            "next_check": next_check.isoformat(),
        }
        server_id_cookie = "value"
        await process_listing(server_id_cookie, tender)
        mock_add_job.assert_called_once()
        mock_add_job.assert_called_with(
            push,
            "date",
            run_date=get_now() + timedelta(seconds=2),
            timezone=TZ,
            id=f'recheck_{tender["id"]}',
            name=f'Recheck {tender["id"]}',
            misfire_grace_time=60 * 60,
            replace_existing=True,
            args=["recheck", tender["id"], server_id_cookie],
        )
        assert f'Start processing tender: {tender["id"]}' in caplog.messages[0]
        assert f"Tender {tenant_id} don't need to resync" in caplog.messages[1]
        assert len(caplog.messages) == 2
        mock_sleep.assert_called_once_with(1)

    @freeze_time("2012-01-14")
    @patch("prozorro_chronograph.scheduler.check_auction")
    @patch("prozorro_chronograph.scheduler.randint", return_value=2)
    @patch("prozorro_chronograph.scheduler.asyncio.sleep")
    @patch("prozorro_chronograph.scheduler.scheduler.add_job")
    async def test_process_listing_with_next_check_without_recheck_job(self, mock_add_job, mock_sleep, _, __, caplog):
        next_check = get_now() + timedelta(days=2)
        tenant_id = uuid4().hex
        tender = {
            "id": tenant_id,
            "next_check": next_check.isoformat(),
        }
        server_id_cookie = "value"
        await process_listing(server_id_cookie, tender)
        mock_add_job.assert_called_once_with(
            push,
            "date",
            run_date=next_check + timedelta(seconds=2),
            timezone=TZ,
            id=f'recheck_{tender["id"]}',
            name=f'Recheck {tender["id"]}',
            misfire_grace_time=60 * 60,
            replace_existing=True,
            args=["recheck", tender["id"], server_id_cookie],
        )
        assert f'Start processing tender: {tender["id"]}' in caplog.messages[0]
        assert f"Tender {tenant_id} don't need to resync" in caplog.messages[1]
        assert len(caplog.messages) == 2
        mock_sleep.assert_called_once_with(1)
