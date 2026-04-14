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
};

const channelGrid = document.getElementById("channel-grid");
const programTableBody = document.getElementById("program-table-body");
const monitorView = document.getElementById("monitor-view");
const programView = document.getElementById("program-view");
const statusText = document.getElementById("status-text");
const modeText = document.getElementById("mode-text");
const listenModeText = document.getElementById("listen-mode-text");
const selectionCountText = document.getElementById("selection-count-text");
const monitorHelpText = document.getElementById("monitor-help-text");
const audioElement = document.getElementById("monitor-audio");
const stopListeningButton = document.getElementById("stop-listening");
const listenModeToggle = document.getElementById("listen-mode-toggle");
const layoutModeToggle = document.getElementById("layout-mode-toggle");
const viewMonitorButton = document.getElementById("view-monitor");
const viewProgramButton = document.getElementById("view-program");
const channelModal = document.getElementById("channel-modal");
const closeModalButton = document.getElementById("close-modal");
const modalChannelNumber = document.getElementById("modal-channel-number");
const modalChannelName = document.getElementById("modal-channel-name");
const modalChannelMeta = document.getElementById("modal-channel-meta");
const modalPatchBadge = document.getElementById("modal-patch-badge");
const modalRecordBadge = document.getElementById("modal-record-badge");
const modalScrubLabel = document.getElementById("modal-scrub-label");
const modalListenLiveButton = document.getElementById("modal-listen-live");
const modalStopListeningButton = document.getElementById("modal-stop-listening");
const waveformCanvas = document.getElementById("waveform-canvas");

async function fetchJson(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });

  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
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

function updateStatusCard() {
  listenModeText.textContent = state.multiListen ? "Multi" : "Single";
  listenModeToggle.textContent = state.multiListen ? "Multi listen" : "Single listen";
  modeText.textContent = state.activeView === "monitor" ? "Monitor" : "Program Show";
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
    ? "Drag channel tiles to rearrange the grid, then leave arrange mode when finished."
    : "Click a channel tile to toggle listening and open its detail popup.";
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
      <div class="meter"><div class="meter-bar" style="width:${level}%"></div></div>
      <div class="channel-meta-row">
        <span class="tag tag--muted">${channel.is_record_enabled ? "Rolling record on" : "Rolling record off"}</span>
        <span class="channel-actions">${state.layoutMode ? "Drag to reorder" : "Tap for detail + listen"}</span>
      </div>
    `;

    card.addEventListener("click", async () => {
      if (state.layoutMode) {
        return;
      }
      await handleChannelCardInteraction(channel.id);
    });

    card.addEventListener("dragstart", () => {
      if (!state.layoutMode) {
        return;
      }
      state.draggedChannelId = channel.id;
    });

    card.addEventListener("dragover", (event) => {
      if (!state.layoutMode) {
        return;
      }
      event.preventDefault();
    });

    card.addEventListener("drop", async (event) => {
      if (!state.layoutMode) {
        return;
      }
      event.preventDefault();
      if (state.draggedChannelId === null || state.draggedChannelId === channel.id) {
        return;
      }
      await reorderChannels(state.draggedChannelId, channel.id);
      state.draggedChannelId = null;
    });

    channelGrid.appendChild(card);
  }
}

function renderProgramTable() {
  programTableBody.innerHTML = "";

  const inputOptions = Array.from({ length: state.settings.channel_count }, (_, index) => index);
  for (const channel of sortChannels(state.channels)) {
    const row = document.createElement("tr");
    row.dataset.channelId = String(channel.id);
    row.innerHTML = `
      <td>CH ${channel.number}</td>
      <td><input type="text" data-field="name" value="${escapeHtml(channel.name)}" /></td>
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
        <button type="button" data-save-channel="${channel.id}">Save</button>
        <span class="row-save-status" data-save-status="${channel.id}"></span>
      </td>
    `;
    programTableBody.appendChild(row);
  }

  for (const button of programTableBody.querySelectorAll("[data-save-channel]")) {
    button.addEventListener("click", async () => {
      await saveProgramRow(Number(button.dataset.saveChannel));
    });
  }
}

function renderAll() {
  updateStatusCard();
  updateViewButtons();
  renderMonitorGrid();
  renderProgramTable();
  updateModalContent();
}

function updateMeters(snapshot) {
  for (const channelMeter of snapshot.channels) {
    state.meterMap.set(channelMeter.channel, channelMeter);
  }

  for (const channel of state.channels) {
    const meter = getAssignedMeter(channel);
    const bar = channelGrid.querySelector(`[data-channel-id="${channel.id}"] .meter-bar`);
    if (!bar) {
      continue;
    }
    const level = meter ? Math.min(meter.rms * 100, 100) : 0;
    bar.style.width = `${level}%`;
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

  await stopListening();

  const pc = new RTCPeerConnection();
  state.peerConnection = pc;

  pc.addTransceiver("audio", { direction: "recvonly" });
  pc.ontrack = (event) => {
    const [stream] = event.streams;
    audioElement.srcObject = stream ?? new MediaStream([event.track]);
  };
  pc.onconnectionstatechange = () => {
    statusText.textContent = pc.connectionState === "connected"
      ? "Streaming"
      : `Streaming (${pc.connectionState})`;
  };

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

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
  channelModal.classList.remove("is-hidden");
  channelModal.setAttribute("aria-hidden", "false");
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
  channelModal.classList.add("is-hidden");
  channelModal.setAttribute("aria-hidden", "true");
  state.modalChannelId = null;
  state.modalWaveform = null;
  state.modalScrubSeconds = 0;
  if (state.waveformRefreshTimer) {
    clearInterval(state.waveformRefreshTimer);
    state.waveformRefreshTimer = null;
  }
}

function updateModalContent() {
  if (!state.modalChannelId) {
    return;
  }
  const channel = getChannelById(state.modalChannelId);
  if (!channel) {
    return;
  }

  modalChannelNumber.textContent = `Channel ${channel.number}`;
  modalChannelName.textContent = channel.name;
  modalChannelMeta.textContent = channel.is_record_enabled
    ? "Rolling record enabled for this channel."
    : "Rolling record disabled for this channel.";
  modalPatchBadge.textContent = getInputLabel(channel);
  modalRecordBadge.textContent = channel.is_record_enabled ? "Recording on" : "Recording off";
  modalScrubLabel.textContent = state.modalScrubSeconds > 0
    ? `Scrubbed to ${state.modalScrubSeconds.toFixed(1)}s behind live`
    : "Click anywhere on the graph to scrub this channel in the past";
}

async function refreshModalWaveform() {
  if (!state.modalChannelId) {
    return;
  }

  const waveform = await fetchJson(
    `/api/channels/${state.modalChannelId}/waveform?seconds=300&points=280`,
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
  const barWidth = width / values.length;
  for (let index = 0; index < values.length; index += 1) {
    const value = values[index];
    const x = index * barWidth;
    const barHeight = Math.max(2, value * (height - 20));
    context.fillStyle = "rgba(56, 189, 248, 0.9)";
    context.fillRect(x, height - barHeight, Math.max(1, barWidth - 1), barHeight);
  }

  if (state.modalWaveform.seconds > 0) {
    const markerX = width * (1 - state.modalScrubSeconds / state.modalWaveform.seconds);
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
  const replaySeconds = Math.max(0, state.modalWaveform.seconds * (1 - ratio));
  state.modalScrubSeconds = replaySeconds;
  state.selectedChannelIds.clear();
  state.selectedChannelIds.add(state.modalChannelId);
  drawWaveform();
  updateModalContent();
  await syncListening(replaySeconds);
}

async function saveProgramRow(channelId) {
  const row = programTableBody.querySelector(`[data-channel-id="${channelId}"]`);
  if (!row) {
    return;
  }

  const existingChannel = getChannelById(channelId);

  const payload = {
    name:
      row.querySelector('[data-field="name"]').value.trim()
      || existingChannel?.name
      || `Channel ${channelId}`,
    input_index: row.querySelector('[data-field="input_index"]').value === ""
      ? null
      : Number(row.querySelector('[data-field="input_index"]').value),
    is_record_enabled: row.querySelector('[data-field="is_record_enabled"]').checked,
  };
  const statusCell = row.querySelector(`[data-save-status="${channelId}"]`);
  statusCell.textContent = "Saving…";

  const updatedChannel = await fetchJson(`/api/channels/${channelId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  state.channels = state.channels.map((channel) =>
    channel.id === channelId ? updatedChannel : channel,
  );
  statusCell.textContent = "Saved";
  renderAll();
  window.setTimeout(() => {
    statusCell.textContent = "";
  }, 1200);
}

async function reorderChannels(draggedChannelId, targetChannelId) {
  const ordered = sortChannels(state.channels);
  const draggedIndex = ordered.findIndex((channel) => channel.id === draggedChannelId);
  const targetIndex = ordered.findIndex((channel) => channel.id === targetChannelId);
  if (draggedIndex === -1 || targetIndex === -1) {
    return;
  }

  const [draggedChannel] = ordered.splice(draggedIndex, 1);
  ordered.splice(targetIndex, 0, draggedChannel);
  const changedChannels = [];
  const nextChannels = ordered.map((channel, index) => {
    if (channel.sort_index !== index) {
      changedChannels.push({ id: channel.id, sort_index: index });
    }
    return { ...channel, sort_index: index };
  });

  state.channels = nextChannels;
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
  layoutModeToggle.textContent = state.layoutMode ? "Done arranging" : "Arrange layout";
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
  stopListeningButton.addEventListener("click", async () => {
    state.selectedChannelIds.clear();
    await stopListening();
    renderAll();
  });
  listenModeToggle.addEventListener("click", toggleListenMode);
  layoutModeToggle.addEventListener("click", toggleLayoutMode);
  viewMonitorButton.addEventListener("click", () => setActiveView("monitor"));
  viewProgramButton.addEventListener("click", () => setActiveView("program"));
  closeModalButton.addEventListener("click", closeChannelModal);
  modalStopListeningButton.addEventListener("click", async () => {
    state.selectedChannelIds.clear();
    await stopListening();
    renderAll();
  });
  modalListenLiveButton.addEventListener("click", async () => {
    if (!state.modalChannelId) {
      return;
    }
    state.modalScrubSeconds = 0;
    state.selectedChannelIds.clear();
    state.selectedChannelIds.add(state.modalChannelId);
    updateModalContent();
    drawWaveform();
    await syncListening(0);
  });
  waveformCanvas.addEventListener("click", scrubModalWaveform);
  channelModal.addEventListener("click", (event) => {
    if (event.target.dataset.closeModal === "true") {
      closeChannelModal();
    }
  });
  window.addEventListener("resize", drawWaveform);

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
