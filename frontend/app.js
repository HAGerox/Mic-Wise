const MODAL_WAVEFORM_WINDOW_SECONDS = 300;
const MODAL_WAVEFORM_POINTS = 280;
const PROGRAM_AUTOSAVE_DELAY_MS = 450;

const state = {
  settings: null,
  channels: [],
  meterMap: new Map(),
  selectedChannelIds: new Set(),
  peerConnection: null,
  activeView: "monitor",
  multiListen: false,
  layoutMode: false,
  draggedChannelId: null,
  modalChannelId: null,
  modalWaveform: null,
  modalScrubSeconds: 0,
  waveformRefreshTimer: null,
  saveStatusByChannelId: new Map(),
};

const channelGrid = document.getElementById("channel-grid");
const programTableBody = document.getElementById("program-table-body");
const monitorView = document.getElementById("monitor-view");
const programView = document.getElementById("program-view");
const channelModalEmpty = document.getElementById("channel-modal-empty");
const monitorDock = document.querySelector(".monitor-dock");
const statusText = document.getElementById("status-text");
const listenModeText = document.getElementById("listen-mode-text");
const selectionCountText = document.getElementById("selection-count-text");
const monitorHelpText = document.getElementById("monitor-help-text");
const audioElement = document.getElementById("monitor-audio");
const stopListeningButton = document.getElementById("stop-listening");
const listenModeToggle = document.getElementById("listen-mode-toggle");
const layoutModeToggle = document.getElementById("layout-mode-toggle");
const viewMonitorButton = document.getElementById("view-monitor");
const viewProgramButton = document.getElementById("view-program");
const addChannelButton = document.getElementById("add-channel");
const channelModal = document.getElementById("channel-modal");
const closeModalButton = document.getElementById("close-modal");
const modalChannelNumber = document.getElementById("modal-channel-number");
const modalChannelName = document.getElementById("modal-channel-name");
const modalChannelMeta = document.getElementById("modal-channel-meta");
const modalTransportStatus = document.getElementById("modal-transport-status");
const modalPatchBadge = document.getElementById("modal-patch-badge");
const modalRecordBadge = document.getElementById("modal-record-badge");
const modalScrubLabel = document.getElementById("modal-scrub-label");
const modalListenLiveButton = document.getElementById("modal-listen-live");
const modalStopListeningButton = document.getElementById("modal-stop-listening");
const waveformCanvas = document.getElementById("waveform-canvas");

const programSaveTimers = new Map();
const programStatusTimers = new Map();

let layoutPlaceholder = null;
let layoutDragSourceCard = null;
let monitorViewportLayoutFrame = 0;

function formatPlaybackOffset(seconds) {
  const totalSeconds = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  return `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
}

async function waitForIceGatheringComplete(peerConnection, timeoutMs = 1200) {
  if (peerConnection.iceGatheringState === "complete") {
    return;
  }

  await new Promise((resolve) => {
    const timeoutId = window.setTimeout(() => {
      peerConnection.removeEventListener("icegatheringstatechange", handleChange);
      resolve();
    }, timeoutMs);

    function handleChange() {
      if (peerConnection.iceGatheringState !== "complete") {
        return;
      }

      window.clearTimeout(timeoutId);
      peerConnection.removeEventListener("icegatheringstatechange", handleChange);
      resolve();
    }

    peerConnection.addEventListener("icegatheringstatechange", handleChange);
  });
}

async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }

  if (response.status === 204) {
    return null;
  }

  const contentType = response.headers.get("Content-Type") ?? "";
  if (!contentType.includes("application/json")) {
    return null;
  }

  return response.json();
}

function sortChannels(channels) {
  return [...channels].sort((left, right) => {
    if (left.sort_index === right.sort_index) {
      return left.number - right.number;
    }
    return left.sort_index - right.sort_index;
  });
}

function getChannelById(channelId) {
  return state.channels.find((channel) => channel.id === channelId) ?? null;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function getInputLabel(channel) {
  return channel.input_index === null || channel.input_index === undefined
    ? "Unpatched"
    : `Input ${channel.input_index + 1}`;
}

function getAssignedMeter(channel) {
  if (channel.input_index === null || channel.input_index === undefined) {
    return null;
  }
  return state.meterMap.get(channel.input_index + 1) ?? null;
}

function getAvailableInputCount() {
  return Math.max(state.settings?.channel_count ?? 0, 0);
}

function shouldShowDockedPanel() {
  return state.activeView === "monitor" && state.modalChannelId !== null;
}

function applyMonitorViewportLayout() {
  const isMonitorView = state.activeView === "monitor";
  document.body.classList.toggle("monitor-view-active", isMonitorView);

  if (!isMonitorView || !monitorDock) {
    monitorView.style.removeProperty("--monitor-dock-height");
    return;
  }

  const dockHeight = Math.ceil(monitorDock.getBoundingClientRect().height);
  if (dockHeight > 0) {
    monitorView.style.setProperty("--monitor-dock-height", `${dockHeight}px`);
  }
}

function scheduleMonitorViewportLayout() {
  if (monitorViewportLayoutFrame) {
    window.cancelAnimationFrame(monitorViewportLayoutFrame);
  }

  monitorViewportLayoutFrame = window.requestAnimationFrame(() => {
    monitorViewportLayoutFrame = 0;
    applyMonitorViewportLayout();
  });
}

function getModalTransportState() {
  if (!state.modalChannelId || !state.selectedChannelIds.has(state.modalChannelId)) {
    return {
      isListening: false,
      isLive: false,
      statusText: "Not currently listening",
    };
  }

  if (state.modalScrubSeconds > 0) {
    return {
      isListening: true,
      isLive: false,
      statusText: `Listening ${formatPlaybackOffset(state.modalScrubSeconds)} behind live`,
    };
  }

  return {
    isListening: true,
    isLive: true,
    statusText: "Listening live",
  };
}

function setProgramRowStatus(channelId, text, tone = "neutral") {
  if (!text) {
    state.saveStatusByChannelId.delete(channelId);
  } else {
    state.saveStatusByChannelId.set(channelId, { text, tone });
  }

  const statusCell = programTableBody.querySelector(`[data-save-status="${channelId}"]`);
  if (!statusCell) {
    return;
  }

  statusCell.textContent = text ?? "";
  statusCell.className = "row-save-status";
  if (tone && text) {
    statusCell.classList.add(`is-${tone}`);
  }
}

function clearProgramRowStatusSoon(channelId, delay = 1200) {
  window.clearTimeout(programStatusTimers.get(channelId));
  const timer = window.setTimeout(() => {
    programStatusTimers.delete(channelId);
    setProgramRowStatus(channelId, "");
  }, delay);
  programStatusTimers.set(channelId, timer);
}

function cancelProgramRowSave(channelId) {
  window.clearTimeout(programSaveTimers.get(channelId));
  programSaveTimers.delete(channelId);
}

function scheduleProgramRowSave(channelId, delay = PROGRAM_AUTOSAVE_DELAY_MS) {
  cancelProgramRowSave(channelId);
  setProgramRowStatus(channelId, "Unsaved changes", "pending");
  const timer = window.setTimeout(() => {
    programSaveTimers.delete(channelId);
    void saveProgramRow(channelId);
  }, delay);
  programSaveTimers.set(channelId, timer);
}

function reconcileChannelState() {
  const validIds = new Set(state.channels.map((channel) => channel.id));
  const nextSelection = new Set(
    [...state.selectedChannelIds].filter((channelId) => validIds.has(channelId)),
  );
  const selectionChanged = nextSelection.size !== state.selectedChannelIds.size;
  state.selectedChannelIds = nextSelection;

  if (state.modalChannelId !== null && !validIds.has(state.modalChannelId)) {
    closeChannelModal();
  }

  for (const channelId of [...state.saveStatusByChannelId.keys()]) {
    if (!validIds.has(channelId)) {
      state.saveStatusByChannelId.delete(channelId);
    }
  }

  return selectionChanged;
}

function updateStatusCard() {
  listenModeText.textContent = state.multiListen ? "Multi" : "Single";
  listenModeToggle.textContent = state.multiListen ? "Multi listen" : "Single listen";
  listenModeToggle.classList.toggle("is-active", state.multiListen);
  layoutModeToggle.textContent = state.layoutMode ? "Done arranging" : "Arrange layout";
  layoutModeToggle.classList.toggle("is-active", state.layoutMode);
  const count = state.selectedChannelIds.size;
  selectionCountText.textContent = `${count} channel${count === 1 ? "" : "s"}`;
}

function updateViewButtons() {
  viewMonitorButton.classList.toggle("is-active", state.activeView === "monitor");
  viewProgramButton.classList.toggle("is-active", state.activeView === "program");
  monitorView.classList.toggle("is-hidden", state.activeView !== "monitor");
  programView.classList.toggle("is-hidden", state.activeView !== "program");
  layoutModeToggle.classList.toggle("is-hidden", state.activeView !== "monitor");
  monitorHelpText.textContent = state.layoutMode
    ? "Drag tiles around the grid and the placeholder will show where they will land."
    : "Click a channel tile to toggle listening and open its docked detail popup.";
}

function updateDockedPanelState() {
  const showDockedPanel = shouldShowDockedPanel();
  channelModalEmpty.classList.toggle("is-hidden", showDockedPanel);
  channelModal.classList.toggle("is-hidden", !showDockedPanel);
  channelModal.setAttribute("aria-hidden", showDockedPanel ? "false" : "true");
  scheduleMonitorViewportLayout();
}

function renderMonitorGrid() {
  channelGrid.innerHTML = "";

  for (const channel of sortChannels(state.channels)) {
    const meter = getAssignedMeter(channel);
    const level = meter ? Math.min(meter.rms * 100, 100) : 0;
    const card = document.createElement("article");
    card.className = "channel-card";
    card.dataset.channelId = String(channel.id);
    card.draggable = state.layoutMode;
    card.classList.toggle("is-selected", state.selectedChannelIds.has(channel.id));
    card.classList.toggle("is-layout-mode", state.layoutMode);
    card.innerHTML = `
      <header>
        <div>
          <div class="channel-number">CH ${channel.number}</div>
          <h2 class="channel-name">${escapeHtml(channel.name)}</h2>
        </div>
        <span class="channel-chip">${escapeHtml(getInputLabel(channel))}</span>
      </header>
      <div class="meter"><div class="meter-mask" style="width:${Math.max(0, 100 - level)}%"></div></div>
      <div class="channel-meta-row">
        <span class="channel-actions">${state.layoutMode ? "Drag to reorder" : "Tap for detail + listen"}</span>
      </div>
    `;

    card.addEventListener("click", async () => {
      if (state.layoutMode || state.draggedChannelId !== null) {
        return;
      }
      await handleChannelCardInteraction(channel.id);
    });

    card.addEventListener("dragstart", (event) => {
      handleLayoutDragStart(event, channel.id);
    });

    card.addEventListener("dragend", () => {
      cleanupLayoutDrag();
    });

    channelGrid.appendChild(card);
  }
}

function renderProgramTable() {
  programTableBody.innerHTML = "";

  const inputOptions = Array.from({ length: getAvailableInputCount() }, (_, index) => index);
  for (const channel of sortChannels(state.channels)) {
    const saveState = state.saveStatusByChannelId.get(channel.id);
    const row = document.createElement("tr");
    row.dataset.channelId = String(channel.id);
    row.innerHTML = `
      <td>CH ${channel.number}</td>
      <td>
        <div class="program-name-field">
          <input type="text" data-field="name" value="${escapeHtml(channel.name)}" />
          <span
            class="row-save-status ${saveState ? `is-${saveState.tone}` : ""}"
            data-save-status="${channel.id}"
          >${escapeHtml(saveState?.text ?? "")}</span>
        </div>
      </td>
      <td>
        <select data-field="input_index">
          <option value="">Unpatched</option>
          ${inputOptions
            .map(
              (index) => `
                <option value="${index}" ${channel.input_index === index ? "selected" : ""}>
                  Input ${index + 1}
                </option>
              `,
            )
            .join("")}
        </select>
      </td>
      <td class="checkbox-cell">
        <input type="checkbox" data-field="is_record_enabled" ${channel.is_record_enabled ? "checked" : ""} />
      </td>
      <td>
        <button type="button" class="button-danger" data-remove-channel="${channel.id}">Remove</button>
      </td>
    `;
    programTableBody.appendChild(row);
  }

  for (const row of programTableBody.querySelectorAll("tr[data-channel-id]")) {
    const channelId = Number(row.dataset.channelId);
    const nameInput = row.querySelector('[data-field="name"]');
    const inputSelect = row.querySelector('[data-field="input_index"]');
    const recordCheckbox = row.querySelector('[data-field="is_record_enabled"]');
    const removeButton = row.querySelector(`[data-remove-channel="${channelId}"]`);

    nameInput.addEventListener("input", () => {
      scheduleProgramRowSave(channelId);
    });
    nameInput.addEventListener("blur", () => {
      void saveProgramRow(channelId);
    });
    inputSelect.addEventListener("change", () => {
      scheduleProgramRowSave(channelId, 0);
    });
    recordCheckbox.addEventListener("change", () => {
      scheduleProgramRowSave(channelId, 0);
    });
    removeButton.addEventListener("click", async () => {
      await removeChannel(channelId);
    });
  }
}

function renderAll() {
  updateStatusCard();
  updateViewButtons();
  updateDockedPanelState();
  renderMonitorGrid();
  renderProgramTable();
  updateModalContent();
  scheduleMonitorViewportLayout();
}

function updateMeters(snapshot) {
  for (const channelMeter of snapshot.channels) {
    state.meterMap.set(channelMeter.channel, channelMeter);
  }

  for (const channel of state.channels) {
    const meter = getAssignedMeter(channel);
    const mask = channelGrid.querySelector(`[data-channel-id="${channel.id}"] .meter-mask`);
    if (!mask) {
      continue;
    }
    const level = meter ? Math.min(meter.rms * 100, 100) : 0;
    mask.style.width = `${Math.max(0, 100 - level)}%`;
  }
}

async function stopListening() {
  if (state.peerConnection) {
    state.peerConnection.getReceivers().forEach((receiver) => receiver.track?.stop());
    await state.peerConnection.close();
    state.peerConnection = null;
  }
  audioElement.srcObject = null;
  statusText.textContent = "Online";
}

function resetStopListeningButton(delay = 260) {
  window.setTimeout(() => {
    stopListeningButton.disabled = false;
    stopListeningButton.textContent = "Stop audio";
  }, delay);
}

async function handleStopAudioClick() {
  const hadActiveAudio = Boolean(state.peerConnection || state.selectedChannelIds.size);
  stopListeningButton.disabled = true;
  stopListeningButton.textContent = hadActiveAudio ? "Stopping…" : "Audio stopped";
  state.selectedChannelIds.clear();
  state.modalScrubSeconds = 0;
  await stopListening();
  renderAll();
  statusText.textContent = hadActiveAudio ? "Audio stopped" : "Online";
  resetStopListeningButton();
}

function orderedSelection() {
  return sortChannels(state.channels)
    .map((channel) => channel.id)
    .filter((channelId) => state.selectedChannelIds.has(channelId));
}

async function startListening(channelIds, replaySeconds = 0) {
  if (channelIds.length === 0) {
    await stopListening();
    return;
  }

  statusText.textContent = "Connecting audio…";
  await stopListening();

  const pc = new RTCPeerConnection({ iceServers: [] });
  state.peerConnection = pc;

  pc.addTransceiver("audio", { direction: "recvonly" });
  pc.ontrack = (event) => {
    const [stream] = event.streams;
    audioElement.srcObject = stream ?? new MediaStream([event.track]);
    void audioElement.play().catch(() => {
      statusText.textContent = "Stream ready";
    });
  };
  pc.onconnectionstatechange = () => {
    statusText.textContent = pc.connectionState === "connected"
      ? "Streaming"
      : `Streaming (${pc.connectionState})`;
  };

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);
  await waitForIceGatheringComplete(pc);

  const answer = await fetchJson("/api/streaming/webrtc/offer", {
    method: "POST",
    body: JSON.stringify({
      sdp: pc.localDescription.sdp,
      type: pc.localDescription.type,
      channel_ids: channelIds,
      replay_seconds: replaySeconds,
    }),
  });

  await pc.setRemoteDescription(answer);
}

async function syncListening(replaySeconds = 0) {
  const selection = orderedSelection();
  if (selection.length === 0) {
    await stopListening();
    renderAll();
    return;
  }
  await startListening(selection, replaySeconds);
  renderAll();
}

async function handleChannelCardInteraction(channelId) {
  if (state.multiListen) {
    if (state.selectedChannelIds.has(channelId)) {
      state.selectedChannelIds.delete(channelId);
    } else {
      state.selectedChannelIds.add(channelId);
    }
  } else if (state.selectedChannelIds.size === 1 && state.selectedChannelIds.has(channelId)) {
    state.selectedChannelIds.clear();
  } else {
    state.selectedChannelIds.clear();
    state.selectedChannelIds.add(channelId);
  }

  state.modalScrubSeconds = 0;
  openChannelModal(channelId);
  await syncListening(0);
}

function openChannelModal(channelId) {
  state.modalChannelId = channelId;
  state.modalScrubSeconds = 0;
  updateDockedPanelState();
  updateModalContent();
  void refreshModalWaveform();
  if (state.waveformRefreshTimer) {
    clearInterval(state.waveformRefreshTimer);
  }
  state.waveformRefreshTimer = window.setInterval(() => {
    void refreshModalWaveform();
  }, 2500);
}

function closeChannelModal() {
  if (document.activeElement instanceof HTMLElement) {
    document.activeElement.blur();
  }
  state.modalChannelId = null;
  state.modalWaveform = null;
  state.modalScrubSeconds = 0;
  if (state.waveformRefreshTimer) {
    clearInterval(state.waveformRefreshTimer);
    state.waveformRefreshTimer = null;
  }
  updateDockedPanelState();
}

function updateModalContent() {
  if (!state.modalChannelId) {
    return;
  }
  const channel = getChannelById(state.modalChannelId);
  if (!channel) {
    return;
  }

  const transportState = getModalTransportState();
  modalChannelNumber.textContent = `Channel ${channel.number}`;
  modalChannelName.textContent = channel.name;
  modalChannelMeta.textContent = channel.is_record_enabled
    ? "Rolling record enabled for this channel."
    : "Rolling record disabled for this channel.";
  modalTransportStatus.textContent = transportState.statusText;
  modalPatchBadge.textContent = getInputLabel(channel);
  modalRecordBadge.textContent = channel.is_record_enabled ? "Recording on" : "Recording off";
  modalScrubLabel.textContent = state.modalScrubSeconds > 0
    ? `${formatPlaybackOffset(state.modalScrubSeconds)} behind live • fixed offset`
    : "Click anywhere on the graph to scrub this channel in the past";
  modalListenLiveButton.textContent = transportState.isLive ? "Listening live" : "Listen live";
  modalListenLiveButton.classList.toggle("is-active", transportState.isLive);
  modalStopListeningButton.textContent = transportState.isListening ? "Stop this channel" : "Stopped";
  modalStopListeningButton.disabled = !transportState.isListening;
  scheduleMonitorViewportLayout();
}

async function refreshModalWaveform() {
  if (!state.modalChannelId) {
    return;
  }

  const waveform = await fetchJson(
    `/api/channels/${state.modalChannelId}/waveform?seconds=${MODAL_WAVEFORM_WINDOW_SECONDS}&points=${MODAL_WAVEFORM_POINTS}`,
  );
  state.modalWaveform = waveform;
  updateModalContent();
  drawWaveform();
}

function resizeCanvas(canvas) {
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = Math.floor(width * ratio);
  canvas.height = Math.floor(height * ratio);
  const context = canvas.getContext("2d");
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width, height };
}

function drawWaveform() {
  if (!state.modalWaveform) {
    return;
  }

  const { context, width, height } = resizeCanvas(waveformCanvas);
  context.clearRect(0, 0, width, height);
  context.fillStyle = "#020617";
  context.fillRect(0, 0, width, height);

  context.strokeStyle = "rgba(148, 163, 184, 0.15)";
  context.lineWidth = 1;
  for (let line = 1; line < 4; line += 1) {
    const y = (height / 4) * line;
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }

  const values = state.modalWaveform.points;
  const availableSeconds = Math.min(state.modalWaveform.seconds, MODAL_WAVEFORM_WINDOW_SECONDS);
  const occupiedWidth = width * (availableSeconds / MODAL_WAVEFORM_WINDOW_SECONDS);
  const startX = width - occupiedWidth;
  const barWidth = values.length > 0 ? occupiedWidth / values.length : occupiedWidth;
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    const x = startX + index * barWidth;
    const barHeight = Math.max(2, value * (height - 20));
    context.fillStyle = "rgba(56, 189, 248, 0.9)";
    context.fillRect(x, height - barHeight, Math.max(1, barWidth - 1), barHeight);
  }

  if (state.modalScrubSeconds > 0) {
    const markerX = width * (1 - Math.min(state.modalScrubSeconds, MODAL_WAVEFORM_WINDOW_SECONDS) / MODAL_WAVEFORM_WINDOW_SECONDS);
    context.strokeStyle = "#f97316";
    context.lineWidth = 2;
    context.beginPath();
    context.moveTo(markerX, 0);
    context.lineTo(markerX, height);
    context.stroke();
  }
}

async function scrubModalWaveform(event) {
  if (!state.modalChannelId || !state.modalWaveform) {
    return;
  }
  const rect = waveformCanvas.getBoundingClientRect();
  const position = Math.min(Math.max(event.clientX - rect.left, 0), rect.width);
  const ratio = position / rect.width;
  const requestedReplaySeconds = Math.max(0, MODAL_WAVEFORM_WINDOW_SECONDS * (1 - ratio));
  const replaySeconds = Math.min(requestedReplaySeconds, state.modalWaveform.seconds);
  state.modalScrubSeconds = replaySeconds;
  state.selectedChannelIds.clear();
  state.selectedChannelIds.add(state.modalChannelId);
  drawWaveform();
  updateModalContent();
  await syncListening(replaySeconds);
}

function getProgramRowPayload(channelId) {
  const row = programTableBody.querySelector(`[data-channel-id="${channelId}"]`);
  if (!row) {
    return null;
  }

  const existingChannel = getChannelById(channelId);
  return {
    name:
      row.querySelector('[data-field="name"]').value.trim()
      || existingChannel?.name
      || `Channel ${channelId}`,
    input_index: row.querySelector('[data-field="input_index"]').value === ""
      ? null
      : Number(row.querySelector('[data-field="input_index"]').value),
    is_record_enabled: row.querySelector('[data-field="is_record_enabled"]').checked,
  };
}

async function saveProgramRow(channelId) {
  cancelProgramRowSave(channelId);
  const payload = getProgramRowPayload(channelId);
  if (!payload) {
    return;
  }

  setProgramRowStatus(channelId, "Saving…", "saving");
  window.clearTimeout(programStatusTimers.get(channelId));

  try {
    const updatedChannel = await fetchJson(`/api/channels/${channelId}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });
    state.channels = state.channels.map((channel) =>
      channel.id === channelId ? updatedChannel : channel,
    );
    updateModalContent();
    renderMonitorGrid();
    setProgramRowStatus(channelId, "Saved", "saved");
    clearProgramRowStatusSoon(channelId);
  } catch (error) {
    console.error(error);
    setProgramRowStatus(channelId, "Save failed", "error");
  }
}

function captureProgramRowRects() {
  if (state.activeView !== "program") {
    return null;
  }

  return new Map(
    [...programTableBody.querySelectorAll("tr[data-channel-id]")].map((row) => [
      Number(row.dataset.channelId),
      row.getBoundingClientRect(),
    ]),
  );
}

function animateProgramRows(previousRowRects) {
  if (!previousRowRects || state.activeView !== "program") {
    return;
  }

  for (const row of programTableBody.querySelectorAll("tr[data-channel-id]")) {
    const channelId = Number(row.dataset.channelId);
    const currentRect = row.getBoundingClientRect();
    const previousRect = previousRowRects.get(channelId);

    if (previousRect) {
      const deltaY = previousRect.top - currentRect.top;
      if (Math.abs(deltaY) > 1) {
        row.animate(
          [
            { transform: `translateY(${deltaY}px)` },
            { transform: "translateY(0)" },
          ],
          {
            duration: 220,
            easing: "cubic-bezier(0.22, 1, 0.36, 1)",
          },
        );
      }
      continue;
    }

    row.animate(
      [
        { opacity: 0, transform: "translateY(12px)" },
        { opacity: 1, transform: "translateY(0)" },
      ],
      {
        duration: 220,
        easing: "ease-out",
      },
    );
  }
}

async function refreshChannels() {
  const previousRowRects = captureProgramRowRects();
  state.channels = await fetchJson("/api/channels");
  const selectionChanged = reconcileChannelState();
  renderAll();
  animateProgramRows(previousRowRects);
  if (selectionChanged) {
    await syncListening(0);
  }
}

async function addChannel() {
  addChannelButton.disabled = true;
  try {
    await fetchJson("/api/channels", {
      method: "POST",
      body: JSON.stringify({}),
    });
    await refreshChannels();
    const newestChannel = sortChannels(state.channels).at(-1);
    const newestNameInput = newestChannel
      ? programTableBody.querySelector(`[data-channel-id="${newestChannel.id}"] [data-field="name"]`)
      : null;
    newestNameInput?.focus();
    newestNameInput?.select();
  } finally {
    addChannelButton.disabled = false;
  }
}

async function removeChannel(channelId) {
  const removeButton = programTableBody.querySelector(`[data-remove-channel="${channelId}"]`);
  if (removeButton) {
    removeButton.disabled = true;
    removeButton.textContent = "Removing…";
  }
  cancelProgramRowSave(channelId);
  window.clearTimeout(programStatusTimers.get(channelId));
  await fetchJson(`/api/channels/${channelId}`, { method: "DELETE" });
  state.saveStatusByChannelId.delete(channelId);
  await refreshChannels();
}

async function persistChannelOrder(orderedIds) {
  const channelById = new Map(state.channels.map((channel) => [channel.id, channel]));
  const changedChannels = [];
  state.channels = orderedIds.map((channelId, sortIndex) => {
    const channel = channelById.get(channelId);
    if (channel.sort_index !== sortIndex) {
      changedChannels.push({ id: channelId, sort_index: sortIndex });
    }
    return { ...channel, sort_index: sortIndex };
  });

  renderAll();

  await Promise.all(
    changedChannels.map((channel) =>
      fetchJson(`/api/channels/${channel.id}`, {
        method: "PATCH",
        body: JSON.stringify({ sort_index: channel.sort_index }),
      }),
    ),
  );
}

function getDropReference(clientX, clientY) {
  const cards = [...channelGrid.querySelectorAll(".channel-card")]
    .filter((card) => card !== layoutPlaceholder && card !== layoutDragSourceCard);
  const rows = [];

  for (const card of cards) {
    const rect = card.getBoundingClientRect();
    const existingRow = rows.find((row) => Math.abs(row.top - rect.top) < 12);
    if (existingRow) {
      existingRow.cards.push({ card, rect });
      existingRow.bottom = Math.max(existingRow.bottom, rect.bottom);
      continue;
    }

    rows.push({
      top: rect.top,
      bottom: rect.bottom,
      cards: [{ card, rect }],
    });
  }

  rows.sort((left, right) => left.top - right.top);
  for (const row of rows) {
    row.cards.sort((left, right) => left.rect.left - right.rect.left);
    row.centerY = (row.top + row.bottom) / 2;
  }

  const hoveredRow = rows.reduce((closestRow, candidateRow) => {
    if (!closestRow) {
      return candidateRow;
    }
    return Math.abs(candidateRow.centerY - clientY) < Math.abs(closestRow.centerY - clientY)
      ? candidateRow
      : closestRow;
  }, null);

  if (!hoveredRow) {
    return null;
  }

  const referenceInRow = hoveredRow.cards.find(({ rect }) => clientX < rect.left + rect.width / 2);
  if (referenceInRow) {
    return referenceInRow.card;
  }

  const rowIndex = rows.indexOf(hoveredRow);
  const nextRow = rows[rowIndex + 1];
  return nextRow ? nextRow.cards[0].card : null;
}

function handleLayoutDragStart(event, channelId) {
  if (!state.layoutMode) {
    event.preventDefault();
    return;
  }

  state.draggedChannelId = channelId;
  layoutDragSourceCard = event.currentTarget;
  layoutPlaceholder = document.createElement("article");
  layoutPlaceholder.className = "channel-card channel-card--placeholder";
  layoutPlaceholder.innerHTML = '<div class="placeholder-label">Drop here</div>';
  layoutPlaceholder.style.height = `${layoutDragSourceCard.offsetHeight}px`;
  layoutDragSourceCard.after(layoutPlaceholder);
  event.dataTransfer.effectAllowed = "move";
  event.dataTransfer.setData("text/plain", String(channelId));
  window.setTimeout(() => {
    layoutDragSourceCard?.classList.add("is-dragging-source");
  }, 0);
}

function handleLayoutDragOver(event) {
  if (!state.layoutMode || state.draggedChannelId === null || !layoutPlaceholder) {
    return;
  }

  event.preventDefault();
  const referenceCard = getDropReference(event.clientX, event.clientY);
  if (referenceCard) {
    channelGrid.insertBefore(layoutPlaceholder, referenceCard);
  } else {
    channelGrid.appendChild(layoutPlaceholder);
  }
}

async function handleLayoutDrop(event) {
  if (!state.layoutMode || state.draggedChannelId === null || !layoutPlaceholder) {
    return;
  }

  event.preventDefault();
  const siblings = [...channelGrid.children].filter((element) => element !== layoutDragSourceCard);
  const insertIndex = siblings.indexOf(layoutPlaceholder);
  const orderedIds = [...channelGrid.querySelectorAll(".channel-card[data-channel-id]")]
    .filter((element) => element !== layoutDragSourceCard)
    .map((element) => Number(element.dataset.channelId));
  orderedIds.splice(insertIndex, 0, state.draggedChannelId);

  cleanupLayoutDrag();
  await persistChannelOrder(orderedIds);
}

function cleanupLayoutDrag() {
  layoutDragSourceCard?.classList.remove("is-dragging-source");
  layoutPlaceholder?.remove();
  layoutPlaceholder = null;
  layoutDragSourceCard = null;
  state.draggedChannelId = null;
}

async function patchSettings(changes) {
  state.settings = await fetchJson("/api/settings", {
    method: "PATCH",
    body: JSON.stringify(changes),
  });
  state.multiListen = state.settings.multi_listen_enabled;
  state.activeView = state.settings.active_mode === "configure" ? "program" : state.settings.active_mode;
  renderAll();
}

async function setActiveView(view) {
  if (view !== "monitor") {
    closeChannelModal();
  }
  state.activeView = view;
  renderAll();
  await patchSettings({ active_mode: view === "program" ? "configure" : "monitor" });
}

async function toggleListenMode() {
  state.multiListen = !state.multiListen;
  if (!state.multiListen && state.selectedChannelIds.size > 1) {
    const [firstSelected] = orderedSelection();
    state.selectedChannelIds = new Set(firstSelected ? [firstSelected] : []);
    await syncListening(0);
  }
  renderAll();
  await patchSettings({ multi_listen_enabled: state.multiListen });
}

function toggleLayoutMode() {
  state.layoutMode = !state.layoutMode;
  if (state.layoutMode) {
    closeChannelModal();
  } else {
    cleanupLayoutDrag();
  }
  renderAll();
}

function connectMeterSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const meterSocket = new WebSocket(`${protocol}://${window.location.host}/ws/meters`);
  meterSocket.onmessage = (event) => updateMeters(JSON.parse(event.data));
  meterSocket.onopen = () => {
    statusText.textContent = "Online";
  };
  meterSocket.onerror = () => {
    statusText.textContent = "Meter socket error";
  };
}

async function bootstrap() {
  stopListeningButton.addEventListener("click", () => {
    void handleStopAudioClick();
  });
  listenModeToggle.addEventListener("click", toggleListenMode);
  layoutModeToggle.addEventListener("click", toggleLayoutMode);
  viewMonitorButton.addEventListener("click", () => setActiveView("monitor"));
  viewProgramButton.addEventListener("click", () => setActiveView("program"));
  addChannelButton.addEventListener("click", addChannel);
  closeModalButton.addEventListener("click", closeChannelModal);
  modalStopListeningButton.addEventListener("click", async () => {
    if (!state.modalChannelId) {
      return;
    }
    state.selectedChannelIds.delete(state.modalChannelId);
    state.modalScrubSeconds = 0;
    await syncListening(0);
  });
  modalListenLiveButton.addEventListener("click", async () => {
    if (!state.modalChannelId) {
      return;
    }
    state.modalScrubSeconds = 0;
    if (!state.multiListen) {
      state.selectedChannelIds.clear();
    }
    state.selectedChannelIds.add(state.modalChannelId);
    updateModalContent();
    drawWaveform();
    await syncListening(0);
  });
  waveformCanvas.addEventListener("click", scrubModalWaveform);
  channelGrid.addEventListener("dragover", handleLayoutDragOver);
  channelGrid.addEventListener("drop", (event) => {
    void handleLayoutDrop(event);
  });
  window.addEventListener("resize", () => {
    drawWaveform();
    scheduleMonitorViewportLayout();
  });

  const [health, settings, channels, latestMeters] = await Promise.all([
    fetchJson("/api/health"),
    fetchJson("/api/settings"),
    fetchJson("/api/channels"),
    fetchJson("/api/meters/latest"),
  ]);

  statusText.textContent = health.audio_engine_running ? "Online" : "Starting";
  state.settings = settings;
  state.channels = channels;
  state.multiListen = settings.multi_listen_enabled;
  state.activeView = settings.active_mode === "configure" ? "program" : settings.active_mode;
  for (const channelMeter of latestMeters.channels) {
    state.meterMap.set(channelMeter.channel, channelMeter);
  }
  renderAll();
  connectMeterSocket();
}

bootstrap().catch((error) => {
  console.error(error);
  statusText.textContent = "Startup failed";
});
