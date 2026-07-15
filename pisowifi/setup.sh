#!/bin/bash
# ============================================================
#  Piso WiFi Setup Script
#  Run as root on Raspberry Pi / Orange Pi ONCE
# ============================================================

set -e

# ── EDIT THESE ───────────────────────────────────────────────
WIFI_IFACE="wlan0"          # interface receiving internet from router
LAN_IFACE="eth0"            # interface facing AP/clients
PORTAL_IP="192.168.100.2"   # Pi's LAN IP (must differ from router)
ROUTER_IP="192.168.100.1"   # your home router IP
# ─────────────────────────────────────────────────────────────

INSTALL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "[1/7] Locking DNS so we keep internet throughout setup..."
chattr -i /etc/resolv.conf 2>/dev/null || true
echo "nameserver 8.8.8.8" > /etc/resolv.conf
echo "nameserver 8.8.4.4" >> /etc/resolv.conf
chattr +i /etc/resolv.conf

echo "[2/7] Configuring eth0 as static (no DHCP, no dhcpcd restart)..."
# Clean previous pisowifi entries
sed -i '/# Piso WiFi/,/^$/d' /etc/dhcpcd.conf 2>/dev/null || true
sed -i "/denyinterfaces $LAN_IFACE/d" /etc/dhcpcd.conf 2>/dev/null || true

# Write eth0 static config — dhcpcd picks this up without a restart
# We use 'inform' mode so dhcpcd doesn't touch wlan0 at all
cat >> /etc/dhcpcd.conf << DHCPEOF

# Piso WiFi — eth0 static, never gets DHCP from router
denyinterfaces $LAN_IFACE
DHCPEOF

# Configure eth0 directly via ip commands — no dhcpcd restart needed
dhclient -r "$LAN_IFACE" 2>/dev/null || true
ip addr flush dev "$LAN_IFACE" 2>/dev/null || true
ip addr add "$PORTAL_IP/24" dev "$LAN_IFACE" 2>/dev/null || true
ip link set "$LAN_IFACE" up

# Remove any wrong default route via eth0 only
ip route del default dev "$LAN_IFACE" 2>/dev/null || true

echo "[3/7] Enabling IP forwarding..."
echo 1 > /proc/sys/net/ipv4/ip_forward
grep -q "^net.ipv4.ip_forward" /etc/sysctl.conf \
  && sed -i 's/^net.ipv4.ip_forward.*/net.ipv4.ip_forward=1/' /etc/sysctl.conf \
  || echo "net.ipv4.ip_forward=1" >> /etc/sysctl.conf

echo "[4/7] Installing dependencies..."
# Stop dnsmasq before installing to prevent it from grabbing wlan0
systemctl stop dnsmasq 2>/dev/null || true
apt-get update -qq
apt-get install -y python3 python3-pip dnsmasq iptables iptables-persistent -qq
pip3 install flask --quiet
# Keep dnsmasq stopped until we configure it properly
systemctl stop dnsmasq 2>/dev/null || true

echo "[5/7] Setting up iptables..."
iptables -t nat -F
iptables -t mangle -F
iptables -F FORWARD
iptables -F INPUT
iptables -F OUTPUT

# NAT masquerade
iptables -t nat -A POSTROUTING -o "$WIFI_IFACE" -j MASQUERADE

# FORWARD: block by default
iptables -P FORWARD DROP
iptables -A FORWARD -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT

# Fix MTU for WiFi-to-WiFi routing (prevents slowness)
iptables -t mangle -A FORWARD -p tcp --tcp-flags SYN,RST SYN -j TCPMSS --clamp-mss-to-pmtu

# Block QUIC for unapproved clients
iptables -A FORWARD -i "$LAN_IFACE" -p udp --dport 443 \
  -j REJECT --reject-with icmp-port-unreachable

# Redirect HTTP/HTTPS from unapproved clients to portal
iptables -t nat -A PREROUTING -i "$LAN_IFACE" -p tcp --dport 80 \
  -j DNAT --to-destination "$PORTAL_IP:80"
iptables -t nat -A PREROUTING -i "$LAN_IFACE" -p tcp --dport 443 \
  -j DNAT --to-destination "$PORTAL_IP:80"

# Allow portal to receive connections
iptables -A INPUT -i "$LAN_IFACE" -p tcp --dport 80  -j ACCEPT
iptables -A INPUT -i "$LAN_IFACE" -p udp --dport 53  -j ACCEPT
iptables -A INPUT -i "$LAN_IFACE" -p tcp --dport 53  -j ACCEPT
iptables -A INPUT -i lo -j ACCEPT
iptables -A INPUT -m conntrack --ctstate RELATED,ESTABLISHED -j ACCEPT

echo "[6/7] Configuring dnsmasq..."
# Write config BEFORE starting dnsmasq so it never runs unconfigured
cat > /etc/dnsmasq.d/pisowifi.conf << DNSEOF
# ONLY bind to eth0 — never touch wlan0
interface=$LAN_IFACE
bind-interfaces
except-interface=$WIFI_IFACE
except-interface=lo

# Real upstream DNS
server=8.8.8.8
server=8.8.4.4

# DHCP for clients
dhcp-range=192.168.100.10,192.168.100.200,1h
dhcp-option=option:router,$PORTAL_IP
dhcp-option=option:dns-server,$PORTAL_IP

# Redirect ALL client DNS to portal
address=/#/$PORTAL_IP
address=/piso.wifi/$PORTAL_IP
DNSEOF

# Now start dnsmasq with correct config already in place
systemctl start dnsmasq
systemctl enable dnsmasq

echo "[7/7] Installing Piso WiFi service..."
mkdir -p /var/lib/pisowifi

cat > /etc/systemd/system/pisowifi.service << SVCEOF
[Unit]
Description=Piso WiFi Captive Portal
After=network-online.target dnsmasq.service netfilter-persistent.service
Wants=network-online.target dnsmasq.service netfilter-persistent.service

[Service]
Type=simple
User=root
WorkingDirectory=$INSTALL_DIR
# Wait for eth0 to be fully up before starting
ExecStartPre=/bin/bash $INSTALL_DIR/start.sh
ExecStart=/usr/bin/python3 $INSTALL_DIR/app.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
SVCEOF

netfilter-persistent save
systemctl enable netfilter-persistent
systemctl daemon-reload
systemctl enable pisowifi
systemctl restart pisowifi

echo ""
ping -c 2 8.8.8.8 && echo "✅ Pi internet OK" || echo "❌ Pi internet broken"
echo ""
echo "✅ Setup complete!"
echo "   Admin panel:  http://$PORTAL_IP/admin"
echo "   Creds:        admin / admin123"
echo "   ⚠️  Change ADMIN_PASS in app.py before going live!"
echo ""
echo "   systemctl status pisowifi   → check status"
echo "   journalctl -u pisowifi -f   → live logs"

# Enable network-online.target so service waits for full network before starting
systemctl enable systemd-networkd-wait-online.service 2>/dev/null || true
