#!/usr/bin/env python3
"""
Himalaya Notification Tool
Counts emails received in the last N hours (default 3h) across all accounts
and delivers a sleek FreeDesktop desktop notification without external dependencies.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
from typing import Any, Dict, List, Union


def is_online(
    max_wait: float = 10.0,
    host: str = "1.1.1.1",
    port: int = 53,
    dns_host: str = "imap.gmail.com",
) -> bool:
    """
    Check if internet connectivity and DNS resolution are active.
    Polls up to max_wait seconds to allow Wi-Fi and DNS to settle after machine wake-up.
    """
    start_time = time.time()
    while True:
        try:
            with socket.create_connection((host, port), timeout=2.0):
                pass
            socket.gethostbyname(dns_host)
            return True
        except OSError:
            if time.time() - start_time + 1.0 <= max_wait:
                time.sleep(1.0)
            else:
                break
    return False


def get_accounts() -> List[str]:
    """Fetch list of account names from himalaya."""
    himalaya_bin = shutil.which("himalaya") or "/usr/local/bin/himalaya"
    cmd = [himalaya_bin, "--quiet", "--output", "json", "account", "list"]
    res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if res.returncode != 0:
        raise RuntimeError(f"himalaya account list failed ({res.returncode}): {res.stderr.strip()}")

    raw_output = res.stdout.strip()
    if not raw_output:
        return []

    # Strip any potential warning lines before JSON payload if present
    json_start = raw_output.find("[")
    if json_start == -1:
        raise ValueError(f"No JSON array found in account list output: {raw_output}")

    accounts_data = json.loads(raw_output[json_start:])
    accounts = [acc["name"] for acc in accounts_data if "name" in acc]
    return accounts


def parse_envelope_date(date_str: str) -> datetime:
    """Parse himalaya envelope date string into a timezone-aware datetime object."""
    date_str = date_str.strip()
    try:
        dt = datetime.fromisoformat(date_str)
    except ValueError:
        # Fallback for formats like '2026-09-22 07:42+05:30'
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M%z")

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def count_recent_emails(
    account: str,
    cutoff: datetime,
    timeout: int = 25,
    page_size: int = 50,
) -> int:
    """
    Fetch envelopes ordered by date descending and count those received >= cutoff.
    Stops as soon as an envelope older than cutoff is encountered.
    """
    himalaya_bin = shutil.which("himalaya") or "/usr/local/bin/himalaya"
    cmd = [
        himalaya_bin,
        "--quiet",
        "--output",
        "json",
        "envelope",
        "list",
        "-a",
        account,
        "-s",
        str(page_size),
    ]

    res = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if res.returncode != 0:
        raise RuntimeError(f"himalaya envelope list failed for {account}: {res.stderr.strip()}")

    raw_output = res.stdout.strip()
    if not raw_output:
        return 0

    json_start = raw_output.find("[")
    if json_start == -1:
        raise ValueError(f"Invalid JSON returned for account {account}: {raw_output}")

    envelopes = json.loads(raw_output[json_start:])
    cutoff_utc = cutoff.astimezone(timezone.utc)

    count = 0
    for env in envelopes:
        date_raw = env.get("date")
        if not date_raw:
            continue
        try:
            env_dt = parse_envelope_date(date_raw)
        except Exception:
            # If a single envelope date can't be parsed, skip it
            continue

        if env_dt.astimezone(timezone.utc) >= cutoff_utc:
            count += 1
        else:
            # Envelopes are ordered descending; once older than cutoff, we stop
            break

    return count


def get_next_schedule_time(now: datetime) -> str:
    """Calculate the next 3-hour boundary (00:00, 03:00, ..., 21:00) in local time."""
    next_hour = ((now.hour // 3) + 1) * 3
    if next_hour >= 24:
        return "00:00"
    return f"{next_hour:02d}:00"


def format_notification(
    results: Dict[str, Union[int, str]],
    start_time: datetime | None = None,
    end_time: datetime | None = None,
) -> tuple[str, str]:
    """
    Format notification:
    - Title: exact time window, e.g. '16:25 – 19:25'
    - Body: 2-column monospace table (right-aligned count, left-aligned account)
    - Footer: 'Next check at HH:MM'
    """
    if end_time is None:
        end_time = datetime.now()
    if start_time is None:
        start_time = end_time - timedelta(hours=3)

    time_fmt = "%H:%M"
    title = f"{start_time.strftime(time_fmt)} \u2013 {end_time.strftime(time_fmt)}"

    if not results:
        body = "<tt>--  No accounts</tt>"
    else:
        max_width = max(len(str(val)) for val in results.values())
        max_width = max(max_width, 2)  # at least 2 chars for clean alignment

        lines = [f"{str(val).rjust(max_width)}  {acc.capitalize()}" for acc, val in results.items()]
        table = "<tt>" + "\n".join(lines) + "</tt>"
        next_check = get_next_schedule_time(end_time)
        body = f"{table}\n\nNext check at {next_check}"

    return title, body


def send_desktop_notification(
    title: str,
    body: str,
    icon: str = "mail-unread",
    expire_time_ms: int = 7000,
) -> bool:
    """
    Send desktop notification using FreeDesktop specification.
    Prefers notify-send if available, otherwise falls back to gdbus.
    """
    # 1. Try notify-send
    notify_send = shutil.which("notify-send")
    if notify_send:
        cmd = [
            notify_send,
            "-a",
            "Himalaya",
            "-i",
            icon,
            "-t",
            str(expire_time_ms),
            title,
            body,
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return True
        except Exception as e:
            sys.stderr.write(f"notify-send failed: {e}\n")

    # 2. Try gdbus (standard GLib / DBus client on virtually all Linux distros)
    gdbus = shutil.which("gdbus")
    if gdbus:
        cmd = [
            gdbus,
            "call",
            "--session",
            "--dest",
            "org.freedesktop.Notifications",
            "--object-path",
            "/org/freedesktop/Notifications",
            "--method",
            "org.freedesktop.Notifications.Notify",
            "Himalaya",
            "0",
            icon,
            title,
            body,
            "[]",
            "{}",
            str(expire_time_ms),
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return True
            else:
                sys.stderr.write(f"gdbus notification call failed: {res.stderr.strip()}\n")
        except Exception as e:
            sys.stderr.write(f"gdbus call exception: {e}\n")

    # 3. Try dbus-send
    dbus_send = shutil.which("dbus-send")
    if dbus_send:
        cmd = [
            dbus_send,
            "--session",
            "--print-reply",
            "--dest=org.freedesktop.Notifications",
            "/org/freedesktop/Notifications",
            "org.freedesktop.Notifications.Notify",
            "string:Himalaya",
            "uint32:0",
            f"string:{icon}",
            f"string:{title}",
            f"string:{body}",
            "array:string:",
            "dict:string:string:",
            f"int32:{expire_time_ms}",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if res.returncode == 0:
                return True
        except Exception as e:
            sys.stderr.write(f"dbus-send failed: {e}\n")

    return False


def check_emails(
    hours: float = 3.0,
    dry_run: bool = False,
    quiet: bool = False,
    accounts: list[str] | None = None,
) -> Dict[str, Union[int, str]]:
    """Execute the check across accounts with guardrails and dispatch notification."""
    now_utc = datetime.now(timezone.utc)
    cutoff = now_utc - timedelta(hours=hours)

    now_local = datetime.now()
    start_local = now_local - timedelta(hours=hours)

    if not accounts:
        try:
            accounts = get_accounts()
        except Exception as e:
            sys.stderr.write(f"Failed to discover accounts: {e}\n")
            accounts = []

    results: Dict[str, Union[int, str]] = {}
    if not accounts:
        results["all"] = "ERR"
    elif not is_online(max_wait=10.0):
        sys.stderr.write("Network offline: Internet connectivity or DNS resolution unavailable after wait period.\n")
        for acc in accounts:
            results[acc] = "OFF"
    else:
        for acc in accounts:
            try:
                count = count_recent_emails(acc, cutoff)
                results[acc] = count
            except Exception as e:
                # Log detailed error for systemd journal / debugging
                sys.stderr.write(f"Error fetching account '{acc}': {e}\n")
                results[acc] = "ERR"

    title, body = format_notification(results, start_time=start_local, end_time=now_local)

    if not quiet:
        print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {title}")
        print(body)

    if not dry_run:
        sent = send_desktop_notification(title, body)
        if not sent:
            sys.stderr.write("Warning: Failed to send desktop notification.\n")

    return results


def update_self() -> int:
    """
    Pull latest changes from git (main branch) and reload/restart systemd user timer.
    """
    repo_dir = Path(__file__).resolve().parent
    git_bin = shutil.which("git")
    if not git_bin:
        sys.stderr.write("git binary not found. Please install git or pull changes manually.\n")
        return 1

    # 1. Guard: Check for uncommitted changes
    status_res = subprocess.run([git_bin, "-C", str(repo_dir), "status", "--porcelain"], capture_output=True, text=True)
    if status_res.stdout.strip():
        sys.stderr.write("Error: You have uncommitted changes in your repository.\n"
                         "Please commit, stash, or discard them before updating.\n")
        return 1

    # 2. Check current branch and ensure we are on main
    branch_res = subprocess.run([git_bin, "-C", str(repo_dir), "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
    current_branch = branch_res.stdout.strip()
    if current_branch != "main":
        print(f"Switching from '{current_branch}' to 'main' branch...")
        co_res = subprocess.run([git_bin, "-C", str(repo_dir), "checkout", "main"], capture_output=True, text=True)
        if co_res.returncode != 0:
            sys.stderr.write(f"Failed to switch to main branch:\n{co_res.stderr.strip()}\n")
            return 1

    # 3. Pull latest changes from origin main
    print("Pulling latest changes from origin/main...")
    res = subprocess.run([git_bin, "-C", str(repo_dir), "pull", "origin", "main"], capture_output=True, text=True)
    if res.returncode != 0:
        sys.stderr.write(f"git pull failed:\n{res.stderr.strip()}\n")
        return 1

    print(res.stdout.strip())

    systemctl = shutil.which("systemctl")
    if systemctl:
        print("Reloading systemd user daemon and restarting timer...")
        subprocess.run([systemctl, "--user", "daemon-reload"], capture_output=True)
        subprocess.run([systemctl, "--user", "restart", "himalaya-notification.timer"], capture_output=True)
        print("✓ Systemd timer reloaded and active.")

    print("✓ himalaya-notification is up to date!")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Himalaya email count notification tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command")

    # Command: check
    check_parser = subparsers.add_parser("check", help="Check emails and send notification")
    check_parser.add_argument(
        "--hours",
        type=float,
        default=3.0,
        help="Window in hours to count emails (default: 3.0)",
    )
    check_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print output to stdout without sending a desktop notification",
    )
    check_parser.add_argument(
        "--quiet",
        action="store_true",
        help="Do not print output to stdout",
    )
    check_parser.add_argument(
        "--account",
        "-a",
        action="append",
        dest="accounts",
        help="Specific account(s) to check (can be specified multiple times)",
    )

    # Command: test-notify
    subparsers.add_parser("test-notify", help="Send a test notification to verify setup")

    # Command: status
    subparsers.add_parser("status", help="Show systemd timer status and schedule")

    # Command: update
    subparsers.add_parser("update", help="Pull latest updates from Git and reload systemd service")

    args = parser.parse_args()

    if args.command == "check" or args.command is None:
        hours = getattr(args, "hours", 3.0)
        dry_run = getattr(args, "dry_run", False)
        quiet = getattr(args, "quiet", False)
        accounts = getattr(args, "accounts", None)
        results = check_emails(hours=hours, dry_run=dry_run, quiet=quiet, accounts=accounts)
        # If any account errored, exit code 1 can be used if desired, but for cron/systemd
        # we still successfully delivered the notification showing ERR, so return 0
        return 0

    elif args.command == "test-notify":
        print("Sending test notification...")
        sample_results = {"official": 2, "personal": 0}
        now_local = datetime.now()
        start_local = now_local - timedelta(hours=3)
        title, body = format_notification(sample_results, start_time=start_local, end_time=now_local)
        ok = send_desktop_notification(title, body)
        if ok:
            print("✓ Notification sent successfully.")
            return 0
        else:
            print("✗ Failed to send notification. Check notification daemon and DBus session.")
            return 1

    elif args.command == "status":
        systemctl = shutil.which("systemctl")
        if not systemctl:
            print("systemctl not found on this system.")
            return 1
        cmd = [systemctl, "--user", "status", "himalaya-notification.timer"]
        res = subprocess.run(cmd)
        return res.returncode

    elif args.command == "update":
        return update_self()

    else:
        parser.print_help()
        return 0


if __name__ == "__main__":
    sys.exit(main())
