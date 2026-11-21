#!/usr/bin/env bash
# Ensure the impersonated-cloud address exists before the bridge starts.
#
# The address is normally added by the network_ip_alias add-on or by hand. A
# container restart does not recreate it, so a missing alias leaves the dongle
# resolving to an unreachable .250 while the bridge itself looks healthy.
#
# NetworkManager also drops secondary addresses that are not part of its
# connection profile when the link flaps or the DHCP lease is renewed. Pass
# --watch SECONDS to re-check the address continuously and add it back.
set -euo pipefail

WATCH_INTERVAL=0
if [ "${1:-}" = "--watch" ]; then
    WATCH_INTERVAL="${2:-30}"
    shift 2
fi

LOCAL_IP="${LOCAL_CLOUD_IP:-}"
if [ -z "$LOCAL_IP" ]; then
    if [ "$#" -gt 0 ]; then exec "$@"; fi
    exit 0
fi

IFACE="${SNIFF_IFACE:-}"
if [ -z "$IFACE" ]; then
    IFACE="$(ip -4 route show default 2>/dev/null | awk '{print $5; exit}')"
fi
if [ -z "$IFACE" ]; then
    echo "[NET] LOCAL_CLOUD_IP=$LOCAL_IP but no interface was found (set SNIFF_IFACE)" >&2
    exit 1
fi

# Reuse the prefix of the interface's primary IPv4 address. Fall back to /24.
prefix() {
    local cidr value
    cidr="$(ip -o -4 addr show dev "$IFACE" scope global 2>/dev/null | awk '{print $4; exit}')"
    value="${cidr#*/}"
    if [ -z "$cidr" ] || [ "$value" = "$cidr" ] || ! [[ "$value" =~ ^[0-9]+$ ]]; then
        echo 24
    else
        echo "$value"
    fi
}

have_ip() {
    ip -o -4 addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -qx "$LOCAL_IP"
}

ensure_ip() {
    if have_ip; then
        return 0
    fi
    local value
    value="$(prefix)"
    echo "[NET] adding fake-cloud address $LOCAL_IP/$value to $IFACE"
    ip addr add "$LOCAL_IP/$value" dev "$IFACE"
}

ensure_ip

if [ "$WATCH_INTERVAL" -gt 0 ] 2>/dev/null; then
    (
        while sleep "$WATCH_INTERVAL"; do
            if ! ip link show dev "$IFACE" up >/dev/null 2>&1; then
                continue
            fi
            ensure_ip || true
        done
    ) &
    echo "[NET] watching fake-cloud address $LOCAL_IP on $IFACE every ${WATCH_INTERVAL}s"
fi

if [ "$#" -gt 0 ]; then
    exec "$@"
fi
