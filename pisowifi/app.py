#!/usr/bin/env python3
"""
Piso WiFi Captive Portal
Runs on Orange Pi - intercepts LAN clients and requires admin approval.
"""

from flask import Flask, render_template, request, redirect, session, jsonify
import subprocess
import sqlite3
import hashlib
import os
import time
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.secret_key = os.urandom(24)

# ── Config ──────────────────────────────────────────────────────────────────
LAN_IFACE   = "eth0"          # interface facing LAN clients
WIFI_IFACE  = "wlan0"         # interface receiving internet
PORTAL_IP   = "192.168.100.2" # this device's LAN IP
SESSION_HOURS = 1             # hours per paid session
ADMIN_USER  = "admin"
ADMIN_PASS  = hashlib.sha256("admin123".encode()).hexdigest()  # change this!
DB_PATH     = "/var/lib/pisowifi/sessions.db"
# ────────────────────────────────────────────────────────────────────────────

os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)


# ── Database ─────────────────────────────────────────────────────────────────
def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                mac       TEXT    NOT NULL,
                hostname  TEXT,
                ip        TEXT,
                granted_at TEXT,
                expires_at TEXT,
                granted_by TEXT DEFAULT 'admin'
            );

            CREATE TABLE IF NOT EXISTS history (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                mac        TEXT NOT NULL,
                hostname   TEXT,
                ip         TEXT,
                started_at TEXT,
                ended_at   TEXT,
                duration   INTEGER
            );
        """)

init_db()


# ── Helpers ───────────────────────────────────────────────────────────────────
def get_mac_from_ip(ip):
    """Read ARP table to get MAC from IP."""
    try:
        with open("/proc/net/arp") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if parts[0] == ip:
                    return parts[3].lower()
    except Exception:
        pass
    # Fallback: ping first to populate ARP
    try:
        subprocess.run(["ping", "-c1", "-W1", ip], capture_output=True)
        with open("/proc/net/arp") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if parts[0] == ip:
                    return parts[3].lower()
    except Exception:
        pass
    return None

def get_hostname(ip):
    try:
        result = subprocess.run(["nslookup", ip], capture_output=True, text=True, timeout=2)
        for line in result.stdout.splitlines():
            if "name =" in line:
                return line.split("name =")[-1].strip().rstrip(".")
    except Exception:
        pass
    return ip  # fallback to IP if no hostname

def is_allowed(mac):
    """Check if MAC has an active (non-expired) session."""
    if not mac:
        return False
    with get_db() as db:
        row = db.execute(
            "SELECT expires_at FROM sessions WHERE mac=? ORDER BY expires_at DESC LIMIT 1",
            (mac,)
        ).fetchone()
    if not row:
        return False
    expires = datetime.fromisoformat(row["expires_at"])
    return datetime.now() < expires

def allow_mac(mac, ip, hostname=None):
    """Grant internet access to a MAC via iptables and record in DB."""
    now = datetime.now()
    expires = now + timedelta(hours=SESSION_HOURS)

    # Allow FORWARD traffic out to internet for this MAC
    subprocess.run([
        "iptables", "-I", "FORWARD", "1",
        "-i", LAN_IFACE, "-o", WIFI_IFACE,
        "-m", "mac", "--mac-source", mac,
        "-j", "ACCEPT"
    ], check=False)

    # Exempt from HTTP redirect
    subprocess.run([
        "iptables", "-t", "nat", "-I", "PREROUTING", "1",
        "-i", LAN_IFACE,
        "-m", "mac", "--mac-source", mac,
        "-p", "tcp", "--dport", "80",
        "-j", "RETURN"
    ], check=False)

    # Exempt from HTTPS redirect
    subprocess.run([
        "iptables", "-t", "nat", "-I", "PREROUTING", "1",
        "-i", LAN_IFACE,
        "-m", "mac", "--mac-source", mac,
        "-p", "tcp", "--dport", "443",
        "-j", "RETURN"
    ], check=False)

    # Exempt from QUIC block so approved clients can use QUIC too
    subprocess.run([
        "iptables", "-I", "FORWARD", "1",
        "-i", LAN_IFACE,
        "-m", "mac", "--mac-source", mac,
        "-p", "udp", "--dport", "443",
        "-j", "ACCEPT"
    ], check=False)

    # Redirect approved client DNS to real DNS (8.8.8.8) instead of dnsmasq
    # dnsmasq redirects everything to portal IP which causes slow DNS for approved clients
    subprocess.run([
        "iptables", "-t", "nat", "-I", "PREROUTING", "1",
        "-i", LAN_IFACE,
        "-m", "mac", "--mac-source", mac,
        "-p", "udp", "--dport", "53",
        "-j", "DNAT", "--to-destination", "8.8.8.8:53"
    ], check=False)
    subprocess.run([
        "iptables", "-t", "nat", "-I", "PREROUTING", "1",
        "-i", LAN_IFACE,
        "-m", "mac", "--mac-source", mac,
        "-p", "tcp", "--dport", "53",
        "-j", "DNAT", "--to-destination", "8.8.8.8:53"
    ], check=False)

    with get_db() as db:
        db.execute(
            "INSERT INTO sessions (mac, hostname, ip, granted_at, expires_at) VALUES (?,?,?,?,?)",
            (mac, hostname or ip, ip, now.isoformat(), expires.isoformat())
        )

def revoke_mac(mac):
    """Remove all iptables rules for this MAC."""
    cmds = [
        # FORWARD rules
        ["iptables", "-D", "FORWARD", "-i", LAN_IFACE, "-o", WIFI_IFACE,
         "-m", "mac", "--mac-source", mac, "-j", "ACCEPT"],
        ["iptables", "-D", "FORWARD", "-i", LAN_IFACE,
         "-m", "mac", "--mac-source", mac, "-p", "udp", "--dport", "443", "-j", "ACCEPT"],
        # NAT exemptions
        ["iptables", "-t", "nat", "-D", "PREROUTING", "-i", LAN_IFACE,
         "-m", "mac", "--mac-source", mac, "-p", "tcp", "--dport", "80", "-j", "RETURN"],
        ["iptables", "-t", "nat", "-D", "PREROUTING", "-i", LAN_IFACE,
         "-m", "mac", "--mac-source", mac, "-p", "tcp", "--dport", "443", "-j", "RETURN"],
        ["iptables", "-t", "nat", "-D", "PREROUTING", "-i", LAN_IFACE,
         "-m", "mac", "--mac-source", mac, "-p", "udp", "--dport", "53",
         "-j", "DNAT", "--to-destination", "8.8.8.8:53"],
        ["iptables", "-t", "nat", "-D", "PREROUTING", "-i", LAN_IFACE,
         "-m", "mac", "--mac-source", mac, "-p", "tcp", "--dport", "53",
         "-j", "DNAT", "--to-destination", "8.8.8.8:53"],
    ]
    for cmd in cmds:
        subprocess.run(cmd, check=False)

def get_active_sessions():
    with get_db() as db:
        rows = db.execute(
            "SELECT * FROM sessions WHERE expires_at > ? ORDER BY granted_at DESC",
            (datetime.now().isoformat(),)
        ).fetchall()
    return [dict(r) for r in rows]

def get_pending_devices():
    """Devices in ARP table that don't have an active session."""
    active_macs = {s["mac"] for s in get_active_sessions()}
    pending = []
    try:
        with open("/proc/net/arp") as f:
            for line in f.readlines()[1:]:
                parts = line.split()
                if len(parts) < 4:
                    continue
                ip, _, flags, mac = parts[0], parts[1], parts[2], parts[3]
                if flags == "0x0" or mac == "00:00:00:00:00:00":
                    continue  # stale entry
                if ip == PORTAL_IP:
                    continue  # skip self
                if mac.lower() not in active_macs:
                    pending.append({
                        "ip": ip,
                        "mac": mac.lower(),
                        "hostname": get_hostname(ip)
                    })
    except Exception:
        pass
    return pending


# ── Auth decorator ────────────────────────────────────────────────────────────
def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("admin"):
            return redirect("/admin/login")
        return f(*args, **kwargs)
    return decorated


# ── Captive portal redirect ───────────────────────────────────────────────────

# OS-specific captive portal probe paths.
# DNS redirects ALL domains to this Pi, so these paths arrive here regardless
# of which hostname the OS was probing (gstatic, apple, msft, etc.)
PROBE_PATHS = {
    # Android / Chrome
    "/generate_204",
    "/gen_204",
    "/connectivitycheck/generate_204",
    # iOS / macOS
    "/hotspot-detect.html",
    "/library/test/success.html",
    "/bag",
    # Windows
    "/connecttest.txt",
    "/ncsi.txt",
    "/redirect",
}

@app.before_request
def captive_portal_check():
    """Intercept every request from an unpaid client and redirect to portal."""
    # Always let admin routes and static files through
    if request.path.startswith("/admin") or request.path.startswith("/static"):
        return

    client_ip  = request.remote_addr
    client_mac = get_mac_from_ip(client_ip)

    if is_allowed(client_mac):
        # Paid client — if they hit a probe path, return 204 so OS knows it's free
        if request.path in PROBE_PATHS:
            return "", 204
        return  # let all other traffic through normally

    # Unpaid client hitting a known probe path → redirect to portal
    # This is what triggers the automatic popup on phones
    if request.path in PROBE_PATHS or request.path != "/portal":
        return redirect(f"http://{PORTAL_IP}/portal", code=302)


# ── Client routes ─────────────────────────────────────────────────────────────
@app.route("/portal")
def portal():
    client_ip  = request.remote_addr
    client_mac = get_mac_from_ip(client_ip)
    if is_allowed(client_mac):
        return redirect("http://www.google.com")
    return render_template("portal.html", ip=client_ip, mac=client_mac)

# Explicit probe routes as fallback (in case before_request doesn't catch them)
@app.route("/generate_204")
@app.route("/gen_204")
@app.route("/hotspot-detect.html")
@app.route("/ncsi.txt")
@app.route("/connecttest.txt")
@app.route("/connectivitycheck/generate_204")
def captive_probe():
    client_ip  = request.remote_addr
    client_mac = get_mac_from_ip(client_ip)
    if is_allowed(client_mac):
        return "", 204
    return redirect(f"http://{PORTAL_IP}/portal", code=302)


# ── Admin routes ──────────────────────────────────────────────────────────────
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        pw_hash  = hashlib.sha256(password.encode()).hexdigest()
        if username == ADMIN_USER and pw_hash == ADMIN_PASS:
            session["admin"] = True
            return redirect("/admin")
        error = "Wrong username or password."
    return render_template("admin_login.html", error=error)

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin/login")

@app.route("/admin")
@admin_required
def admin_dashboard():
    active  = get_active_sessions()
    pending = get_pending_devices()
    return render_template("admin_dashboard.html",
                           active=active, pending=pending,
                           now=datetime.now())

@app.route("/admin/grant", methods=["POST"])
@admin_required
def admin_grant():
    mac      = request.form.get("mac", "").lower()
    ip       = request.form.get("ip", "")
    hostname = request.form.get("hostname", ip)
    if mac and ip:
        allow_mac(mac, ip, hostname)
    return redirect("/admin")

@app.route("/admin/revoke", methods=["POST"])
@admin_required
def admin_revoke():
    mac = request.form.get("mac", "").lower()
    if mac:
        revoke_mac(mac)
        with get_db() as db:
            db.execute(
                "UPDATE sessions SET expires_at=? WHERE mac=?",
                (datetime.now().isoformat(), mac)
            )
    return redirect("/admin")

@app.route("/admin/api/status")
@admin_required
def api_status():
    return jsonify({
        "active":  get_active_sessions(),
        "pending": get_pending_devices()
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=80, debug=False)
