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

// Stop is a safety action: no confirmation dialog, fire immediately.
stopBtn.addEventListener('click', () => performAction('stop'));

async function performAction(action) {
  try {
    const resp = await fetch(`/api/${action}`, { method: 'POST' });
    const data = await resp.json();
    updateStatus(data);
  } catch (err) {
    statusEl.textContent = 'Error contacting the gate controller.';
  }
}

function updateStatus(data) {
  statusEl.textContent = data.error ? data.error : data.message;
  const busy = !!data.busy;
  upBtn.disabled = busy;
  downBtn.disabled = busy;
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
