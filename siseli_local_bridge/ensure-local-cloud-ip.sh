#!/usr/bin/env bash
# Ensure the impersonated-cloud address exists before the bridge starts.
#
# The address is normally added by the network_ip_alias add-on or by hand. A
# container restart does not recreate it, so a missing alias leaves the dongle
# resolving to an unreachable .250 while the bridge itself looks healthy.
set -euo pipefail

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
CIDR="$(ip -o -4 addr show dev "$IFACE" scope global 2>/dev/null | awk '{print $4; exit}')"
PREFIX="${CIDR#*/}"
if [ -z "$CIDR" ] || [ "$PREFIX" = "$CIDR" ] || ! [[ "$PREFIX" =~ ^[0-9]+$ ]]; then
    PREFIX=24
fi

if ip -o -4 addr show 2>/dev/null | awk '{print $4}' | cut -d/ -f1 | grep -qx "$LOCAL_IP"; then
    echo "[NET] fake-cloud address $LOCAL_IP already present"
else
    echo "[NET] adding fake-cloud address $LOCAL_IP/$PREFIX to $IFACE"
    ip addr add "$LOCAL_IP/$PREFIX" dev "$IFACE"
fi

if [ "$#" -gt 0 ]; then
    exec "$@"
fi
