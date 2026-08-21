/* Gate control UI logic: confirmation modal with press-and-hold-to-confirm. */

const HOLD_DURATION_MS = 2000;

const statusEl = document.getElementById('status');
const backdrop = document.getElementById('modal-backdrop');
const modalActionText = document.getElementById('modal-action-text');
const confirmBtn = document.getElementById('modal-confirm');
const cancelBtn = document.getElementById('modal-cancel');
const confirmProgress = confirmBtn.querySelector('.confirm-progress');
const upBtn = document.getElementById('btn-up');
const downBtn = document.getElementById('btn-down');
const stopBtn = document.getElementById('btn-stop');
const modalStopBtn = document.getElementById('modal-stop');
const historyList = document.getElementById('history-list');
const geofenceStatusEl = document.getElementById('geofence-status');

// Whether the client is known to be within range of the gate; null while
// unknown/unchecked. Up/Down are only enabled once this is true.
let geofenceOk = null;

let pendingAction = null;
let holdTimer = null;
let holdStart = null;
let holdRaf = null;

function resetConfirmVisual() {
  confirmProgress.style.transition = 'none';
  confirmProgress.style.width = '0%';
}

function openModal(action, label) {
  pendingAction = action;
  modalActionText.textContent = `You are about to ${label} the gate.`;
  resetConfirmVisual();
  backdrop.classList.remove('hidden');
}

function closeModal() {
  backdrop.classList.add('hidden');
  pendingAction = null;
  cancelHold();
}

function startHold() {
  if (!pendingAction) return;
  holdStart = Date.now();
  confirmProgress.style.transition = `width ${HOLD_DURATION_MS}ms linear`;
  // Force reflow so the transition restarts each time.
  // eslint-disable-next-line no-unused-expressions
  confirmProgress.offsetWidth;
  confirmProgress.style.width = '100%';

  holdTimer = setTimeout(() => {
    const action = pendingAction;
    closeModal();
    performAction(action);
  }, HOLD_DURATION_MS);
}

function cancelHold() {
  if (holdTimer) {
    clearTimeout(holdTimer);
    holdTimer = null;
  }
  if (holdRaf) {
    cancelAnimationFrame(holdRaf);
    holdRaf = null;
  }
  resetConfirmVisual();
}

confirmBtn.addEventListener('mousedown', startHold);
confirmBtn.addEventListener('touchstart', (e) => {
  e.preventDefault();
  startHold();
}, { passive: false });

['mouseup', 'mouseleave', 'touchend', 'touchcancel'].forEach((evt) => {
  confirmBtn.addEventListener(evt, cancelHold);
});

cancelBtn.addEventListener('click', closeModal);
backdrop.addEventListener('click', (e) => {
  if (e.target === backdrop) closeModal();
});

upBtn.addEventListener('click', () => openModal('up', 'raise'));
downBtn.addEventListener('click', () => openModal('down', 'lower'));

// Stop is a safety action: no confirmation dialog, no location check, fire
// immediately. It is also available inside the modal, so a move can be
// interrupted without needing to dismiss the confirmation dialog first.
function stopNow() {
  closeModal();
  performStop();
}

stopBtn.addEventListener('click', stopNow);
modalStopBtn.addEventListener('click', stopNow);

async function performStop() {
  try {
    const resp = await fetch('/api/stop', { method: 'POST' });
    const data = await resp.json();
    updateStatus(data);
  } catch (err) {
    statusEl.textContent = 'Error contacting the gate controller.';
  }
}

async function performAction(action) {
  try {
    const position = await getPosition();
    const resp = await fetch(`/api/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(position),
    });
    const data = await resp.json();
    updateStatus(data);
  } catch (err) {
    statusEl.textContent = err.message || 'Error contacting the gate controller.';
  }
}

// The gate is geofenced server-side; the client's location must be sent
// with every up/down command so the server can check it is close enough.
function getPosition() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error('Geolocation is not supported by this browser.'));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => reject(new Error('Unable to determine your location. Enable location access to operate the gate.')),
      { enableHighAccuracy: true, timeout: 10000, maximumAge: 10000 }
    );
  });
}

function distanceMeters(lat1, lon1, lat2, lon2) {
  const earthRadiusM = 6371000;
  const toRad = (deg) => (deg * Math.PI) / 180;
  const dPhi = toRad(lat2 - lat1);
  const dLambda = toRad(lon2 - lon1);
  const a = Math.sin(dPhi / 2) ** 2
    + Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLambda / 2) ** 2;
  return 2 * earthRadiusM * Math.asin(Math.sqrt(a));
}

// Checked once on load: fetches the gate's geofence config, gets the
// client's position, and enables/disables Up/Down accordingly.
async function checkGeofence() {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    const { lat, lon, radius_m: radiusM } = data.geofence;
    const position = await getPosition();
    const distance = distanceMeters(position.lat, position.lon, lat, lon);
    geofenceOk = distance <= radiusM;
    geofenceStatusEl.textContent = geofenceOk
      ? `You are ${Math.round(distance)}m from the gate – within range to operate Up/Down.`
      : `You are ${Math.round(distance)}m from the gate – must be within ${radiusM}m to operate Up/Down.`;
    updateStatus(data);
  } catch (err) {
    geofenceOk = false;
    geofenceStatusEl.textContent = err.message || 'Unable to determine your location; Up/Down are disabled.';
    updateStatus({ busy: false, message: 'Ready' });
  }
}

const LIKELY_STATE_LABELS = { open: 'likely open', closed: 'likely closed', unknown: 'position unknown' };

function updateStatus(data) {
  let message = data.error ? data.error : data.message;
  if (!data.busy && data.likely_state) {
    message += ` (${LIKELY_STATE_LABELS[data.likely_state] || data.likely_state})`;
  }
  statusEl.textContent = message;
  const busy = !!data.busy;
  upBtn.disabled = busy || geofenceOk !== true;
  downBtn.disabled = busy || geofenceOk !== true;
  renderHistory(data.history);
}

function renderHistory(history) {
  if (!Array.isArray(history)) return;
  historyList.innerHTML = '';
  history.forEach((entry) => {
    const li = document.createElement('li');
    const time = new Date(entry.time).toLocaleString();
    li.textContent = `${entry.command} – ${time}`;
    historyList.appendChild(li);
  });
}

async function pollStatus() {
  try {
    const resp = await fetch('/api/status');
    const data = await resp.json();
    updateStatus(data);
  } catch (err) {
    // Ignore transient network errors while polling.
  }
}

pollStatus();
setInterval(pollStatus, 2000);
checkGeofence();
