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

| Variable    | Default | Description                                   |
|-------------|---------|------------------------------------------------|
| `PORT`      | `5000`  | TCP port the Flask server listens on.          |
| `UP_GPIO`   | `19`    | BCM GPIO pin driving the "up" relay.           |
| `DOWN_GPIO` | `26`    | BCM GPIO pin driving the "down" relay.         |
| `DOOR_TIME` | `17`    | Seconds the relay stays energised for a move.  |

## Web UI

Open `http://<pi-address>:5000/` in a browser (desktop or mobile). The page
offers three buttons:

* **Up** – raises the gate.
* **Down** – lowers the gate.
* **Stop** – immediately stops any gate movement.

Pressing **Up** or **Down** opens a confirmation dialog with a safety
warning. The dialog must be confirmed by pressing and holding the confirm
button for two seconds (works with mouse and touch) before the command is
sent, to avoid accidental activation. **Stop** is a safety action and is
executed immediately without confirmation.

The UI is responsive and usable on both desktop and mobile screens.

## HTTP/JSON API

| Method | Path          | Description                                                   |
|--------|---------------|----------------------------------------------------------------|
| GET    | `/`           | Serves the HTML control page.                                 |
| GET    | `/api/status` | Returns the current status as JSON: `{"busy": bool, "direction": "up"\|"down"\|null, "message": str}`. |
| POST   | `/api/up`     | Starts raising the gate. Returns `409` if a move is already in progress. |
| POST   | `/api/down`   | Starts lowering the gate. Returns `409` if a move is already in progress. |
| POST   | `/api/stop`   | Immediately stops any movement and releases both relays. Always returns `200`. |

All endpoints return a JSON body describing the resulting status, e.g.:

```json
{"busy": true, "direction": "up", "message": "Raising the gate..."}
```

## Running as a service

An example `supervisord` program definition is provided in
`config/sv-door-control.conf` to run the Flask app as a persistent service on
boot.
