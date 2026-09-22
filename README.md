# Himalaya Email Notification

A lightweight, OS-agnostic, zero-dependency periodic email notification tool for [`himalaya-cli`](https://github.com/pimalaya/himalaya).

It runs in the background every 3 hours, checks all configured accounts, counts emails received within that 3-hour window, and sends a sleek desktop notification.

```
Himalaya (App banner)
16:25 – 19:25

 2  Official
 0  Personal

Next check at 21:00
```

---

## Features

- **Exact Time Window**: Shows the precise 3-hour period inspected (e.g. `16:25 – 19:25`).
- **2-Column Monospace Table**: Count right-aligned, account name left-aligned with monospaced precision.
- **Next Check Schedule**: Footer indicates when the next 3-hour systemd check will run.
- **Error Guardrails**: Isolated per-account error handling with timeouts. Shows `ERR` if an account query fails or times out—only displays `0` when zero emails were verified.
- **OS Agnostic (Universal Linux)**: Uses FreeDesktop Notifications (`org.freedesktop.Notifications`) with multi-tier fallback (`notify-send` -> `gdbus` -> `dbus-send`). Compatible with COSMIC, GNOME, KDE Plasma, XFCE, Sway, Hyprland, i3, etc.
- **No `sudo` Required**: Operates 100% in user-space (`~/.config/systemd/user`).
- **Zero External Dependencies**: Powered purely by Python 3 standard library.
- **Reliable Scheduling**: Configured via `systemd --user` timer with `Persistent=true` so missed checks run immediately after waking from sleep.

---

## Quickstart

### 1. Clone & Install

```bash
git clone https://github.com/arimaone/himalaya-notification.git
cd himalaya-notification
./install.sh
```

`install.sh` runs prerequisite checks (Python 3.8+, `himalaya`, configured accounts, DBus notifications, and user systemd) before configuring and activating the systemd timer.

---

## Manual Usage & CLI Options

You can invoke the script directly anytime:

```bash
# Check emails and send desktop notification (3h window by default)
./himalaya_notify.py check

# Dry-run: print to terminal without sending a notification
./himalaya_notify.py check --dry-run

# Custom window (e.g. check last 1 hour or 6 hours)
./himalaya_notify.py check --hours 1 --dry-run

# Check specific accounts only
./himalaya_notify.py check -a official -a personal

# Send a test desktop notification to verify desktop popup
./himalaya_notify.py test-notify

# View systemd timer status and next schedule
./himalaya_notify.py status
```

---

## Managing the Service

### View Timer Schedule
```bash
systemctl --user list-timers himalaya-notification.timer
```

### View Execution Logs
```bash
journalctl --user -u himalaya-notification.service -f
```

### Trigger an Immediate Check via Systemd
```bash
systemctl --user start himalaya-notification.service
```

---

## Running Unit Tests

```bash
python3 -m unittest discover -s . -p "test_*.py" -v
```

---

## Uninstallation

To cleanly stop, disable, and remove the systemd user timer:

```bash
./uninstall.sh
```

---

## Contributing

Contributions, feedback, and ideas are warmly welcomed!

- **Report bugs or suggest features**: Open an issue on GitHub.
- **Submit improvements**: Fork the repository, create a feature branch, and submit a pull request.
- **Run tests before opening a PR**:
  ```bash
  python3 -m unittest discover -s . -p "test_*.py" -v
  ```

---

## License

Distributed under the [MIT License](LICENSE). Built and maintained by [Arima](https://arima.one).
