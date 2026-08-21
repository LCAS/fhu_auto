#!/usr/bin/env python3
"""Flask web application for controlling the FHU gate.

This is a pure Python replacement for the previous ROS-based control
stack. It drives the same GPIO relays that used to be driven by the ROS
node, but exposes them through a small HTTP/JSON API and a simple,
mobile-friendly web UI.

API
---
GET  /            HTML control page.
GET  /api/status  JSON status of the gate: {"busy": bool, "direction":
                   "up"|"down"|null, "message": str, "last_command":
                   "up"|"down"|"stop"|null, "last_command_time": str|null,
                   "likely_state": "open"|"closed"|"unknown", "history":
                   [{"command": str, "time": str}, ...] (newest first,
                   last 10 commands), "geofence": {"lat": float, "lon":
                   float, "radius_m": float}.
POST /api/up      Start raising the gate. Requires the client's location
                   (see geofencing below). Returns 409 if a move is
                   already in progress, 403 if outside the geofence.
POST /api/down     Start lowering the gate. Same location requirement as
                   /api/up.
POST /api/stop     Immediately stop any door movement and release the
                   relays. Always allowed: never geofenced, never blocked.

Every command is also appended, with its timestamp, to a local log file
(see LOG_FILE below).

Geofencing
----------
Up/down requests must include a JSON body {"lat": float, "lon": float}
with the client's current position. The request is rejected (403) unless
that position is within GEOFENCE_RADIUS_M metres of (GATE_LAT, GATE_LON).
The stop endpoint is exempt from this check.
"""

import atexit
import logging
import math
import os
import threading
from collections import deque
from datetime import datetime, timezone

from flask import Flask, jsonify, render_template, request

try:
    import RPi.GPIO as GPIO
except (ImportError, RuntimeError):
    # Allow the app to run (e.g. for development/testing) on machines
    # that are not a Raspberry Pi, or without RPi.GPIO installed.
    class _MockGPIO:
        BCM = 'BCM'
        OUT = 'OUT'
        HIGH = 1
        LOW = 0

        def setmode(self, *_args, **_kwargs):
            pass

        def setup(self, *_args, **_kwargs):
            pass

        def output(self, pin, value):
            print('[mock GPIO] pin {} -> {}'.format(pin, value))

        def cleanup(self):
            pass

    GPIO = _MockGPIO()

app = Flask(__name__)

UP_GPIO = int(os.environ.get('UP_GPIO', 19))
DOWN_GPIO = int(os.environ.get('DOWN_GPIO', 26))
DOOR_TIME = float(os.environ.get('DOOR_TIME', 17))  # seconds

# Geofencing: the gate's position and the radius (in metres) within which
# a client is allowed to operate it.
GATE_LAT = float(os.environ.get('GATE_LAT', 53.268684))
GATE_LON = float(os.environ.get('GATE_LON', -0.524170))
GEOFENCE_RADIUS_M = float(os.environ.get('GEOFENCE_RADIUS_M', 50))

# Protects access to the shared state below.
_lock = threading.Lock()
_busy = False
_direction = None  # 'up' or 'down' while a move is in progress
_stop_event = threading.Event()

# Last command issued and the gate position it implies, since the actual
# door position cannot be read back from hardware.
_last_command = None  # 'up', 'down' or 'stop'
_last_command_time = None
_likely_state = 'unknown'  # 'open', 'closed' or 'unknown'

# ── Command logging ──────────────────────────────────────────────────────────

LOG_FILE = os.environ.get(
    'LOG_FILE', os.path.join(os.path.dirname(os.path.abspath(__file__)), 'gate_control.log')
)

_command_logger = logging.getLogger('gate_control')
_command_logger.setLevel(logging.INFO)
_command_logger.addHandler(logging.FileHandler(LOG_FILE))
_command_logger.handlers[-1].setFormatter(logging.Formatter('%(asctime)s %(message)s'))

_command_history = deque(maxlen=10)  # newest first: {'command', 'time'}


def _log_command(command):
    timestamp = datetime.now(timezone.utc).isoformat()
    _command_logger.info(command)
    with _lock:
        _command_history.appendleft({'command': command, 'time': timestamp})


# ── GPIO initialisation ─────────────────────────────────────────────────────

GPIO.setmode(GPIO.BCM)
GPIO.setup(UP_GPIO, GPIO.OUT)
GPIO.setup(DOWN_GPIO, GPIO.OUT)
GPIO.output(UP_GPIO, GPIO.HIGH)    # relay off
GPIO.output(DOWN_GPIO, GPIO.HIGH)  # relay off

atexit.register(GPIO.cleanup)


# ── GPIO helpers ─────────────────────────────────────────────────────────────

def _run_relay(active_pin, idle_pin, duration):
    """Energise *active_pin* for up to *duration* seconds then release it.

    The move can be interrupted early by setting ``_stop_event``.
    """
    global _busy, _direction, _likely_state
    try:
        # Ensure the idle relay is off before activating the other (safety measure)
        GPIO.output(idle_pin, GPIO.HIGH)
        GPIO.output(active_pin, GPIO.LOW)

        # Wait in small increments so a stop request is honoured quickly.
        completed = not _stop_event.wait(duration)

        GPIO.output(active_pin, GPIO.HIGH)
    finally:
        GPIO.output(active_pin, GPIO.HIGH)
        GPIO.output(idle_pin, GPIO.HIGH)
        with _lock:
            # Only a move that ran for its full duration reliably reaches
            # the end stop; anything interrupted leaves the position unknown.
            if completed:
                _likely_state = 'open' if _direction == 'up' else 'closed'
            else:
                _likely_state = 'unknown'
            _busy = False
            _direction = None


def _start_move(active_pin, idle_pin, direction):
    global _busy, _direction, _last_command, _last_command_time
    with _lock:
        if _busy:
            return False
        _busy = True
        _direction = direction
        _last_command = direction
        _last_command_time = datetime.now(timezone.utc).isoformat()
        _stop_event.clear()

    _log_command(direction)
    thread = threading.Thread(
        target=_run_relay,
        args=(active_pin, idle_pin, DOOR_TIME),
        daemon=True,
    )
    thread.start()
    return True


def _status():
    with _lock:
        busy = _busy
        direction = _direction
        last_command = _last_command
        last_command_time = _last_command_time
        likely_state = _likely_state
        history = list(_command_history)
    if busy:
        message = '{} the gate...'.format('Raising' if direction == 'up' else 'Lowering')
    else:
        message = 'Ready'
    return {
        'busy': busy,
        'direction': direction,
        'message': message,
        'last_command': last_command,
        'last_command_time': last_command_time,
        'likely_state': likely_state,
        'history': history,
        'geofence': {'lat': GATE_LAT, 'lon': GATE_LON, 'radius_m': GEOFENCE_RADIUS_M},
    }


# ── Geofencing ───────────────────────────────────────────────────────────────

def _distance_m(lat1, lon1, lat2, lon2):
    """Great-circle distance between two WGS84 points, in metres."""
    earth_radius_m = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * earth_radius_m * math.asin(math.sqrt(a))


def _geofence_error(payload):
    """Return an error message if *payload* lacks a valid, in-range location."""
    if not payload or 'lat' not in payload or 'lon' not in payload:
        return 'Your location is required to operate the gate.'
    try:
        lat = float(payload['lat'])
        lon = float(payload['lon'])
    except (TypeError, ValueError):
        return 'Invalid location.'
    distance = _distance_m(lat, lon, GATE_LAT, GATE_LON)
    if distance > GEOFENCE_RADIUS_M:
        return 'You must be within {:.0f}m of the gate to operate it (you are {:.0f}m away).'.format(
            GEOFENCE_RADIUS_M, distance
        )
    return None


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/api/status', methods=['GET'])
def api_status():
    return jsonify(_status())


@app.route('/api/up', methods=['POST'])
def api_up():
    geofence_error = _geofence_error(request.get_json(silent=True))
    if geofence_error:
        return jsonify({**_status(), 'error': geofence_error}), 403
    if not _start_move(UP_GPIO, DOWN_GPIO, 'up'):
        return jsonify({**_status(), 'error': 'A move is already in progress.'}), 409
    return jsonify(_status())


@app.route('/api/down', methods=['POST'])
def api_down():
    geofence_error = _geofence_error(request.get_json(silent=True))
    if geofence_error:
        return jsonify({**_status(), 'error': geofence_error}), 403
    if not _start_move(DOWN_GPIO, UP_GPIO, 'down'):
        return jsonify({**_status(), 'error': 'A move is already in progress.'}), 409
    return jsonify(_status())


@app.route('/api/stop', methods=['POST'])
def api_stop():
    global _busy, _direction, _last_command, _last_command_time, _likely_state
    # Stop is a safety action and is never geofenced or blocked.
    # Signal the running relay thread to stop waiting; also make sure the
    # relays are released immediately, regardless of thread state.
    _stop_event.set()
    GPIO.output(UP_GPIO, GPIO.HIGH)
    GPIO.output(DOWN_GPIO, GPIO.HIGH)
    with _lock:
        was_busy = _busy
        _busy = False
        _direction = None
        _last_command = 'stop'
        _last_command_time = datetime.now(timezone.utc).isoformat()
        # A stop issued while idle doesn't change the known position; a stop
        # mid-move leaves the position unknown.
        if was_busy:
            _likely_state = 'unknown'
    _log_command('stop')
    return jsonify(_status())


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('Starting gate-control Flask app on http://0.0.0.0:{}'.format(port))
    app.run(host='0.0.0.0', port=port)
