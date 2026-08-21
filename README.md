# fhu_auto

FHU door Raspberry Pi controller.

This repository has been fully migrated away from ROS. It is now a small,
self-contained Python Flask application that drives the gate relays through
the Raspberry Pi GPIO pins, and exposes a web UI plus a simple HTTP/JSON API.

## Requirements

* Python 3.5+
* A Raspberry Pi with the two relay channels wired to the GPIO pins
  configured in `app.py` (default: GPIO19 for up, GPIO26 for down).

## Installation

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

`RPi.GPIO` is only required (and only installable) on a Raspberry Pi. When
running the app on a regular PC (e.g. for development or UI testing) a mock
GPIO backend is used automatically and GPIO calls are just printed to the
console.

## Running

```bash
python app.py
```

By default the server listens on `0.0.0.0:5000`. The following environment
variables can be used to configure it:

| Variable            | Default        | Description                                          |
|---------------------|----------------|-------------------------------------------------------|
| `PORT`              | `5000`         | TCP port the Flask server listens on.                 |
| `UP_GPIO`           | `19`           | BCM GPIO pin driving the "up" relay.                  |
| `DOWN_GPIO`         | `26`           | BCM GPIO pin driving the "down" relay.                |
| `DOOR_TIME`         | `17`           | Seconds the relay stays energised for a move.         |
| `GATE_LAT`          | `53.268684`    | Latitude of the gate, used for geofencing.            |
| `GATE_LON`          | `-0.524170`    | Longitude of the gate, used for geofencing.            |
| `GEOFENCE_RADIUS_M` | `50`           | Radius (metres) within which Up/Down can be operated. |
| `LOG_FILE`          | `gate_control.log` (next to `app.py`) | Path to the command log file.  |

## Web UI

Open `http://<pi-address>:5000/` in a browser (desktop or mobile). The page
offers three buttons:

* **Up** – raises the gate.
* **Down** – lowers the gate.
* **Stop** – immediately stops any gate movement.

Pressing **Up** or **Down** opens a confirmation dialog with a safety
warning. The dialog must be confirmed by pressing and holding the confirm
button for two seconds (works with mouse and touch) before the command is
sent, to avoid accidental activation. **Stop** is a safety action: it is
executed immediately without confirmation, is never geofenced, and is also
available as a button inside the confirmation dialog itself, so a move can
always be interrupted.

On load, the page requests the browser's location and compares it against
the configured gate position and radius. **Up** and **Down** stay disabled,
and a status line explains why, until the client is confirmed to be within
range; **Stop** is never affected by this check.

The page also shows the likely current state of the gate (`open`, `closed`
or `unknown`, since the actual door position can't be read back from
hardware) and a "Recent commands" list with the last 10 commands issued.

The UI is responsive and usable on both desktop and mobile screens.

Note: browsers only expose geolocation on secure origins (HTTPS or
`localhost`), so serving the app over plain HTTP on the LAN may prevent
Up/Down from ever becoming available in the field unless TLS is set up.

## HTTP/JSON API

| Method | Path          | Description                                                   |
|--------|---------------|----------------------------------------------------------------|
| GET    | `/`           | Serves the HTML control page.                                 |
| GET    | `/api/status` | Returns the current status as JSON (see below).                |
| POST   | `/api/up`     | Starts raising the gate. Requires a JSON body `{"lat": float, "lon": float}` with the client's location. Returns `403` if outside the geofence, `409` if a move is already in progress. |
| POST   | `/api/down`   | Starts lowering the gate. Same location requirement and error codes as `/api/up`. |
| POST   | `/api/stop`   | Immediately stops any movement and releases both relays. Never geofenced, always returns `200`. |

`/api/status` (and the other endpoints) return a JSON body describing the
resulting status, e.g.:

```json
{
  "busy": true,
  "direction": "up",
  "message": "Raising the gate...",
  "last_command": "up",
  "last_command_time": "2026-08-21T10:15:00+00:00",
  "likely_state": "unknown",
  "history": [
    {"command": "up", "time": "2026-08-21T10:15:00+00:00"}
  ],
  "geofence": {"lat": 53.268684, "lon": -0.524170, "radius_m": 50}
}
```

Every command (`up`, `down`, `stop`) is also appended, with its timestamp,
to the local log file configured by `LOG_FILE`.


## Running as a service

An example `supervisord` program definition is provided in
`config/sv-door-control.conf` to run the Flask app as a persistent service on
boot.
