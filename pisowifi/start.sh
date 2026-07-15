#!/bin/bash
# ============================================================
#  Piso WiFi Startup Script
#  Called by systemd before starting app.py
#  Ensures eth0 is properly configured on every boot
# ============================================================

LAN_IFACE="eth0"
PORTAL_IP="192.168.100.2"
WIFI_IFACE="wlan0"
ROUTER_IP="192.168.100.1"

echo "[pisowifi] Waiting for wlan0 to come up..."
for i in $(seq 1 30); do
    if ip link show "$WIFI_IFACE" | grep -q "state UP"; then
        echo "[pisowifi] wlan0 is up"
        break
    fi
    sleep 1
done

echo "[pisowifi] Configuring eth0..."
# Kill any DHCP client on eth0
dhclient -r "$LAN_IFACE" 2>/dev/null || true
pkill -f "dhclient.*$LAN_IFACE" 2>/dev/null || true

# Set static IP on eth0
ip addr flush dev "$LAN_IFACE" 2>/dev/null || true
ip addr add "$PORTAL_IP/24" dev "$LAN_IFACE" 2>/dev/null || true
ip link set "$LAN_IFACE" up

# Remove any wrong default route via eth0
ip route del default dev "$LAN_IFACE" 2>/dev/null || true

echo "[pisowifi] Ensuring IP forwarding is on..."
echo 1 > /proc/sys/net/ipv4/ip_forward

echo "[pisowifi] Ensuring DNS is correct..."
chattr -i /etc/resolv.conf 2>/dev/null || true
echo "nameserver 8.8.8.8" > /etc/resolv.conf
echo "nameserver 8.8.4.4" >> /etc/resolv.conf
chattr +i /etc/resolv.conf

echo "[pisowifi] Ready — starting portal..."
