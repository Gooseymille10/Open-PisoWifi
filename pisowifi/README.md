# Piso WiFi Captive Portal

Python-based captive portal for Orange Pi. Admin manually approves devices (no coin slot needed).

## How It Works

```
[Client device]
     |  LAN (eth0)
[Orange Pi]  ← receives internet via wlan0
     |  WiFi upstream
  [Router/ISP]
```

1. Client connects to LAN → gets DHCP IP from this device
2. All DNS resolves to portal IP (captive portal trick)
3. HTTP traffic is redirected to Flask app on port 80
4. Client sees "Pay to owner" page
5. Admin opens `/admin`, sees the device, clicks **Grant 1hr**
6. `iptables` ACCEPT rule added for that MAC
7. Client can now browse freely for 1 hour

---

## Quick Start

### 1. Copy files to Orange Pi
```bash
scp -r pisowifi/ orangepi@192.168.x.x:/opt/pisowifi
```

### 2. Run setup (once, as root)
```bash
cd /opt/pisowifi
chmod +x setup.sh
sudo ./setup.sh
```

Edit the variables at the top of `setup.sh` first:
- `WIFI_IFACE` – your WiFi interface (check with `ip link`)
- `LAN_IFACE`  – your LAN/ethernet interface
- `PORTAL_IP`  – IP you want this device to have on LAN side

### 3. Change the admin password
In `app.py`, find:
```python
ADMIN_PASS = hashlib.sha256("admin123".encode()).hexdigest()
```
Change `"admin123"` to your own password.

### 4. Start the portal
```bash
sudo python3 /opt/pisowifi/app.py
```

### 5. (Optional) Auto-start on boot
```bash
sudo cp pisowifi.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable pisowifi
sudo systemctl start pisowifi
```

---

## URLs

| URL | Who | What |
|-----|-----|-------|
| `http://anything/` | Client | Portal page (pay to owner) |
| `http://192.168.100.1/admin` | Admin | Login page |
| `http://192.168.100.1/admin` (logged in) | Admin | Dashboard |

---

## Admin Dashboard

- **Waiting for Approval** – devices on the LAN that haven't paid yet
- **Active Sessions** – approved devices with live countdown timers
- Click **Grant 1hr** to allow a device
- Click **Revoke** to kick a device off immediately

---

## Troubleshooting

**Devices not showing in "Waiting" list**
- Make sure they actually got a DHCP IP: check with `arp -n`
- Run `ping 192.168.100.x` from Orange Pi to populate ARP table

**iptables rules lost after reboot**
- Install `iptables-persistent`: `sudo apt install iptables-persistent`
- Or add `setup.sh` rules to a `@reboot` cron job

**Port 80 already in use**
- Check: `sudo lsof -i :80`
- Kill whatever is using it, or change `app.run(port=...)` in `app.py`

**"Network not available" on client after granting**
- Some phones cache the captive portal check — toggle WiFi off/on
