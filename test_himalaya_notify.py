#!/usr/bin/env python3
"""
Unit tests for Himalaya Notification Tool.
"""

from datetime import datetime, timedelta, timezone
import json
import unittest
from unittest.mock import MagicMock, patch

from himalaya_notify import (
    check_emails,
    count_recent_emails,
    format_notification,
    get_next_schedule_time,
    parse_envelope_date,
    send_desktop_notification,
)


class TestHimalayaNotify(unittest.TestCase):
    def test_parse_envelope_date(self):
        # Format with timezone offset
        dt1 = parse_envelope_date("2026-09-22 07:42+05:30")
        self.assertEqual(dt1.year, 2026)
        self.assertEqual(dt1.month, 9)
        self.assertEqual(dt1.day, 22)
        self.assertEqual(dt1.hour, 7)
        self.assertEqual(dt1.minute, 42)
        self.assertIsNotNone(dt1.tzinfo)

        # Negative offset
        dt2 = parse_envelope_date("2026-09-21 14:47-07:00")
        self.assertEqual(dt2.hour, 14)
        self.assertIsNotNone(dt2.tzinfo)

        # UTC format
        dt3 = parse_envelope_date("2026-09-22 04:10+00:00")
        self.assertEqual(dt3.utcoffset().total_seconds(), 0)

    def test_get_next_schedule_time(self):
        # Test 3-hour boundaries
        self.assertEqual(get_next_schedule_time(datetime(2026, 9, 22, 19, 25)), "21:00")
        self.assertEqual(get_next_schedule_time(datetime(2026, 9, 22, 21, 0)), "00:00")
        self.assertEqual(get_next_schedule_time(datetime(2026, 9, 22, 23, 45)), "00:00")
        self.assertEqual(get_next_schedule_time(datetime(2026, 9, 22, 1, 15)), "03:00")
        self.assertEqual(get_next_schedule_time(datetime(2026, 9, 22, 3, 0)), "06:00")

    def test_format_notification_layout(self):
        start = datetime(2026, 9, 22, 16, 30)
        end = datetime(2026, 9, 22, 19, 30)
        results = {"official": 2, "personal": 0}

        title, body = format_notification(results, start_time=start, end_time=end)
        self.assertEqual(title, "16:30 – 19:30")
        expected_body = (
            "<tt> 2  Official\n"
            " 0  Personal</tt>\n\n"
            "Next check at 21:00"
        )
        self.assertEqual(body, expected_body)

    def test_format_notification_with_err_alignment(self):
        start = datetime(2026, 9, 22, 16, 30)
        end = datetime(2026, 9, 22, 19, 30)
        results = {"official": 2, "personal": "ERR"}

        title, body = format_notification(results, start_time=start, end_time=end)
        self.assertEqual(title, "16:30 – 19:30")
        expected_body = (
            "<tt>  2  Official\n"
            "ERR  Personal</tt>\n\n"
            "Next check at 21:00"
        )
        self.assertEqual(body, expected_body)

    @patch("himalaya_notify.subprocess.run")
    def test_count_recent_emails_filtering_and_early_stop(self, mock_run):
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=3)

        recent_dt1 = (now - timedelta(minutes=30)).isoformat()
        recent_dt2 = (now - timedelta(hours=2)).isoformat()
        old_dt = (now - timedelta(hours=5)).isoformat()
        ancient_dt = (now - timedelta(hours=24)).isoformat()

        mock_envelopes = [
            {"id": "103", "date": recent_dt1},
            {"id": "102", "date": recent_dt2},
            {"id": "101", "date": old_dt},
            {"id": "100", "date": ancient_dt},
        ]

        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps(mock_envelopes),
            stderr="",
        )

        count = count_recent_emails("test_account", cutoff)
        self.assertEqual(count, 2)

    @patch("himalaya_notify.subprocess.run")
    def test_count_recent_emails_guardrail_on_error(self, mock_run):
        # When subprocess fails or times out, it should raise an exception
        mock_run.return_value = MagicMock(
            returncode=1,
            stdout="",
            stderr="IMAP authentication failed",
        )
        with self.assertRaises(RuntimeError):
            count_recent_emails("broken_account", datetime.now(timezone.utc))

    @patch("himalaya_notify.count_recent_emails")
    @patch("himalaya_notify.get_accounts")
    @patch("himalaya_notify.send_desktop_notification")
    def test_check_emails_guardrail_marks_err(self, mock_send, mock_accounts, mock_count):
        mock_accounts.return_value = ["acc_ok", "acc_fail", "acc_zero"]

        def side_effect(account, cutoff):
            if account == "acc_ok":
                return 4
            elif account == "acc_zero":
                return 0
            elif account == "acc_fail":
                raise TimeoutError("Command timed out")
            return 0

        mock_count.side_effect = side_effect
        mock_send.return_value = True

        results = check_emails(hours=3.0, dry_run=True, quiet=True)

        self.assertEqual(results["acc_ok"], 4)
        self.assertEqual(results["acc_zero"], 0)
        self.assertEqual(results["acc_fail"], "ERR")

    def test_format_notification_with_off_alignment(self):
        start = datetime(2026, 9, 22, 16, 30)
        end = datetime(2026, 9, 22, 19, 30)
        results = {"official": "OFF", "personal": "OFF"}

        title, body = format_notification(results, start_time=start, end_time=end)
        self.assertEqual(title, "16:30 – 19:30")
        expected_body = (
            "<tt>OFF  Official\n"
            "OFF  Personal</tt>\n\n"
            "Next check at 21:00"
        )
        self.assertEqual(body, expected_body)

    @patch("himalaya_notify.socket.create_connection")
    @patch("himalaya_notify.socket.gethostbyname")
    def test_is_online_success(self, mock_dns, mock_conn):
        mock_conn.return_value = MagicMock()
        mock_dns.return_value = "142.250.190.109"
        from himalaya_notify import is_online
        self.assertTrue(is_online(max_wait=0.1))

    @patch("himalaya_notify.socket.create_connection")
    def test_is_online_failure(self, mock_conn):
        mock_conn.side_effect = OSError("Network unreachable")
        from himalaya_notify import is_online
        self.assertFalse(is_online(max_wait=0.1))

    @patch("himalaya_notify.is_online")
    @patch("himalaya_notify.get_accounts")
    @patch("himalaya_notify.count_recent_emails")
    def test_check_emails_offline_marks_off(self, mock_count, mock_accounts, mock_online):
        mock_online.return_value = False
        mock_accounts.return_value = ["official", "personal"]

        results = check_emails(hours=3.0, dry_run=True, quiet=True)

        self.assertEqual(results["official"], "OFF")
        self.assertEqual(results["personal"], "OFF")
        # Ensure himalaya is never called when offline
        mock_count.assert_not_called()

    @patch("himalaya_notify.subprocess.run")
    @patch("himalaya_notify.shutil.which")
    def test_update_self_success(self, mock_which, mock_run):
        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"
        mock_run.return_value = MagicMock(returncode=0, stdout="Already up to date.", stderr="")
        from himalaya_notify import update_self
        self.assertEqual(update_self(), 0)

    @patch("himalaya_notify.subprocess.run")
    @patch("himalaya_notify.shutil.which")
    def test_update_self_git_failure(self, mock_which, mock_run):
        mock_which.side_effect = lambda cmd: f"/usr/bin/{cmd}"
        mock_run.return_value = MagicMock(returncode=1, stdout="", stderr="Could not resolve host")
        from himalaya_notify import update_self
        self.assertEqual(update_self(), 1)


if __name__ == "__main__":
    unittest.main()
