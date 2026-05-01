#!/usr/bin/env python

"""
Flask web app for controlling the gate without ROS.
Provides a simple UI with Up and Down buttons that drive
the same GPIO relays used by the ROS node.
"""

import atexit
import threading
import time
import RPi.GPIO as GPIO
from flask import Flask, redirect, url_for

app = Flask(__name__)

UP_GPIO = 19
DOWN_GPIO = 26
DOOR_TIME = 17  # seconds

# Track whether a move is already in progress
_lock = threading.Lock()
_busy = False

# ── GPIO initialisation ────────────────────────────────────────────────────────

GPIO.setmode(GPIO.BCM)
GPIO.setup(UP_GPIO, GPIO.OUT)
GPIO.setup(DOWN_GPIO, GPIO.OUT)
GPIO.output(UP_GPIO, GPIO.HIGH)   # relay off
GPIO.output(DOWN_GPIO, GPIO.HIGH) # relay off

atexit.register(GPIO.cleanup)


# ── HTML template ──────────────────────────────────────────────────────────────

_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Gate Control</title>
  <style>
    body {{
      font-family: sans-serif;
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 100vh;
      margin: 0;
      background: #f0f4f8;
    }}
    h1 {{ margin-bottom: 2rem; color: #333; }}
    .buttons {{ display: flex; gap: 2rem; }}
    button {{
      padding: 1.5rem 3rem;
      font-size: 1.4rem;
      border: none;
      border-radius: 8px;
      cursor: pointer;
      color: #fff;
      transition: opacity 0.2s;
    }}
    button:disabled {{ opacity: 0.5; cursor: not-allowed; }}
    .up   {{ background: #27ae60; }}
    .down {{ background: #c0392b; }}
    .status {{
      margin-top: 2rem;
      font-size: 1.1rem;
      color: #555;
      min-height: 1.5em;
    }}
  </style>
</head>
<body>
  <h1>Gate Control</h1>
  <div class="buttons">
    <form method="post" action="/up">
      <button class="up" {disabled}>&#8679; Up</button>
    </form>
    <form method="post" action="/down">
      <button class="down" {disabled}>&#8681; Down</button>
    </form>
  </div>
  <p class="status">{status}</p>
</body>
</html>"""


def _render(status=""):
    with _lock:
        disabled = 'disabled' if _busy else ''
    return _PAGE.format(status=status, disabled=disabled)


# ── GPIO helpers ───────────────────────────────────────────────────────────────

def _run_relay(active_pin, idle_pin, duration):
    """Energise *active_pin* for *duration* seconds then release it."""
    global _busy
    try:
        # Ensure the idle relay is off before activating the other (safety measure)
        GPIO.output(idle_pin, GPIO.HIGH)
        GPIO.output(active_pin, GPIO.LOW)
        time.sleep(duration)
        GPIO.output(active_pin, GPIO.HIGH)
    finally:
        with _lock:
            _busy = False


# ── Routes ─────────────────────────────────────────────────────────────────────

@app.route('/', methods=['GET'])
def index():
    return _render()


@app.route('/up', methods=['POST'])
def up():
    global _busy
    with _lock:
        if _busy:
            return _render("A move is already in progress — please wait."), 409
        _busy = True

    thread = threading.Thread(
        target=_run_relay,
        args=(UP_GPIO, DOWN_GPIO, DOOR_TIME),
        daemon=True,
    )
    thread.start()
    return redirect(url_for('index'))


@app.route('/down', methods=['POST'])
def down():
    global _busy
    with _lock:
        if _busy:
            return _render("A move is already in progress — please wait."), 409
        _busy = True

    thread = threading.Thread(
        target=_run_relay,
        args=(DOWN_GPIO, UP_GPIO, DOOR_TIME),
        daemon=True,
    )
    thread.start()
    return redirect(url_for('index'))


# ── Entry point ────────────────────────────────────────────────────────────────

if __name__ == '__main__':
    print('Starting gate-control Flask app on http://0.0.0.0:5000')
    app.run(host='0.0.0.0', port=5000)
