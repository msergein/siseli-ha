# ☀️ Siseli Local Bridge for Home Assistant

**English** | [Русский](README.ru.md)

[![Siseli Local Bridge](https://img.shields.io/badge/version-2.8.2-blue.svg?label=Siseli%20Local%20Bridge)](siseli_local_bridge/CHANGELOG.md)
[![HA Add-on](https://img.shields.io/badge/Home%20Assistant-Add--on-green.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey.svg)](LICENSE)

<img src="siseli_local_bridge/icon.png" alt="" width="140" align="right">

A Home Assistant add-on that reads your Siseli-compatible solar inverter **locally** and
publishes it to Home Assistant through MQTT auto-discovery. It runs in one of three modes:

- **Pass-through** — the dongle keeps talking to the vendor cloud and the official app
  keeps working; the add-on decodes the telemetry on its way.
- **100% local** — the add-on **replaces the vendor cloud**: the dongle only talks to your
  Home Assistant host, and the inverter's settings become Home Assistant controls. See
  [100% local mode](#100-local-mode).
- **Hybrid relay** — this fork's mode: fast H-block reads stay local, while the dongle's
  slow/cloud traffic is forwarded to the vendor cloud **as-is**. The official app keeps
  working; the cloud slow stream is parsed for Home Assistant too. See
  [Hybrid relay](#hybrid-relay-this-fork).

**206 sensors across 7 devices**, 148 enabled on a fresh install, plus the controls of
the 100% local mode. Entity names in English or French (`LANGUAGE` option).

> **Tested deployment:** this fork has been tested as a Docker Compose deployment. The
> Home Assistant add-on packaging path has **not** been tested in this fork — use it at
> your own risk. See [Docker deployment](#docker-deployment).

> **Acknowledgment:** a fork of [fadmaz/siseli-ha](https://github.com/fadmaz/siseli-ha)
> and its **Siseli Inverter Bridge**, itself an expanded fork of
> [yuraantonov11/siseli-ha](https://github.com/yuraantonov11/siseli-ha). Huge thanks to
> both authors. If you only want to **listen** to your inverter, never send it anything,
> and keep the vendor cloud in the loop, use Siseli Inverter Bridge from
> [fadmaz/siseli-ha](https://github.com/fadmaz/siseli-ha) — that is exactly what it is
> built for.

---

## Fork differences

Compared with upstream `siseli-local-bridge`, this fork adds:

- **Fast local H reads** (`LIVE_POLL_INTERVAL_SEC`, tested at 5 s) instead of relying on
  the dongle's ~5-minute cache.
- **Strict live typing by echoed token** — no shape fallback; unknown or expired tokens
  are dropped and logged, never published as telemetry.
- **Hybrid relay** (`UPSTREAM_RELAY`) — fast reads stay local, slow/cloud MQTT is
  forwarded as-is to the vendor cloud.
- **Always-on journal** (`monitor.jsonl`) with `cloud`, `dongle`, `fast` and `slow`
  records and size-based rotation.
- **HTTP bootstrap additions** — `gatherProtocol`, `syncTime`, an authenticated
  upstream fallback for unknown `/dtu/` calls, and `HTTP_BOOTSTRAP_MODE`
  (`local` / `cloud` / `cloud_then_local`).
- **HPVINV08 BMS support** — `dbXf`/`MzuA` aliases and the BMS current-direction fix.
- **Diagnostic live probe** (`LIVE_PROBE_*`) and **Docker deployment** documentation.
- **Container startup restores the fake-cloud IP** from `LOCAL_CLOUD_IP` if the host
  alias is missing.
- **Russian README** and a tested Docker Compose path.

Not yet verified in this fork:

- the Home Assistant **add-on packaging path** (the add-on was inherited from upstream;
  only Docker has been tested);
- long-running stability and vendor-side behavior of hybrid relay;
- the 38 sensors that remain `Unknown` (see [Known limitations](#known-limitations)).

---

## Install

**Settings → Add-ons → Add-on Store → ⋮ → Repositories**, then add:

```
https://github.com/msergein/siseli-ha
```

Install **Siseli Local Bridge** (and **Network IP Alias** if you want the 100% local
mode), then follow **[the documentation](siseli_local_bridge/DOCS.md)** — requirements,
every configuration option, network setup and troubleshooting. Home Assistant renders
that same page on the add-on's **Documentation** tab once it is installed.

---

## Docker deployment

The bridge can also run as a normal Docker container on a Linux host. It needs
`network_mode: host` plus `NET_ADMIN`/`NET_RAW`, because it performs ARP interception and
raw packet capture. Docker Desktop on macOS/Windows cannot provide this.

Build the image from the repository root:

```bash
docker build -t siseli-local-bridge:local ./siseli_local_bridge
```

Example `docker-compose.yml` (Mosquitto is assumed to be running already; point
`MQTT_HOST` at it):

```yaml
services:
  siseli-local-bridge:
    build:
      context: ./siseli_local_bridge
      dockerfile: Dockerfile
    image: siseli-local-bridge:local
    container_name: siseli-local-bridge
    restart: unless-stopped
    network_mode: host
    cap_add:
      - NET_ADMIN
      - NET_RAW
    security_opt:
      - apparmor=unconfined
    entrypoint: []
    command:
      - python3
      - -u
      - -m
      - src.siseli_local_bridge.core
    env_file:
      - .env
    volumes:
      - ./data:/data
```

Create `.env` from the example below and **do not commit it**:

```dotenv
# MQTT broker (Mosquitto)
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
MQTT_USER=your-mqtt-user
MQTT_PASSWORD=your-mqtt-password

# Inverter and network
INVERTER_IP=192.168.1.50
ROUTER_IP=192.168.1.1
INVERTER_MAC=aa:bb:cc:dd:ee:ff
ROUTER_MAC=11:22:33:44:55:66
SNIFF_IFACE=eth0

# Local cloud on a spare host address
LOCAL_CLOUD_IP=192.168.1.250
LOCAL_CLOUD_PORT=1883
HTTP_STUB_PORT=80
HTTP_STUB_REAL_IPS=8.212.16.60
HTTP_BOOTSTRAP_MODE=local
DNS_SPOOF_DOMAIN=broker.mqtt.solar.siseli.com,dtu.access.solar.siseli.com
MQTT_BROKER_HOSTNAME=hongkong.broker.mqtt.solar.siseli.com

# Vendor cloud, for hybrid relay / pass-through
TARGET_HOST=8.212.18.157
TARGET_PORT=1883
AUTO_INTERCEPT=true
FORWARD_ALL_INVERTER_TRAFFIC=false

# Fast local reads and journal
TELEMETRY_POLL_INTERVAL_SEC=0
LIVE_POLL_INTERVAL_SEC=5
LIVE_MAX_INFLIGHT=1
LIVE_MONITOR=true
LIVE_MONITOR_ONLY=false
MONITOR_MAX_BYTES=20971520
MONITOR_BACKUPS=5

# false = 100% local, true = hybrid relay
UPSTREAM_RELAY=false
```

For **pass-through**, leave `LOCAL_CLOUD_IP` empty and keep `UPSTREAM_RELAY=false`.

Create the data directory and start:

```bash
mkdir -p data
docker compose up -d --build
docker compose logs -f siseli-local-bridge
```

For **100% local** or **hybrid relay**, the container entrypoint now adds the
local-cloud address automatically from `LOCAL_CLOUD_IP` if it is missing. It uses
`SNIFF_IFACE` when set, otherwise the default-route interface. The manual equivalent is:

```bash
sudo ip addr add 192.168.1.250/24 dev eth0
```

Remove it with `sudo ip addr del 192.168.1.250/24 dev eth0` when returning to
pass-through. On Home Assistant OS, use the **Network IP Alias** add-on instead of this
manual command.

For **hybrid relay**, set `UPSTREAM_RELAY=true` and keep `LOCAL_CLOUD_IP` set. The
bridge will forward the dongle's cloud traffic as-is and keep fast H reads local.

---

## How it works (pass-through)

Your inverter's WiFi dongle publishes telemetry over MQTT to the Siseli cloud at
`8.212.18.157:1883`. In pass-through mode the add-on:

1. **Puts itself in the path** using ARP interception, so the inverter's packets reach
   the Home Assistant host.
2. **Reassembles the TCP stream** and pulls out the MQTT PUBLISH frames.
3. **Decodes the payload** — base64 blocks keyed by four-character names (`2ONL`, `WdRR`,
   `Yavb`, …), each a list of space-separated values read by position.
4. **Publishes to your broker** with MQTT auto-discovery, so entities appear on their own.
5. **Forwards the traffic onward** to the cloud, unchanged.

In this mode it never terminates a connection and never opens a listening socket. It
observes, decodes, and relays.

**What this means in practice:** if the add-on stops, your inverter keeps working and the
vendor app keeps working. You lose the Home Assistant sensors, nothing else.

---

## Hybrid relay (this fork)

This fork adds a third mode for installations that still need the vendor cloud:

```text
                 fast H-block reads (local)
inverter dongle <────────────────────────────> bridge <──> Home Assistant
       │                                           │
       └──────── slow/cloud MQTT as-is ────────────┴──> vendor cloud
```

- The dongle still talks to the real cloud through the bridge. The official web portal and
  Android app keep working.
- The bridge reads `HOP`, `HGRID`, `HPV`, `HBAT`, `HBMS1`, `HBMS2`, `HBMS3`, `HTEMP`,
  `HSTS`, `HGEN` and `HPVB` locally every `LIVE_POLL_INTERVAL_SEC` seconds.
- Slow/cloud traffic is forwarded **unchanged**. The bridge parses the slow payloads for
  Home Assistant; the cloud's own replies are forwarded back to the dongle.
- Local fast commands and their replies are identified by their echoed `t` token and are
  **never sent to the cloud**. Settings writes are tracked the same way.
- Monitoring records both sides in `monitor.jsonl`: `source=cloud` /
  `direction=cloud->dongle` and `source=dongle` / `direction=dongle->cloud`.

Enable it with:

```yaml
UPSTREAM_RELAY: true
HTTP_BOOTSTRAP_MODE: cloud_then_local
LOCAL_CLOUD_IP: 192.168.1.250
LIVE_POLL_INTERVAL_SEC: 5
LIVE_MAX_INFLIGHT: 1
LIVE_MONITOR: true
LIVE_MONITOR_ONLY: false
TELEMETRY_POLL_INTERVAL_SEC: 0
```

**Status:** experimental. It has been verified against a live account: the cloud accepted
the session, the web/app showed the device online, a manual “refresh” produced a cloud
`dev_rpc` (`i=501`), the dongle reply (`i=502`) was forwarded back, and the slow payload
was parsed for Home Assistant. The cloud sees the Home Assistant host's IP, not the
dongle's, and uses the same MQTT client id; this may violate the vendor's terms or trigger
server-side session handling. Use it at your own risk and keep the rollback path below.

### Rollback to 100% local

```yaml
UPSTREAM_RELAY: false
```

Restart the add-on and power-cycle the dongle if it does not reconnect. The bridge then
keeps everything local, and the vendor app shows the inverter offline.

### Live reads and monitoring

- `LIVE_POLL_INTERVAL_SEC` — fast local cycle interval (seconds; `0` disables it).
- `LIVE_MAX_INFLIGHT` — how many local reads may wait for an answer (the tested deployment
  uses `1`; the code default is `2`).
- `LIVE_MONITOR_ONLY` — when `true`, fast answers are written to the journal but not
  published to Home Assistant. Slow data remains the reference.
- `LIVE_MONITOR` — always-on journal, independent of `LIVE_MONITOR_ONLY` (default `true`).
- `MONITOR_MAX_BYTES` / `MONITOR_BACKUPS` — size-based rotation for `monitor.jsonl`
  (default 20 MiB × 5 backups).

The journal is diagnostic: it stores the command, token, envelope error and raw answer
for each fast reply, plus the parsed slow snapshot. It rotates automatically and is safe
to keep on permanently.

---

## Known limitations

**38 of the 206 sensors read `Unknown` and cannot be decoded.** Earlier versions filled them
with hardcoded constants — fault flags that could never report a fault, a `Mode` that was
a fixed string in the source. Those were removed in 2.6.1. The entities remain, disabled
by default, and publish an explicit "no value" rather than a comforting lie. If your
inverter emits blocks that would decode them, an issue with a capture is welcome.

If instead *every* sensor reads `Unknown`, that is a different situation entirely: your
inverter speaks a protocol this add-on does not decode. The log says so in one line —
see [Every sensor reads Unknown](siseli_local_bridge/DOCS.md#every-sensor-reads-unknown).

**Two current sources disagree, and there is no way to tell which is right.** The BMS and
the inverter's own ammeter can differ by a factor of two or more, in either direction. The
official app displays both and they disagree there too. The bridge uses the BMS figure and
logs `[ENERGY SOURCE DISAGREEMENT]` when the two diverge, rather than silently picking a
winner. Settling this needs a clamp meter on the DC bus.

**Block positions were reverse-engineered from one device.** There is no published schema.
Values are read by position from blocks whose meaning was inferred. Where a position was
not understood, nothing is published.

---

---

## Supported hardware

Anything using the Siseli IoT cloud platform, which includes inverters sold as:

Solar of Things · LUMINOUS NEO · SUN WISE · Queen Tech · LIB Life · Sun house · LeiLing ·
SunSaviour · ECOmenic · HC solar · 沐能低碳 · PowMr · Taico

The configuration verified in this fork is listed under
[Verified hardware](#verified-hardware).

Other brands on that list are reported to work but are not covered by captures. If you
have one, a debug capture is the single most useful contribution you can make — see
[Troubleshooting](siseli_local_bridge/DOCS.md#your-inverter-is-not-decoded).

---

---

## 100% local mode

With `LOCAL_CLOUD_IP` set and `UPSTREAM_RELAY` off, the add-on **impersonates the vendor
cloud** on a spare IP address of your Home Assistant host. The dongle never reaches the
internet; the bridge reads the fast H blocks every `LIVE_POLL_INTERVAL_SEC` seconds and
uses the dongle's own slow push as the reference. The inverter's settings become Home
Assistant controls. Pass-through stays the default (`LOCAL_CLOUD_IP` left empty).

**Trade-off of the 100% local mode:** the vendor cloud no longer hears from the dongle, so
the official app shows the inverter offline. To use the app again, go back to
pass-through (see the end of this section).

The full option reference, with every setting explained, is on the add-on's
**Documentation** tab: [`siseli_local_bridge/DOCS.md`](siseli_local_bridge/DOCS.md).

### How the local cloud works

1. The **Network IP Alias** add-on (also in this repository) gives the Home Assistant host
   one extra IPv4 address on your LAN. That address plays the vendor cloud.
2. **ARP interception** puts the Home Assistant host between the dongle and your router,
   as in pass-through mode.
3. When the dongle boots, it looks up `broker.mqtt.solar.siseli.com` and
   `dtu.access.solar.siseli.com`. The bridge **answers those DNS queries** with the extra
   address, and answers the dongle's **HTTP bootstrap calls** (check-in, device lookup,
   "which MQTT broker should I use"). It also answers the vendor's HTTP address the
   dongle has cached, since some dongles skip DNS for it.
4. The dongle then connects to a **small MQTT broker built into the bridge** on the extra
   address. The bridge acknowledges its messages as the real cloud would. It reads the
   fast H blocks every `LIVE_POLL_INTERVAL_SEC` seconds; the optional full poll is
   controlled separately by `TELEMETRY_POLL_INTERVAL_SEC` (`0` disables it).
5. An **nftables rule** stops the host's own services (the Mosquitto add-on, for example)
   from answering on the extra address, so only the bridge does.
6. Decoded values go to **your** MQTT broker, and Home Assistant picks them up through
   MQTT discovery. Setting changes made in Home Assistant go back to the dongle on the
   same connection.

### Setting up the 100% local mode

The addresses below are **examples**; use your own.

1. Install the **Mosquitto broker** add-on and the MQTT integration, if you have not
   already.
2. On your router, give the WiFi dongle a **fixed address** (DHCP reservation), and pick
   one **free address** on the same LAN for the local cloud.
3. Add this repository (**Settings → Add-ons → Add-on Store → ⋮ → Repositories**):

   ```
   https://github.com/msergein/siseli-ha
   ```

4. Install **Network IP Alias** and give it the free address. On a Raspberry Pi running
   Home Assistant OS the LAN interface is `end0`; on most other hosts it is `eth0`.

   ```yaml
   INTERFACE: end0
   IP_ADDRESS: 192.168.1.200/24
   ```

5. Install **Siseli Local Bridge** and set at least these options (everything else can
   stay at its default):

   ```yaml
   MQTT_HOST: core-mosquitto
   MQTT_USER: your-mqtt-user
   MQTT_PASSWORD: your-mqtt-password
   INVERTER_IP: 192.168.1.50            # the dongle's fixed address
   ROUTER_IP: 192.168.1.1               # your gateway
   AUTO_INTERCEPT: true
   LOCAL_CLOUD_IP: 192.168.1.200        # same address as Network IP Alias, without /24
   LOCAL_CLOUD_PORT: 1883
   HTTP_STUB_PORT: 80
   HTTP_STUB_REAL_IPS: 8.212.16.60
   DNS_SPOOF_DOMAIN: broker.mqtt.solar.siseli.com,dtu.access.solar.siseli.com
   MQTT_BROKER_HOSTNAME: hongkong.broker.mqtt.solar.siseli.com
   TELEMETRY_POLL_INTERVAL_SEC: 0
   LIVE_POLL_INTERVAL_SEC: 5
   LIVE_MAX_INFLIGHT: 1
   FORWARD_ALL_INVERTER_TRAFFIC: false
   ```

6. Start **Network IP Alias**, then **Siseli Local Bridge**, and enable **Start on boot**
   for both.
7. **Power-cycle the WiFi dongle.** The DNS answers and the HTTP bootstrap only happen
   when it boots; until then it stays connected to the real cloud.
8. Within a minute the entities appear and refresh every few seconds. The controls are on
   the **Siseli Local Inverter 1** device, in its **Configuration** card.

> **Tip — faster connection: redirect the two names in your router's DNS.** If your router
> (or Pi-hole, AdGuard Home…) lets you add local DNS records, point these two names at the
> local cloud address (`LOCAL_CLOUD_IP`, `192.168.1.200` in the example above):
>
> ```
> hongkong.broker.mqtt.solar.siseli.com  ->  192.168.1.200
> dtu.access.solar.siseli.com            ->  192.168.1.200
> ```
>
> The dongle then gets the local address straight from the router, instead of the bridge
> having to answer its DNS query faster than the router does. It connects sooner after a
> power cut or a dongle reboot, and reconnects even if it happens to boot before the
> add-on. **Remove these records before going back to pass-through**: while they exist,
> the dongle cannot reach the real cloud whatever the add-on's settings.

### Controlling the inverter from Home Assistant

Every control shows the value **read back from the inverter**, not the last value sent:
if the inverter refuses or adjusts a setting, the entity shows what it really holds. The
commands follow the Voltronic PI30 protocol the inverter speaks (PI18 for programme 50
and the clock, PI17 for programmes 46/47); each one below was checked on the test hardware. ECO and programmes 22
and 25 appear in no telemetry block, so the add-on asks the inverter's flag status
(`QFLAG`, read only) once a minute to read them back.

| Control | Manual programme | Values |
|---|---|---|
| Output Source Priority | 01 | SBU / SUB |
| Max Charging Current (solar + utility) | 02 | 10–150 A, steps of 10 |
| Grid Working Range | 03 | UPS / Appliance |
| Battery Type | 05 | AGM … Growatt, Pylontech, … (10 types) |
| Overload Automatic Restart | 06 | on / off |
| Over Temperature Automatic Restart | 07 | on / off |
| ECO Power Saving | 08 | on / off |
| Output Voltage | 10 | 220 / 230 / 240 V |
| Max Utility Charge Current | 11 | 2, 10–90 A |
| Back To Grid Voltage | 12 | 44–51 V |
| Back To Battery Voltage | 13 | 48–58 V |
| Charger Priority | 16 | OSO / CSO / SNU |
| Buzzer | 18 | on / off |
| Display Returns To Homepage | 19 | on / off |
| Backlight | 20 | on / off |
| Beeps While Primary Source Interrupted | 22 | on / off |
| Overload To Bypass | 23 | on / off |
| Fault Code Record | 25 | on / off |
| Equalization Voltage | 31 | 48.0–60.0 V |
| BMS Lock Machine SOC | 38 | 5–95 %, steps of 5 |
| Restore Mains Charging SOC | 39 | 5–95 %, steps of 5 |
| Restore Battery Discharging SOC | 40 | 5–95 %, steps of 5 |
| Inverter Startup SOC | 41 | 5–100 %, steps of 5 |
| Solar Supply Priority | 43 | BLU / LBU |
| AC Charging Start Time / Stop Time | 46 / 47 | 00:00–23:00; outside this window the grid does not charge the battery (00:00–00:00 = no limit) |
| Grid Regulation Mode | 50 | Mode 1 IND … Mode 5 U2b, each labelled with its accepted voltage and frequency (Mode 3 SAd is the 57–62 Hz one) |
| Sync Inverter Clock (button) | 51–55 | sets the inverter's date and time to Home Assistant's |
| Grid-Tie Current | 56 | 4–40 A (the inverter refuses less than 4 A) |
| Dual Output | 60 | on / off |

Plus a **BMS Communication Normal** sensor: when it reads `No`, the inverter has lost its
BMS and the state of charge it reports is its own estimate (it read 99–100 % against a
real 43 % in testing), so SOC-based automations should check it first. A **Solar Feed To Grid**
sensor shows programme 44 (`GtD` / `GtE`); it can only be changed on the front panel, the
inverter refuses the documented command.

To keep the inverter's clock right, press **Sync Inverter Clock** from a daily automation
(`button.press` at 03:00, for example).

**Handle with care:**

- **Battery Type.** Changing it can briefly cut the inverter's AC output; if the inverter
  also powers your Home Assistant host, Home Assistant goes down with it. A battery type
  the BMS does not speak raises inverter warning 61 and loses the BMS data.
- **BMS Lock Machine SOC (programme 38)** shuts the inverter down below it. The bridge
  refuses any value at or above the current SOC, and refuses it entirely while BMS
  communication is lost.
- The inverter only accepts the SOC thresholds in steps of 5, and raising programme 38
  makes it raise programmes 39 and 62 by itself; the entities show where it settles.
- Two vendor-app actions are **deliberately not exposed**, because they cannot be undone:
  "Control Parameters To Default Value" (factory reset of every setting) and "Reset PV
  Energy Storage".

### Verified hardware

| Part | Model |
|---|---|
| Inverter | Easun SMT 6.2KW, model code `HPVINV08`, firmware `0020.05`, 48 V battery system, 230 V / 50 Hz output |
| WiFi dongle | RWB1 (Solar of Things), `V1.44.5_SolarV67`-class firmware |
| Battery | 48 V LiFePO4 bank, 100 Ah configured, BMS reported over the inverter's BMS link |
| Home Assistant host | x86_64 Linux host, Home Assistant 2026.9.4, Mosquitto broker |
| PV | one active string on PV1 (PV2 may be present but idle) |

Other devices that use the same cloud should behave the same way, but only this
configuration has been tested. Reports from other hardware are welcome.

### Going back to pass-through

Clear `LOCAL_CLOUD_IP` (and set `FORWARD_ALL_INVERTER_TRAFFIC: true` if the dongle does
not reconnect), remove the router DNS records if you added them, restart the add-on and
power-cycle the dongle. It finds the real cloud
again and the official app works; the Home Assistant controls stop working, since there is
no local connection to send them on, and the sensors fall back to the dongle's own
5-minute push.

---

---

## Contributing

Development setup, test conventions, how to add a capture from your own inverter, and the
release checklist are in [`CONTRIBUTING.md`](CONTRIBUTING.md).

The code and documentation in this fork were written with assistance from DeepSeek.

Release history is in [`siseli_local_bridge/CHANGELOG.md`](siseli_local_bridge/CHANGELOG.md), which
Home Assistant also renders on the add-on's **Changelog** tab.

Bug reports: use the [issue templates](.github/ISSUE_TEMPLATE/). Always include your
add-on version and a scrubbed log — this project's experience is that almost every real
defect was found by running it on someone's hardware, not by reading the code.

---

---

## License

[MIT](LICENSE). This repository is a fork of
[fadmaz/siseli-ha](https://github.com/fadmaz/siseli-ha) (MIT), itself a fork of
[yuraantonov11/siseli-ha](https://github.com/yuraantonov11/siseli-ha), which carries no
licence of its own, so no grant here can extend to that original work. [`NOTICE`](NOTICE)
sets out the distinction, and lists the licences of the bundled dependencies.
