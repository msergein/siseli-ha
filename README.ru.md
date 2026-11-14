# ☀️ Siseli Local Bridge для Home Assistant

[English](README.md) | **Русский**

[![Siseli Local Bridge](https://img.shields.io/badge/version-2.8.0-blue.svg?label=Siseli%20Local%20Bridge)](siseli_local_bridge/CHANGELOG.md)
[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Add--on-green.svg)](https://www.home-assistant.io/)
[![License: MIT](https://img.shields.io/badge/license-MIT-lightgrey.svg)](LICENSE)

Этот репозиторий — форк [siselilocal/siseli-ha](https://github.com/siselilocal/siseli-ha),
который, в свою очередь, является форком [fadmaz/siseli-ha](https://github.com/fadmaz/siseli-ha)
и [yuraantonov11/siseli-ha](https://github.com/yuraantonov11/siseli-ha). Спасибо авторам
исходного проекта.

Аддон читает телеметрию Siseli-совместимого солнечного инвертора и публикует её в Home
Assistant через MQTT auto-discovery. Поддерживаются три режима:

- **Pass-through** — донгл продолжает общаться с облаком, официальное приложение
  работает, а bridge декодирует трафик по пути.
- **100% local** — bridge заменяет облако: донгл общается только с хостом Home
  Assistant. Настройки инвертора становятся сущностями HA.
- **Hybrid relay** — режим этого форка: быстрые H-команды остаются локальными, а
  медленный/облачный трафик уходит в облако **как есть**. Официальный сайт и Android
  приложение продолжают работать, slow-поток из облака тоже парсится для HA.

> **Проверенное развёртывание:** этот форк тестировался как Docker Compose. Путь
> установки через Home Assistant add-on в этом форке **не тестировался** — используй
> на свой риск. См. [Развёртывание в Docker](#развёртывание-в-docker).

> Английский README — основной. Если перевод и `README.md` расходятся, ориентируйся на
> английский вариант.

---

## Отличия форка

По сравнению с upstream `siseli-local-bridge`, в этом форке добавлено:

- **быстрые локальные H-чтения** (`LIVE_POLL_INTERVAL_SEC`, проверено на 5 с) вместо
  ожидания кэша донгла раз в ~5 минут;
- **строгая типизация live-ответов по токену** — без shape-fallback; неизвестный или
  просроченный токен отбрасывается и логируется, а не публикуется как телеметрия;
- **hybrid relay** (`UPSTREAM_RELAY`) — быстрые чтения локально, slow/cloud MQTT
  уходит в облако как есть;
- **постоянный журнал** (`monitor.jsonl`) с записями `cloud`, `dongle`, `fast`, `slow`
  и ротацией по размеру;
- **дополнения HTTP bootstrap** — `gatherProtocol`, `syncTime` и authenticated
  upstream fallback для неизвестных `/dtu/` запросов;
- **поддержка BMS HPVINV08** — aliases `dbXf`/`MzuA` и исправление направления тока;
- **диагностический live probe** (`LIVE_PROBE_*`) и **Docker deployment**;
- **русский README** и проверенный путь Docker Compose.

В этом форке пока **не проверены**:

- путь установки как Home Assistant **add-on** (add-on унаследован от upstream;
  тестировался только Docker);
- долговременная стабильность и поведение облака в hybrid relay;
- 38 сенсоров, которые остаются `Unknown` (см. [Ограничения](#ограничения)).

---

## Hybrid relay (этот форк)

```text
                 быстрые H-команды (локально)
инвертор/донгл <────────────────────────────> bridge <──> Home Assistant
       │                                         │
       └──────── slow/cloud MQTT как есть ───────┴──> облако Siseli
```

Что происходит:

- донгл подключается к локальному bridge, но его исходящий MQTT-трафик bridge
  пересылает в настоящее облако;
- быстрые чтения (`HOP`, `HGRID`, `HPV`, `HBAT`, `HBMS1`, `HBMS2`, `HBMS3`,
  `HTEMP`, `HSTS`, `HGEN`, `HPVB`) идут локально каждые `LIVE_POLL_INTERVAL_SEC`
  секунд;
- ответы на локальные команды определяются по токену `t` и **не отправляются в
  облако**;
- ответы облака пересылаются донглу как есть;
- slow-данные из облака парсятся для HA;
- `monitor.jsonl` пишет обе стороны: `source=cloud` (`cloud->dongle`) и
  `source=dongle` (`dongle->cloud`).

Пример настроек:

```yaml
UPSTREAM_RELAY: true
LOCAL_CLOUD_IP: 192.168.1.250
LIVE_POLL_INTERVAL_SEC: 5
LIVE_MAX_INFLIGHT: 1
LIVE_MONITOR: true
LIVE_MONITOR_ONLY: false
TELEMETRY_POLL_INTERVAL_SEC: 0
```

**Статус:** экспериментальный режим. Проверено на живом аккаунте: облако приняло
сессию, сайт и Android-приложение видели устройство, кнопка «Обновить» вызвала
облачный `dev_rpc` (`i=501`), ответ донгла (`i=502`) ушёл обратно, а slow-данные
распарсились для HA.

Риски:

- облако видит IP хоста Home Assistant, а не IP донгла;
- используется тот же MQTT `client_id`;
- это может нарушать условия использования облака или ломаться при изменении его
  серверной логики;
- режим требует наблюдения и готовности откатиться на 100% local.

### Откат на 100% local

```yaml
UPSTREAM_RELAY: false
```

Перезапустить аддон. Если донгл не переподключился — перезапустить питание донгла.
После этого облако снова не получает данные, а официальное приложение показывает
инвертор offline.

### Быстрые чтения и мониторинг

- `LIVE_POLL_INTERVAL_SEC` — интервал быстрого локального цикла; `0` отключает его.
- `LIVE_MAX_INFLIGHT` — сколько локальных команд может ждать ответ. В проверенном
  развёртывании используется `1`; в коде default `2`.
- `LIVE_MONITOR_ONLY` — если `true`, быстрые ответы пишутся в журнал, но **не**
  публикуются в HA. Slow остаётся эталоном.
- `LIVE_MONITOR` — постоянный журнал, независимый от `LIVE_MONITOR_ONLY`
  (default `true`).
- `MONITOR_MAX_BYTES` / `MONITOR_BACKUPS` — ротация `monitor.jsonl`
  (default 20 MiB × 5 backups).

Журнал нужен для разбора ошибок: в нём есть команда, токен, ошибка конверта и сырой
ответ. Ротация не даёт файлу разрастись.

---

## Установка

**Settings → Add-ons → Add-on Store → ⋮ → Repositories**, добавить:

```text
https://github.com/msergein/siseli-ha
```

Установить **Siseli Local Bridge** (и **Network IP Alias**, если нужен 100% local),
затем открыть **[документацию](siseli_local_bridge/DOCS.md)** — там требования, все
опции, настройка сети и troubleshooting.

---

## Развёртывание в Docker

Bridge можно запускать как обычный Docker-контейнер на Linux-хосте. Нужны
`network_mode: host` и capabilities `NET_ADMIN`/`NET_RAW`: bridge делает ARP
interception и захват сырых пакетов. Docker Desktop на macOS/Windows для этого не
подходит.

Сборка из корня репозитория:

```bash
docker build -t siseli-local-bridge:local ./siseli_local_bridge
```

Пример `docker-compose.yml` (Mosquitto уже должен работать отдельно; `MQTT_HOST`
укажи на него):

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

Создай `.env` по примеру ниже и **не коммить его**:

```dotenv
# MQTT-брокер (Mosquitto)
MQTT_HOST=127.0.0.1
MQTT_PORT=1883
MQTT_USER=your-mqtt-user
MQTT_PASSWORD=your-mqtt-password

# Инвертор и сеть
INVERTER_IP=192.168.1.50
ROUTER_IP=192.168.1.1
INVERTER_MAC=aa:bb:cc:dd:ee:ff
ROUTER_MAC=11:22:33:44:55:66
SNIFF_IFACE=eth0

# Локальное облако на свободном адресе хоста
LOCAL_CLOUD_IP=192.168.1.250
LOCAL_CLOUD_PORT=1883
HTTP_STUB_PORT=80
HTTP_STUB_REAL_IPS=8.212.16.60
DNS_SPOOF_DOMAIN=broker.mqtt.solar.siseli.com,dtu.access.solar.siseli.com
MQTT_BROKER_HOSTNAME=hongkong.broker.mqtt.solar.siseli.com

# Облако вендора — для hybrid relay / pass-through
TARGET_HOST=8.212.18.157
TARGET_PORT=1883
AUTO_INTERCEPT=true
FORWARD_ALL_INVERTER_TRAFFIC=false

# Быстрые локальные чтения и журнал
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

Для **pass-through** оставь `LOCAL_CLOUD_IP` пустым и `UPSTREAM_RELAY=false`.

Запуск:

```bash
mkdir -p data
docker compose up -d --build
docker compose logs -f siseli-local-bridge
```

Для **100% local** или **hybrid relay** добавь адрес локального облака на интерфейс
хоста:

```bash
sudo ip addr add 192.168.1.250/24 dev eth0
```

Удалить при возврате в pass-through:

```bash
sudo ip addr del 192.168.1.250/24 dev eth0
```

На Home Assistant OS вместо ручной команды используй аддон **Network IP Alias**.

Для **hybrid relay** установи `UPSTREAM_RELAY=true` и оставь `LOCAL_CLOUD_IP`
заполненным. Быстрые H-чтения останутся локальными, облачный трафик пойдёт в облако
как есть.

---

## 100% local

С `LOCAL_CLOUD_IP` и выключенным `UPSTREAM_RELAY` аддон изображает облако на
дополнительном IP-адресе хоста HA:

1. **Network IP Alias** добавляет хосту второй IPv4-адрес.
2. ARP interception ставит хост между донглом и роутером.
3. Bridge отвечает на DNS-запросы `broker.mqtt.solar.siseli.com` и
   `dtu.access.solar.siseli.com` этим адресом.
4. Донгл подключается к встроенному MQTT-брокеру bridge.
5. Bridge читает быстрые H-блоки каждые `LIVE_POLL_INTERVAL_SEC` секунд.
6. Значения уходят в MQTT Home Assistant; настройки из HA идут обратно в инвертор.

Основные опции:

```yaml
MQTT_HOST: core-mosquitto
MQTT_USER: your-mqtt-user
MQTT_PASSWORD: your-mqtt-password
INVERTER_IP: 192.168.1.50
ROUTER_IP: 192.168.1.1
AUTO_INTERCEPT: true
LOCAL_CLOUD_IP: 192.168.1.200
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

После установки **Network IP Alias** и **Siseli Local Bridge** нужно включить
**Start on boot** для обоих и перезапустить питание донгла: DNS и HTTP bootstrap
происходят при его загрузке.

---

## Управление из Home Assistant

Все контролы показывают значение, **прочитанное обратно с инвертора**, а не последнее
отправленное. Если инвертор отказал или скорректировал настройку, HA покажет реальное
состояние.

Основные контролы:

| Контрол | Программа | Значения |
|---|---|---|
| Output Source Priority | 01 | SBU / SUB |
| Max Charging Current | 02 | 10–150 A, шаг 10 |
| Grid Working Range | 03 | UPS / Appliance |
| Battery Type | 05 | AGM … Growatt, Pylontech, … |
| Overload Restart | 06 | on / off |
| Over Temperature Restart | 07 | on / off |
| ECO | 08 | on / off |
| Output Voltage | 10 | 220 / 230 / 240 V |
| Max Utility Charge Current | 11 | 2, 10–90 A |
| Back To Grid Voltage | 12 | 44–51 V |
| Back To Battery Voltage | 13 | 48–58 V |
| Charger Priority | 16 | OSO / CSO / SNU |
| Buzzer | 18 | on / off |
| Display Returns To Homepage | 19 | on / off |
| Backlight | 20 | on / off |
| Overload To Bypass | 23 | on / off |
| Equalization Voltage | 31 | 48.0–60.0 V |
| BMS Lock Machine SOC | 38 | 5–95 %, шаг 5 |
| Restore Mains Charging SOC | 39 | 5–95 %, шаг 5 |
| Restore Battery Discharging SOC | 40 | 5–95 %, шаг 5 |
| Inverter Startup SOC | 41 | 5–100 %, шаг 5 |
| Solar Supply Priority | 43 | BLU / LBU |
| AC Charging Start/Stop Time | 46 / 47 | 00:00–23:00 |
| Grid Regulation Mode | 50 | Mode 1 … Mode 5 |
| Sync Inverter Clock | 51–55 | кнопка |
| Grid-Tie Current | 56 | 4–40 A |
| Dual Output | 60 | on / off |

**Осторожно:**

- **Battery Type** может кратко отключить AC-выход инвертора. Если инвертор питает
  сам хост Home Assistant, HA тоже выключится.
- **BMS Lock Machine SOC (38)** выключает инвертор ниже этого SOC. Bridge не даст
  выставить значение выше текущего SOC и откажет, если BMS communication потеряна.
- SOC-пороги принимаются шагом 5 %.
- Два действия из приложения **специально не выставлены**: полный сброс настроек
  («Control Parameters To Default Value») и сброс PV-энергии («Reset PV Energy
  Storage»).

---

## Ограничения

**38 из 206 сенсоров показывают `Unknown`.** Раньше они заполнялись
захардкоженными константами, из-за чего «авария» не могла появиться, а `Mode` был
фиксированной строкой. Эти константы убраны: лучше `Unknown`, чем ложное значение.
Сущности остаются, часть выключена по умолчанию.

Если **все** сенсоры `Unknown` — это другая ситуация: инвертор говорит на протоколе,
который аддон не декодирует. В логе будет соответствующая строка; см.
[Every sensor reads Unknown](siseli_local_bridge/DOCS.md#every-sensor-reads-unknown).

**Два источника тока могут расходиться.** BMS и собственный амперметр инвертора
могут показывать разные значения, иногда в два раза. Официальное приложение тоже
показывает оба, и они расходятся. Bridge использует BMS и пишет
`[ENERGY SOURCE DISAGREEMENT]`, когда значения расходятся, вместо молчаливого выбора
одного.

**Позиции в блоках восстановлены по одному устройству.** Опубликованного протокола
нет; значения читаются по позициям. Если позиция не подтверждена — ничего не
публикуется.

Отдельно: `QMOD`/`QFLAG` на проверенном инверторе отвечают `(NAKss)`, поэтому
`mode`/`eco` локально недоступны. Облачный API при этом показывает `B`/`Off`, но это
не доказывает, что значения живые — облако может хранить последнее известное.

---

## Проверенное железо

| Компонент | Модель |
|---|---|
| Инвертор | Easun SMT 6.2KW, `HPVINV08`, firmware `0020.05`, 48 V, 230 V / 50 Hz |
| Донгл | RWB1 (Solar of Things), класс `V1.44.5_SolarV67` |
| Батарея | 48 V LiFePO4, конфигурация 100 Ah, BMS через инвертор |
| Home Assistant | 2026.9.4, x86_64 Linux, Mosquitto |
| PV | одна активная строка на PV1 |

Проверена только эта конфигурация. Отчёты по другому железу приветствуются.

---

## Разработка

Инструкции по тестам, capture с собственного инвертора и release checklist — в
[`CONTRIBUTING.md`](CONTRIBUTING.md).

Код и документация этого форка написаны с помощью DeepSeek.

История версий — в [`siseli_local_bridge/CHANGELOG.md`](siseli_local_bridge/CHANGELOG.md).

---

## Лицензия

[MIT](LICENSE). Репозиторий — форк [fadmaz/siseli-ha](https://github.com/fadmaz/siseli-ha)
(MIT), который является форком
[yuraantonov11/siseli-ha](https://github.com/yuraantonov11/siseli-ha). Подробности и
лицензии зависимостей — в [`NOTICE`](NOTICE).
