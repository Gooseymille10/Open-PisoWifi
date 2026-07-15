# 📶 OpenPisoWifi

> An open source captive portal for Piso WiFi — no ₱10,000 black box required.

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.x-blue.svg)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%20%7C%20Orange%20Pi-red.svg)](https://www.raspberrypi.com)
[![Built by](https://img.shields.io/badge/Built%20by-Gooseymille-black.svg)](https://github.com/Gooseymille10)

---

## 📖 Table of Contents

- [About](#about)
- [How It Works](#how-it-works)
- [Requirements](#requirements)
- [Installation](#installation)
- [Configuration](#configuration)
- [File Structure](#file-structure)
- [Admin Panel](#admin-panel)
- [Useful Commands](#useful-commands)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

---

## About

Proprietary Piso WiFi vendo machines cost **₱10,000+** — a cheap SBC, a ₱300 coin acceptor from Shopee, locked firmware, and a ₱2,000 software license slapped together in a plastic box that you don't own.

**OpenPisoWifi** does the same thing for free, on hardware you probably already have.

- Admin manually approves devices from a **mobile-friendly web panel**
- **Captive portal** auto-pops on client devices (iOS, Android, Windows, Linux)
- **Per-MAC session tracking** via iptables — 1 hour per approval
- **Brownout recovery** — auto-restarts after power loss, no manual intervention
- **No coin slot needed** — owner grants access after receiving payment

---

## How It Works

```
[Internet / ISP]
       ↓
   [Router]
       ↓ wlan0 — Pi receives internet here
   [Raspberry Pi / Orange Pi]  ← runs OpenPisoWifi
       ↓ eth0 — wired to AP
   [Access Point]
       ↓ WiFi
   [Client Devices]
```

1. Client connects to WiFi → gets IP from Pi's dnsmasq
2. All DNS resolves to portal IP → captive portal popup appears automatically
3. Client sees **"Pay to Owner"** page — no browsing yet
4. Owner opens `/admin` on their phone → clicks **Grant 1 Hour**
5. iptables ACCEPT + RETURN exemption rules added for that MAC
6. Client browses freely — HTTP, HTTPS, QUIC all work
7. After 1 hour, access is automatically revoked

---

## Requirements

### Hardware

| Component | Example | Est. Cost |
|-----------|---------|-----------|
| SBC | Raspberry Pi 3/4/5, Orange Pi | ₱1,500–3,000 |
| MicroSD Card | 8GB+ Class 10 | ₱150–300 |
| Access Point | Any router in AP mode | ₱500–2,000 |
| Ethernet cable | Cat5e/6 | ₱50–100 |
| Power supply | 5V/3A USB-C | ₱200–400 |

**Total: ~₱2,400–5,800** vs ₱10,000+ for a proprietary vendo.

### Software

- Raspberry Pi OS / Armbian (Debian-based)
- Python 3.x
- Flask, dnsmasq, iptables *(installed automatically by setup script)*

---

## Installation

### 1. Clone the repo
```bash
git clone https://github.com/Gooseymille10/OpenPisoWifi.git
```

### 2. Copy to your Pi
```bash
scp -r OpenPisoWifi/ pi@<your-pi-ip>:/opt/pisowifi
```

### 3. Edit configuration
```bash
sudo nano /opt/pisowifi/setup.sh
```

Set these variables:
```bash
WIFI_IFACE="wlan0"          # interface receiving internet (check: ip link)
LAN_IFACE="eth0"            # interface connected to your AP
PORTAL_IP="192.168.100.2"   # Pi's static IP — must differ from router IP
ROUTER_IP="192.168.100.1"   # your home router's IP
```

### 4. Run setup (once, as root)
```bash
cd /opt/pisowifi
chmod +x setup.sh start.sh
sudo bash setup.sh
```

### 5. Reboot
```bash
sudo reboot
```

Connect a device to your AP — the captive portal will appear automatically within a few seconds.

---

## Configuration

### Change the admin password
In `app.py`:
```python
ADMIN_PASS = hashlib.sha256("admin123".encode()).hexdigest()
#                            ↑ change this
```

### Change session duration
In `app.py`:
```python
SESSION_HOURS = 1   # change to however many hours you want
```

### Change session price display
In `templates/portal.html`:
```html
<div class="pay-price">₱5.00</div>
<div class="pay-duration">per hour of internet access</div>
```

---

## File Structure

```
OpenPisoWifi/
├── app.py                      # Main Flask app — portal logic, admin routes, iptables
├── setup.sh                    # One-time setup script
├── start.sh                    # Boot startup script (called by systemd)
├── pisowifi.service            # Systemd service file
├── LICENSE
├── README.md
└── templates/
    ├── portal.html             # Client-facing captive portal page
    ├── admin_login.html        # Admin login page
    └── admin_dashboard.html    # Admin dashboard — approve/revoke devices
```

---

## Admin Panel

Access at `http://<PORTAL_IP>/admin`

Default credentials: `admin` / `admin123` *(change this before going live)*

| Feature | Description |
|---------|-------------|
| **Waiting for Approval** | Devices connected but not yet paid |
| **Active Sessions** | Approved devices with live countdown timers |
| **Grant 1 Hour** | Approve a device — starts their session |
| **Revoke Access** | Immediately remove a device's internet access |

The admin panel is mobile-optimized — use it from your phone at the counter.

---

## Useful Commands

```bash
# Check if portal is running
sudo systemctl status pisowifi

# Restart portal
sudo systemctl restart pisowifi

# Live logs
sudo journalctl -u pisowifi -f

# View active iptables rules
sudo iptables -L FORWARD -v --line-numbers
sudo iptables -t nat -L PREROUTING -v --line-numbers

# View connected clients and their IPs
cat /var/lib/misc/dnsmasq.leases

# Full reset (wipes all rules back to stock)
sudo systemctl stop pisowifi
sudo iptables -F && sudo iptables -t nat -F && sudo iptables -t mangle -F
sudo iptables -P FORWARD ACCEPT && sudo iptables -P INPUT ACCEPT
```

---

## Troubleshooting

**Captive portal doesn't pop up automatically**
- Make sure AP is in bridge/AP mode — not router mode
- Disable the AP's own DHCP server — only Pi's dnsmasq should hand out IPs
- Verify clients are getting IPs from Pi: `cat /var/lib/misc/dnsmasq.leases`

**Client bypasses portal and gets internet without paying**
- AP is still in router mode and routing around the Pi
- Check: client gateway should be Pi's IP, not router's IP

**Internet stops working after granting access**
- Check iptables RETURN rules exist for client MAC: `sudo iptables -t nat -L PREROUTING -v`
- Restart service: `sudo systemctl restart pisowifi`

**Pi loses internet when setup.sh runs**
- Fixed in current version — dnsmasq is stopped before install, config is written before it starts
- Make sure `bind-interfaces` is in `/etc/dnsmasq.d/pisowifi.conf`

**Everything breaks after reboot/brownout**
- `start.sh` handles this — it waits for wlan0, re-applies eth0 static IP, and ensures IP forwarding is on before Flask starts
- Check service logs: `journalctl -u pisowifi -f`

**eth0 grabbing wrong IP from router**
- `denyinterfaces eth0` in `/etc/dhcpcd.conf` prevents this
- Verify: `ip addr show eth0` — should only show `PORTAL_IP`

---

## Contributing

PRs welcome! Some ideas for future features:

- [ ] Coin slot GPIO integration (for hardware vendo builds)
- [ ] Bandwidth limiting per session
- [ ] Session history and earnings tracker
- [ ] Multiple price tiers (₱5 = 1hr, ₱10 = 3hr, etc.)
- [ ] Web-based config editor

To contribute:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/your-feature`)
3. Commit your changes (`git commit -m 'Add your feature'`)
4. Push to the branch (`git push origin feature/your-feature`)
5. Open a Pull Request

---

## License

This project is licensed under the **GNU General Public License v3.0**.

See [LICENSE](LICENSE) for the full license text.

> Derivatives must also be open source under the same license — so no one can take this, lock it down, and sell it as a ₱10,000 black box. 😄

---

Made with 💜 by [Gooseymille](https://github.com/Gooseymille10) · [YouTube](https://www.youtube.com/@GooseymilleonYT/featured)
