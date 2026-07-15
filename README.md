<div align="center">

<img src="https://raw.githubusercontent.com/Gooseymille10/OpenPisoWifi/main/assets/logo.svg" alt="OpenPisoWifi Logo" width="80"/>

# OpenPisoWifi

**Open source Piso WiFi captive portal — no ₱10,000 black box required.**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.x-blue?logo=python)](https://python.org)
[![Platform](https://img.shields.io/badge/Platform-Raspberry%20Pi%20%7C%20Orange%20Pi-red)](https://www.raspberrypi.com)
[![GitHub](https://img.shields.io/badge/Built%20by-Gooseymille-black?logo=github)](https://github.com/Gooseymille10)

</div>

---

## What is this?

Proprietary Piso WiFi vendo machines cost **₱10,000+** — a cheap SBC, a ₱300 coin acceptor, locked firmware, and a ₱2,000 software license slapped together in a plastic box.

**OpenPisoWifi** does the same thing for free, on hardware you probably already have.

- **Admin approves devices** from a mobile-friendly web panel
- **Captive portal** auto-pops on client devices (iOS, Android, Windows, Linux)
- **1-hour sessions** tracked per MAC address via iptables
- **Brownout recovery** — auto-restarts after power loss
- **No coin slot needed** — owner manually grants access after payment

---

## How It Works

```
[Internet / ISP]
       ↓
   [Router]
       ↓ WiFi (wlan0) — Pi receives internet here
   [Raspberry Pi / Orange Pi]  ← runs OpenPisoWifi
       ↓ Ethernet (eth0) — clients connect here
   [Access Point / Switch]
       ↓ WiFi
   [Client Devices]
```

1. Client connects to WiFi → gets IP from Pi's DHCP
2. All DNS resolves to portal IP → captive portal popup appears
3. Client sees **"Pay to Owner"** page — no browsing yet
4. Owner opens `/admin` on their phone → sees the device → clicks **Grant 1 Hour**
5. iptables ACCEPT rule added for that MAC → client browses freely
6. After 1 hour, access is automatically revoked

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

**Total: ~₱2,400–5,800** vs ₱10,000+ for a proprietary vendo 😄

### Software
- Raspberry Pi OS / Armbian (Debian-based)
- Python 3.x
- Flask (installed by setup script)
- dnsmasq, iptables (installed by setup script)

---

## Quick Start

### 1. Clone the repo
```bash
git clone https://github.com/Gooseymille10/OpenPisoWifi.git
cd OpenPisoWifi
```

### 2. Copy to your Pi
```bash
scp -r OpenPisoWifi/ pi@<your-pi-ip>:/opt/pisowifi
```

### 3. Edit setup.sh
```bash
sudo nano /opt/pisowifi/setup.sh
```

Set these variables to match your setup:
```bash
WIFI_IFACE="wlan0"          # interface receiving internet (check with: ip link)
LAN_IFACE="eth0"            # interface facing AP/clients
PORTAL_IP="192.168.100.2"   # Pi's IP — must NOT be same as your router
ROUTER_IP="192.168.100.1"   # your home router's IP
```

### 4. Change the admin password
In `app.py`:
```python
ADMIN_PASS = hashlib.sha256("admin123".encode()).hexdigest()
# Change "admin123" to your own password ↑
```

### 5. Run setup (once, as root)
```bash
cd /opt/pisowifi
chmod +x setup.sh start.sh
sudo bash setup.sh
```

Setup will automatically:
- Install dependencies (Flask, dnsmasq, iptables-persistent)
- Configure eth0 as static IP
- Set up iptables rules (NAT, captive portal redirect, QUIC blocking)
- Configure dnsmasq (DHCP + DNS redirect)
- Install and enable systemd service
- Save all rules so they survive reboots and brownouts

### 6. Reboot and test
```bash
sudo reboot
```

After ~30 seconds, connect a device to your AP — the captive portal should appear automatically.

---

## Admin Panel

Access at `http://<PORTAL_IP>/admin`

| Feature | Description |
|---------|-------------|
| **Waiting for Approval** | Devices connected but not yet paid |
| **Active Sessions** | Approved devices with live countdown timers |
| **Grant 1 Hour** | Approve a device — starts their 1-hour session |
| **Revoke Access** | Immediately kick a device off |

The admin panel is **mobile-optimized** — use it from your phone while sitting at the counter.

---

## File Structure

```
OpenPisoWifi/
├── app.py              # Main Flask app (captive portal + admin)
├── setup.sh            # One-time setup script
├── start.sh            # Startup script (called by systemd on boot)
├── pisowifi.service    # Systemd service file
└── templates/
    ├── portal.html         # Client-facing portal page
    ├── admin_login.html    # Admin login page
    └── admin_dashboard.html # Admin dashboard
```

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

# View DHCP leases (connected clients)
cat /var/lib/misc/dnsmasq.leases

# Reset everything back to stock
sudo systemctl stop pisowifi
sudo iptables -F && sudo iptables -t nat -F
sudo iptables -P FORWARD ACCEPT && sudo iptables -P INPUT ACCEPT
```

---

## Troubleshooting

**Captive portal doesn't pop up automatically**
- Make sure your AP is in bridge/AP mode (not router mode) so traffic flows through the Pi
- Disable the AP's own DHCP server — only Pi's dnsmasq should hand out IPs
- Check clients are getting IPs in the Pi's subnet: `cat /var/lib/misc/dnsmasq.leases`

**Internet works before granting access**
- AP might still be in router mode and routing around the Pi
- Check client gateway: should be Pi's IP, not router's IP

**Slow internet after granting access**
- Already handled by MTU clamping in setup.sh
- If still slow, check: `sudo iptables -t mangle -L FORWARD -v`

**Portal breaks after reboot/brownout**
- Re-run `sudo bash setup.sh` to re-apply all rules
- Check service: `sudo systemctl status pisowifi`

**Pi loses internet when setup.sh runs**
- This is fixed in the latest version — dnsmasq is stopped before installing and only started after config is written

**eth0 grabbing wrong IP from router**
- Fixed by `denyinterfaces eth0` in dhcpcd.conf
- Check: `ip addr show eth0` — should only show `PORTAL_IP`

---

## Why Open Source?

Proprietary Piso WiFi vendors charge:
- ₱2,000+ for a software license
- ₱10,000–20,000 for a "complete unit"
- Sometimes a **cut of your earnings** through their ecosystem

All for what is essentially Flask + iptables + dnsmasq on a cheap SBC.

OpenPisoWifi gives small business owners — sari-sari stores, waiting sheds, carenderias — the same capability for free. You own your hardware, your software, and your earnings. 🇵🇭

---

## Contributing

PRs welcome! Some ideas for future features:
- [ ] Coin slot GPIO integration (for hardware vendo builds)
- [ ] Bandwidth limiting per session
- [ ] Session history / earnings tracker
- [ ] Multiple price tiers (₱5 = 1hr, ₱10 = 3hr, etc.)
- [ ] SMS notification when client connects
- [ ] Web-based config editor (no more nano)

---

## License

MIT — free to use, modify, and distribute.

---

<div align="center">

Built by [Gooseymille](https://github.com/Gooseymille10) · [YouTube](https://www.youtube.com/@GooseymilleonYT/featured)

*"Why pay ₱10,000 for a black box when it's just couple lines of code?"*

</div>
