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

    def test_format_notification_sleek(self):
        # Test sleek format: account: count
        results = {"official": 2, "personal": 0}
        title, body = format_notification(results)
        self.assertEqual(title, "Himalaya")
        expected_body = "official: 2\npersonal: 0"
        self.assertEqual(body, expected_body)

    def test_format_notification_with_err(self):
        # Test sleek format with ERR
        results = {"official": 2, "personal": "ERR"}
        title, body = format_notification(results)
        self.assertEqual(title, "Himalaya")
        expected_body = "official: 2\npersonal: ERR"
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


if __name__ == "__main__":
    unittest.main()
