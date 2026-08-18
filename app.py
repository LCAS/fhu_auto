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
                   "up"|"down"|null, "message": str}.
POST /api/up      Start raising the gate. Returns 409 if a move is
                   already in progress.
POST /api/down     Start lowering the gate. Returns 409 if a move is
                   already in progress.
POST /api/stop     Immediately stop any door movement and release the
                   relays. Always returns 200.
"""

import atexit
import os
import threading

from flask import Flask, jsonify, render_template

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

# Protects access to the shared state below.
_lock = threading.Lock()
_busy = False
_direction = None  # 'up' or 'down' while a move is in progress
_stop_event = threading.Event()

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
    global _busy, _direction
    try:
        # Ensure the idle relay is off before activating the other (safety measure)
        GPIO.output(idle_pin, GPIO.HIGH)
        GPIO.output(active_pin, GPIO.LOW)

        # Wait in small increments so a stop request is honoured quickly.
        _stop_event.wait(duration)

        GPIO.output(active_pin, GPIO.HIGH)
    finally:
        GPIO.output(active_pin, GPIO.HIGH)
        GPIO.output(idle_pin, GPIO.HIGH)
        with _lock:
            _busy = False
            _direction = None


def _start_move(active_pin, idle_pin, direction):
    global _busy, _direction
    with _lock:
        if _busy:
            return False
        _busy = True
        _direction = direction
        _stop_event.clear()

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
    if busy:
        message = '{} the gate...'.format('Raising' if direction == 'up' else 'Lowering')
    else:
        message = 'Ready'
    return {'busy': busy, 'direction': direction, 'message': message}


# ── Routes ───────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET'])
def index():
    return render_template('index.html')


@app.route('/api/status', methods=['GET'])
def api_status():
    return jsonify(_status())


@app.route('/api/up', methods=['POST'])
def api_up():
    if not _start_move(UP_GPIO, DOWN_GPIO, 'up'):
        return jsonify({**_status(), 'error': 'A move is already in progress.'}), 409
    return jsonify(_status())


@app.route('/api/down', methods=['POST'])
def api_down():
    if not _start_move(DOWN_GPIO, UP_GPIO, 'down'):
        return jsonify({**_status(), 'error': 'A move is already in progress.'}), 409
    return jsonify(_status())


@app.route('/api/stop', methods=['POST'])
def api_stop():
    global _busy, _direction
    # Signal the running relay thread to stop waiting; also make sure the
    # relays are released immediately, regardless of thread state.
    _stop_event.set()
    GPIO.output(UP_GPIO, GPIO.HIGH)
    GPIO.output(DOWN_GPIO, GPIO.HIGH)
    with _lock:
        _busy = False
        _direction = None
    return jsonify(_status())


# ── Entry point ──────────────────────────────────────────────────────────────

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    print('Starting gate-control Flask app on http://0.0.0.0:{}'.format(port))
    app.run(host='0.0.0.0', port=port)
