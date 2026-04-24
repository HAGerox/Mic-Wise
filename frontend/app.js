import {
  buildExternalSyncStatusText,
  computeWaveformDisplayPoints,
  getSceneChecklistStats,
  getShowChannelVisualState,
  normaliseActiveView,
  resolveActiveSceneId,
} from "./ui_logic.mjs";

const MODAL_WAVEFORM_WINDOW_SECONDS = 300;
const MODAL_WAVEFORM_POINTS = 360;
const MODAL_WAVEFORM_REFRESH_MS = 900;
const MODAL_WAVEFORM_RENDER_MS = 33;
const PROGRAM_AUTOSAVE_DELAY_MS = 450;
const AUDIO_CONTROL_CHANNEL_LABEL = "micwise-control";
const LONG_PRESS_MS = 420;
const SYNC_STATUS_REFRESH_MS = 1500;

const state = {
  settings: null,
  channels: [],
  scenes: [],
  syncStatus: null,
  meterMap: new Map(),
  selectedChannelIds: new Set(),
  peerConnection: null,
  audioControlChannel: null,
  audioTransportPromise: null,
  pendingAudioCommand: null,
  listenRequestToken: 0,
  activeView: "monitor",
  setupTab: "program",
  multiListen: false,
  layoutMode: false,
  draggedChannelId: null,
  modalChannelId: null,
  modalWaveform: null,
  modalWaveformDisplayPoints: null,
  modalWaveformLastFetchedAt: 0,
  modalWaveformRenderTimer: null,
  modalWaveformRequestToken: 0,
  modalScrubSeconds: 0,
  waveformRefreshTimer: null,
  activeSceneId: null,
  sceneModeEnabled: false,
  sceneChecklistById: new Map(),
  sortable: null,
  sortableImportPromise: null,
  longPressTimer: null,
  longPressTriggered: false,
  syncStatusRefreshTimer: null,
};

const channelGrid = document.getElementById("channel-grid");
const programTableBody = document.getElementById("program-table-body");
const monitorView = document.getElementById("monitor-view");
const setupView = document.getElementById("setup-view");
const setupProgramPanel = document.getElementById("setup-program-panel");
const setupScenesPanel = document.getElementById("setup-scenes-panel");
const setupTabProgramButton = document.getElementById("setup-tab-program");
const setupTabScenesButton = document.getElementById("setup-tab-scenes");
const channelModalEmpty = document.getElementById("channel-modal-empty");
const monitorDock = document.querySelector(".monitor-dock");
const showSidebar = document.getElementById("show-sidebar");
const showList = document.getElementById("show-list");
const showSceneSummary = document.getElementById("show-scene-summary");
const showNextScene = document.getElementById("show-next-scene");
const showProgressPill = document.getElementById("show-progress-pill");
const showProgressText = document.getElementById("show-progress-text");
const showSceneStepper = document.getElementById("show-scene-stepper");
const statusText = document.getElementById("status-text");
const selectionCountText = document.getElementById("selection-count-text");
const audioElement = document.getElementById("monitor-audio");
const stopListeningButton = document.getElementById("stop-listening");
const listenModeToggle = document.getElementById("listen-mode-toggle");
const layoutModeToggle = document.getElementById("layout-mode-toggle");
const scenePrevButton = document.getElementById("scene-prev");
const sceneNextButton = document.getElementById("scene-next");
const viewMonitorButton = document.getElementById("view-monitor");
const viewShowButton = document.getElementById("view-show");
const viewSetupButton = document.getElementById("view-setup");
const addChannelButton = document.getElementById("add-channel");
const masterGainInput = document.getElementById("master-gain-input");
const channelModal = document.getElementById("channel-modal");
const closeModalButton = document.getElementById("close-modal");
const modalChannelNumber = document.getElementById("modal-channel-number");
const modalChannelName = document.getElementById("modal-channel-name");
const modalChannelMeta = document.getElementById("modal-channel-meta");
const modalTransportStatus = document.getElementById("modal-transport-status");
const modalPatchBadge = document.getElementById("modal-patch-badge");
const modalRecordBadge = document.getElementById("modal-record-badge");
const modalScrubLabel = document.getElementById("modal-scrub-label");
const waveformCanvas = document.getElementById("waveform-canvas");
const sceneStatusText = document.getElementById("scene-status-text");
const addSceneButton = document.getElementById("add-scene");
const sceneList = document.getElementById("scene-list");
const sceneEmptyState = document.getElementById("scene-empty-state");
const sceneDetail = document.getElementById("scene-detail");
const sceneNameInput = document.getElementById("scene-name-input");
const deleteSceneButton = document.getElementById("delete-scene");
const sceneDetailSummary = document.getElementById("scene-detail-summary");
const sceneTableBody = document.getElementById("scene-table-body");
const sceneSyncOscAddressInput = document.getElementById("scene-sync-osc-address");
const sceneSyncOscArgumentInput = document.getElementById("scene-sync-osc-argument");
const sceneSyncMidiPatternInput = document.getElementById("scene-sync-midi-pattern");
const externalSyncEnabledInput = document.getElementById("external-sync-enabled");
const externalSyncTransportSelect = document.getElementById("external-sync-transport");
const externalSyncOscHostInput = document.getElementById("external-sync-osc-host");
const externalSyncOscPortInput = document.getElementById("external-sync-osc-port");
const externalSyncMidiInputNameInput = document.getElementById("external-sync-midi-input-name");
const externalSyncStatus = document.getElementById("external-sync-status");

let layoutPlaceholder = null;
let layoutDragSourceCard = null;
let monitorViewportLayoutFrame = 0;

function formatPlaybackOffset(seconds) {
  const totalSeconds = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  return `${minutes}:${String(remainingSeconds).padStart(2, "0")}`;
}

function clampGainDb(value, min = -24, max = 24) {
  return Math.min(max, Math.max(min, Number.isFinite(value) ? value : 0));
}

function dbToLinearGain(gainDb) {
  return 10 ** (clampGainDb(gainDb) / 20);
}

function formatGainDb(gainDb) {
  const value = clampGainDb(Number(gainDb));
  return `${value > 0 ? "+" : ""}${value} dB`;
}

function getCombinedGainDb(channel) {
  return clampGainDb((channel?.gain_db ?? 0) + (state.settings?.master_gain_db ?? 0));
}

function getCombinedGainLinear(channel) {
  return dbToLinearGain(getCombinedGainDb(channel));
}

async function waitForIceGatheringComplete(peerConnection, timeoutMs = 250) {
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

function sortScenes(scenes) {
  return [...scenes].sort((left, right) => {
    if (left.order_index === right.order_index) {
      return left.id - right.id;
    }
    return left.order_index - right.order_index;
  });
}

function getOrderedScenes() {
  return sortScenes(state.scenes);
}

function getChannelById(channelId) {
  return state.channels.find((channel) => channel.id === channelId) ?? null;
}

function getSceneById(sceneId) {
  return state.scenes.find((scene) => scene.id === sceneId) ?? null;
}

function getActiveScene() {
  return state.activeSceneId === null ? null : getSceneById(state.activeSceneId);
}

function syncActiveSceneId(preferredSceneId = state.activeSceneId) {
  state.activeSceneId = resolveActiveSceneId(preferredSceneId, state.scenes);
}

function getActiveSceneIndex() {
  return getOrderedScenes().findIndex((scene) => scene.id === state.activeSceneId);
}

function getNextScene() {
  const orderedScenes = getOrderedScenes();
  const currentIndex = getActiveSceneIndex();
  if (currentIndex === -1) {
    return orderedScenes[0] ?? null;
  }
  return orderedScenes[currentIndex + 1] ?? null;
}

function getSceneAssignmentState(scene, channelId) {
  if (!scene) {
    return "off";
  }

  return scene.channel_assignments?.find((assignment) => assignment.channel_id === channelId)?.state ?? "off";
}

function getSceneChecklist(sceneId) {
  if (!state.sceneChecklistById.has(sceneId)) {
    state.sceneChecklistById.set(sceneId, new Set());
  }
  return state.sceneChecklistById.get(sceneId);
}

function getSceneSummary(scene) {
  const assignments = scene?.channel_assignments ?? [];
  const onstageCount = assignments.filter((assignment) => assignment.state === "onstage").length;
  const readyCount = assignments.filter((assignment) => assignment.state === "ready").length;
  return `${onstageCount} on stage • ${readyCount} about to enter`;
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

function isDefaultChannelName(channel) {
  return channel.name.trim().toLowerCase() === `channel ${channel.number}`.toLowerCase();
}

function getAvailableInputCount() {
  return Math.max(state.settings?.channel_count ?? 0, 0);
}

function isMonitorLikeView() {
  return state.activeView === "monitor" || state.activeView === "show";
}

function shouldShowDockedPanel() {
  return isMonitorLikeView() && state.modalChannelId !== null;
}

function isShowModeActive() {
  return state.activeView === "show";
}

function applyMonitorViewportLayout() {
  document.body.classList.toggle("monitor-view-active", isMonitorLikeView());

  if (!isMonitorLikeView() || !monitorDock) {
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

function reconcileChannelState() {
  const validIds = new Set(state.channels.map((channel) => channel.id));
  state.selectedChannelIds = new Set(
    [...state.selectedChannelIds].filter((channelId) => validIds.has(channelId)),
  );

  if (state.modalChannelId !== null && !validIds.has(state.modalChannelId)) {
    closeChannelModal();
  }
}

function updateStatusCard() {
  const activeScene = getActiveScene();
  const sceneChecklistStats = activeScene
    ? getSceneChecklistStats(activeScene, getSceneChecklist(activeScene.id))
    : { total: 0, checked: 0 };
  const sceneIndex = getActiveSceneIndex();
  const orderedScenes = getOrderedScenes();

  listenModeToggle.querySelector(".button-label").textContent = state.multiListen ? "Multi listen" : "Single listen";
  listenModeToggle.classList.toggle("is-active", state.multiListen);
  selectionCountText.textContent = `${state.selectedChannelIds.size} channel${state.selectedChannelIds.size === 1 ? "" : "s"}`;
  stopListeningButton.classList.toggle("is-armed", state.selectedChannelIds.size > 0);

  layoutModeToggle.querySelector(".button-label").textContent = state.layoutMode ? "Done arranging" : "Arrange";
  layoutModeToggle.classList.toggle("is-active", state.layoutMode);
  layoutModeToggle.disabled = isShowModeActive();
  layoutModeToggle.classList.toggle("is-hidden", state.activeView !== "monitor");

  sceneStatusText.textContent = activeScene ? activeScene.name : "No scenes";
  scenePrevButton.disabled = sceneIndex <= 0;
  sceneNextButton.disabled = sceneIndex === -1 || sceneIndex >= orderedScenes.length - 1;
  showSceneStepper.classList.toggle("is-hidden", !isShowModeActive());
  showProgressPill.classList.toggle("is-hidden", !isShowModeActive());
  showProgressText.textContent = `${sceneChecklistStats.checked}/${sceneChecklistStats.total} checked`;
}

function updateViewButtons() {
  viewMonitorButton.classList.toggle("is-active", state.activeView === "monitor");
  viewShowButton.classList.toggle("is-active", state.activeView === "show");
  viewSetupButton.classList.toggle("is-active", state.activeView === "setup");
  monitorView.classList.toggle("is-hidden", state.activeView === "setup");
  monitorView.classList.toggle("is-show-mode", state.activeView === "show");
  setupView.classList.toggle("is-hidden", state.activeView !== "setup");
  showSidebar.classList.toggle("is-hidden", state.activeView !== "show");
  setupProgramPanel.classList.toggle("is-hidden", state.setupTab !== "program");
  setupScenesPanel.classList.toggle("is-hidden", state.setupTab !== "scenes");
  setupTabProgramButton.classList.toggle("is-active", state.setupTab === "program");
  setupTabScenesButton.classList.toggle("is-active", state.setupTab === "scenes");
}

function updateDockedPanelState() {
  const showDockedPanel = shouldShowDockedPanel();
  channelModalEmpty.classList.toggle("is-hidden", showDockedPanel);
  channelModal.classList.toggle("is-hidden", !showDockedPanel);
  channelModal.setAttribute("aria-hidden", showDockedPanel ? "false" : "true");
  scheduleMonitorViewportLayout();
}

function getFocusedShowChannelId() {
  if (state.modalChannelId !== null) {
    return state.modalChannelId;
  }
  const [selectedChannelId] = orderedSelection();
  return selectedChannelId ?? null;
}

function getMonitorCardState(channel) {
  if (!isShowModeActive()) {
    return null;
  }

  return getShowChannelVisualState(
    getSceneAssignmentState(getActiveScene(), channel.id),
    getSceneChecklist(getActiveScene()?.id ?? -1).has(channel.id),
  );
}

function getCardBadgeMarkup(visualState) {
  if (!visualState) {
    return "";
  }
  if (visualState === "off") {
    return '<span class="tag tag--scene-muted">Out</span>';
  }
  if (visualState === "checked") {
    return '<span class="tag tag--scene-checked">Checked</span>';
  }
  return '<span class="tag tag--scene-pending">Pending</span>';
}

function renderMonitorGrid() {
  channelGrid.innerHTML = "";

  for (const channel of sortChannels(state.channels)) {
    const meter = getAssignedMeter(channel);
    const level = meter ? Math.min(meter.rms * getCombinedGainLinear(channel) * 100, 100) : 0;
    const repeatedName = isDefaultChannelName(channel);
    const visualState = getMonitorCardState(channel);
    const titleMarkup = repeatedName
      ? `<h2 class="channel-name">CH ${channel.number}</h2>`
      : `
        <div class="channel-number">CH ${channel.number}</div>
        <h2 class="channel-name">${escapeHtml(channel.name)}</h2>
      `;

    const card = document.createElement("article");
    card.className = "channel-card";
    card.dataset.channelId = String(channel.id);
    card.draggable = state.layoutMode && !state.sortable;
    card.classList.toggle("is-selected", state.selectedChannelIds.has(channel.id));
    card.classList.toggle("is-layout-mode", state.layoutMode);
    card.classList.toggle("is-show-off", visualState === "off");
    card.classList.toggle("is-show-pending", visualState === "pending");
    card.classList.toggle("is-show-checked", visualState === "checked");
    card.innerHTML = `
      <header>
        <div class="channel-title-group">
          ${titleMarkup}
        </div>
        <span class="channel-chip">${escapeHtml(getInputLabel(channel))}</span>
      </header>
      <div class="meter"><div class="meter-mask" style="width:${Math.max(0, 100 - level)}%"></div></div>
      <div class="channel-meta-row">
        <span class="channel-actions">${state.layoutMode ? "Hold and move" : "Tap to listen"}</span>
        ${getCardBadgeMarkup(visualState)}
      </div>
    `;

    card.addEventListener("click", async () => {
      if (state.layoutMode || state.draggedChannelId !== null || state.longPressTriggered) {
        state.longPressTriggered = false;
        return;
      }
      await handleChannelCardInteraction(channel.id);
    });

    card.addEventListener("pointerdown", () => {
      if (!isShowModeActive()) {
        return;
      }
      window.clearTimeout(state.longPressTimer);
      state.longPressTriggered = false;
      state.longPressTimer = window.setTimeout(() => {
        state.longPressTriggered = true;
        toggleSceneChecklist(channel.id);
      }, LONG_PRESS_MS);
    });

    const clearLongPress = () => {
      window.clearTimeout(state.longPressTimer);
      state.longPressTimer = null;
    };
    card.addEventListener("pointerup", clearLongPress);
    card.addEventListener("pointerleave", clearLongPress);
    card.addEventListener("pointercancel", clearLongPress);

    if (!state.sortable) {
      card.addEventListener("dragstart", (event) => {
        handleLayoutDragStart(event, channel.id);
      });
      card.addEventListener("dragend", () => {
        cleanupLayoutDrag();
      });
    }

    channelGrid.appendChild(card);
  }
}

function renderProgramTable() {
  programTableBody.innerHTML = "";
  const inputOptions = Array.from({ length: getAvailableInputCount() }, (_, index) => index);

  for (const channel of sortChannels(state.channels)) {
    const row = document.createElement("tr");
    row.dataset.channelId = String(channel.id);
    row.innerHTML = `
      <td>CH ${channel.number}</td>
      <td>
        <div class="program-name-field">
          <input type="text" data-field="name" value="${escapeHtml(channel.name)}" />
        </div>
      </td>
      <td>
        <select data-field="input_index">
          <option value="">Unpatched</option>
          ${inputOptions.map((index) => `
            <option value="${index}" ${channel.input_index === index ? "selected" : ""}>Input ${index + 1}</option>
          `).join("")}
        </select>
      </td>
      <td>
        <div class="gain-input-field">
          <input type="number" data-field="gain_db" min="-24" max="24" step="1" value="${clampGainDb(channel.gain_db ?? 0)}" />
          <span>dB</span>
        </div>
      </td>
      <td class="checkbox-cell">
        <label class="record-toggle" aria-label="Rolling record enabled">
          <input type="checkbox" data-field="is_record_enabled" ${channel.is_record_enabled ? "checked" : ""} />
          <span class="record-toggle-ui" aria-hidden="true"></span>
        </label>
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
    const gainInput = row.querySelector('[data-field="gain_db"]');
    const recordCheckbox = row.querySelector('[data-field="is_record_enabled"]');
    const removeButton = row.querySelector(`[data-remove-channel="${channelId}"]`);

    nameInput.addEventListener("input", () => scheduleProgramRowSave(channelId));
    nameInput.addEventListener("blur", () => {
      void saveProgramRow(channelId);
    });
    inputSelect.addEventListener("change", () => scheduleProgramRowSave(channelId, 0));
    gainInput.addEventListener("change", () => {
      gainInput.value = String(clampGainDb(Number(gainInput.value)));
      scheduleProgramRowSave(channelId, 0);
    });
    gainInput.addEventListener("blur", () => {
      gainInput.value = String(clampGainDb(Number(gainInput.value)));
      void saveProgramRow(channelId);
    });
    recordCheckbox.addEventListener("change", () => scheduleProgramRowSave(channelId, 0));
    removeButton.addEventListener("click", async () => {
      await removeChannel(channelId);
    });
  }
}

function renderShowList() {
  showList.innerHTML = "";

  const activeScene = getActiveScene();
  if (!activeScene) {
    showSceneSummary.textContent = "No active scene selected yet.";
    showNextScene.textContent = "Next: —";
    return;
  }

  const checklist = getSceneChecklist(activeScene.id);
  const nextScene = getNextScene();
  showSceneSummary.textContent = getSceneSummary(activeScene);
  showNextScene.textContent = nextScene ? `Next: ${nextScene.name}` : "Next: —";

  for (const channel of sortChannels(state.channels)) {
    const sceneState = getSceneAssignmentState(activeScene, channel.id);
    const visualState = getShowChannelVisualState(sceneState, checklist.has(channel.id));
    const item = document.createElement("button");
    item.type = "button";
    item.className = `show-list-item is-${visualState}`;
    item.disabled = sceneState === "off";
    item.innerHTML = `
      <span class="show-list-channel">CH ${channel.number}</span>
      <span class="show-list-name">${escapeHtml(channel.name)}</span>
      <span class="show-list-state">${sceneState === "off" ? "Not in scene" : (visualState === "checked" ? "Checked" : "Pending")}</span>
    `;
    item.addEventListener("click", () => {
      toggleSceneChecklist(channel.id);
    });
    showList.appendChild(item);
  }
}

function renderSceneList() {
  sceneList.innerHTML = "";
  for (const scene of getOrderedScenes()) {
    const item = document.createElement("button");
    item.type = "button";
    item.className = "scene-list-item";
    item.classList.toggle("is-active", scene.id === state.activeSceneId);
    item.innerHTML = `
      <strong>${escapeHtml(scene.name)}</strong>
      <span>${escapeHtml(getSceneSummary(scene))}</span>
    `;
    item.addEventListener("click", () => {
      void setActiveScene(scene.id);
    });
    sceneList.appendChild(item);
  }
}

function renderSceneTable() {
  const activeScene = getActiveScene();
  sceneTableBody.innerHTML = "";
  sceneEmptyState.classList.toggle("is-hidden", Boolean(activeScene));
  sceneDetail.classList.toggle("is-hidden", !activeScene);

  if (!activeScene) {
    return;
  }

  sceneNameInput.value = activeScene.name;
  sceneDetailSummary.textContent = getSceneSummary(activeScene);
  sceneSyncOscAddressInput.value = activeScene.sync_osc_address ?? "";
  sceneSyncOscArgumentInput.value = activeScene.sync_osc_argument ?? "";
  sceneSyncMidiPatternInput.value = activeScene.sync_midi_pattern ?? "";

  for (const channel of sortChannels(state.channels)) {
    const sceneState = getSceneAssignmentState(activeScene, channel.id);
    const row = document.createElement("tr");
    row.dataset.channelId = String(channel.id);
    row.className = `scene-row is-${sceneState}`;
    row.innerHTML = `
      <td>CH ${channel.number}</td>
      <td>${escapeHtml(channel.name)}</td>
      <td>
        <select class="scene-state-select" data-field="scene_state">
          <option value="off" ${sceneState === "off" ? "selected" : ""}>Greyed out</option>
          <option value="ready" ${sceneState === "ready" ? "selected" : ""}>About to enter</option>
          <option value="onstage" ${sceneState === "onstage" ? "selected" : ""}>On stage</option>
        </select>
      </td>
    `;
    sceneTableBody.appendChild(row);
  }

  for (const row of sceneTableBody.querySelectorAll("tr[data-channel-id]")) {
    row.querySelector('[data-field="scene_state"]')?.addEventListener("change", () => {
      void saveActiveSceneAssignments();
    });
  }
}

function renderSyncSettings() {
  if (!state.settings) {
    return;
  }

  externalSyncEnabledInput.checked = Boolean(state.settings.external_sync_enabled);
  externalSyncTransportSelect.value = state.settings.external_sync_transport ?? "off";
  externalSyncOscHostInput.value = state.settings.external_sync_osc_host ?? "0.0.0.0";
  externalSyncOscPortInput.value = String(state.settings.external_sync_osc_port ?? 53001);
  externalSyncMidiInputNameInput.value = state.settings.external_sync_midi_input_name ?? "";
  externalSyncStatus.textContent = buildExternalSyncStatusText(state.syncStatus);
}

function renderAll() {
  updateStatusCard();
  updateViewButtons();
  updateDockedPanelState();
  renderMonitorGrid();
  renderProgramTable();
  renderShowList();
  renderSceneList();
  renderSceneTable();
  renderSyncSettings();
  state.sortable?.option("disabled", !state.layoutMode || state.activeView !== "monitor");
  updateModalContent();
  if (state.settings && document.activeElement !== masterGainInput) {
    masterGainInput.value = String(clampGainDb(Number(state.settings.master_gain_db ?? 0)));
  }
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
    const level = meter ? Math.min(meter.rms * getCombinedGainLinear(channel) * 100, 100) : 0;
    mask.style.width = `${Math.max(0, 100 - level)}%`;
  }
}

function flushPendingAudioCommand() {
  if (!state.pendingAudioCommand || state.audioControlChannel?.readyState !== "open") {
    return;
  }
  state.audioControlChannel.send(JSON.stringify(state.pendingAudioCommand));
  state.pendingAudioCommand = null;
}

async function waitForDataChannelOpen(channel, timeoutMs = 900) {
  if (!channel || channel.readyState === "open") {
    return;
  }

  await new Promise((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      channel.removeEventListener("open", handleOpen);
      reject(new Error("Audio control channel timed out"));
    }, timeoutMs);

    function handleOpen() {
      window.clearTimeout(timeoutId);
      channel.removeEventListener("open", handleOpen);
      resolve();
    }

    channel.addEventListener("open", handleOpen, { once: true });
  });
}

async function closeAudioTransport({ preserveStatus = false } = {}) {
  const peerConnection = state.peerConnection;
  state.peerConnection = null;
  state.audioControlChannel = null;
  state.audioTransportPromise = null;
  state.pendingAudioCommand = null;

  if (peerConnection) {
    peerConnection.ontrack = null;
    peerConnection.onconnectionstatechange = null;
    peerConnection.getReceivers().forEach((receiver) => receiver.track?.stop());
    peerConnection.close();
  }

  audioElement.srcObject = null;
  if (!preserveStatus) {
    statusText.textContent = "Online";
  }
}

async function ensureAudioTransport() {
  if (state.peerConnection && state.audioControlChannel?.readyState === "open") {
    return state.peerConnection;
  }

  if (state.audioTransportPromise) {
    return state.audioTransportPromise;
  }

  const transportPromise = (async () => {
    const pc = new RTCPeerConnection({ iceServers: [] });
    const controlChannel = pc.createDataChannel(AUDIO_CONTROL_CHANNEL_LABEL, { ordered: true });

    state.peerConnection = pc;
    state.audioControlChannel = controlChannel;

    pc.addTransceiver("audio", { direction: "recvonly" });
    pc.ontrack = (event) => {
      if (pc !== state.peerConnection) {
        return;
      }
      const [stream] = event.streams;
      audioElement.srcObject = stream ?? new MediaStream([event.track]);
      if (state.selectedChannelIds.size > 0) {
        void audioElement.play().catch(() => {
          statusText.textContent = "Audio ready";
        });
      }
    };
    pc.onconnectionstatechange = () => {
      if (pc !== state.peerConnection) {
        return;
      }
      if (pc.connectionState === "failed" || pc.connectionState === "closed") {
        void closeAudioTransport({ preserveStatus: true });
        statusText.textContent = "Audio link unavailable";
        return;
      }
      if (pc.connectionState === "connected") {
        statusText.textContent = state.selectedChannelIds.size > 0 ? "Streaming" : "Online";
      }
    };

    controlChannel.addEventListener("open", flushPendingAudioCommand);

    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    await waitForIceGatheringComplete(pc, 180);

    const answer = await fetchJson("/api/streaming/webrtc/offer", {
      method: "POST",
      body: JSON.stringify({
        sdp: pc.localDescription.sdp,
        type: pc.localDescription.type,
        channel_ids: [],
        replay_seconds: 0,
      }),
    });

    await pc.setRemoteDescription(answer);
    await waitForDataChannelOpen(controlChannel);
    flushPendingAudioCommand();
    return pc;
  })();

  state.audioTransportPromise = transportPromise;

  try {
    return await transportPromise;
  } catch (error) {
    await closeAudioTransport({ preserveStatus: true });
    throw error;
  } finally {
    if (state.audioTransportPromise === transportPromise) {
      state.audioTransportPromise = null;
    }
  }
}

function buildSelectionInputSources(channelIds) {
  return channelIds
    .map((channelId) => getChannelById(channelId))
    .filter((channel) => channel && channel.input_index !== null && channel.input_index !== undefined)
    .map((channel) => [channel.input_index, getCombinedGainDb(channel)]);
}

async function sendAudioSelection(channelIds, replaySeconds = 0) {
  state.pendingAudioCommand = {
    input_sources: buildSelectionInputSources(channelIds),
    replay_seconds: replaySeconds,
  };

  if (!state.peerConnection && !state.audioTransportPromise && channelIds.length === 0) {
    return;
  }

  await ensureAudioTransport();
  await waitForDataChannelOpen(state.audioControlChannel);
  flushPendingAudioCommand();
}

async function handleStopAudioClick() {
  state.selectedChannelIds.clear();
  state.modalScrubSeconds = 0;
  await sendAudioSelection([], 0);
  renderAll();
  statusText.textContent = "Online";
}

function orderedSelection() {
  return sortChannels(state.channels)
    .map((channel) => channel.id)
    .filter((channelId) => state.selectedChannelIds.has(channelId));
}

async function startListening(channelIds, replaySeconds = 0) {
  if (channelIds.length === 0) {
    await sendAudioSelection([], 0);
    statusText.textContent = "Online";
    return;
  }

  const requestToken = ++state.listenRequestToken;
  statusText.textContent = replaySeconds > 0 ? "Cueing replay…" : "Cueing audio…";

  try {
    await sendAudioSelection(channelIds, replaySeconds);
    void audioElement.play().catch(() => {
      statusText.textContent = "Audio ready";
    });
    if (requestToken !== state.listenRequestToken) {
      return;
    }
    statusText.textContent = "Streaming";
  } catch (error) {
    if (requestToken !== state.listenRequestToken) {
      return;
    }
    statusText.textContent = "Audio connection failed";
    console.error(error);
  }
}

async function syncListening(replaySeconds = 0) {
  const selection = orderedSelection();
  if (selection.length === 0) {
    await sendAudioSelection([], 0);
    renderAll();
    statusText.textContent = "Online";
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
  statusText.textContent = state.selectedChannelIds.size > 0 ? "Cueing audio…" : "Online";
  void audioElement.play().catch(() => {});
  renderAll();
  await syncListening(0);
}

function openChannelModal(channelId) {
  state.modalChannelId = channelId;
  state.modalScrubSeconds = 0;
  updateDockedPanelState();
  updateModalContent();
  requestModalWaveformRefresh(channelId);

  if (state.waveformRefreshTimer) {
    window.clearInterval(state.waveformRefreshTimer);
  }
  if (state.modalWaveformRenderTimer) {
    window.clearInterval(state.modalWaveformRenderTimer);
  }

  state.waveformRefreshTimer = window.setInterval(() => {
    requestModalWaveformRefresh(state.modalChannelId);
  }, MODAL_WAVEFORM_REFRESH_MS);
  state.modalWaveformRenderTimer = window.setInterval(() => {
    updateModalWaveformDisplay();
  }, MODAL_WAVEFORM_RENDER_MS);
}

function closeChannelModal() {
  if (document.activeElement instanceof HTMLElement) {
    document.activeElement.blur();
  }

  state.modalWaveformRequestToken += 1;
  state.modalChannelId = null;
  state.modalWaveform = null;
  state.modalWaveformDisplayPoints = null;
  state.modalWaveformLastFetchedAt = 0;
  state.modalScrubSeconds = 0;
  if (state.waveformRefreshTimer) {
    window.clearInterval(state.waveformRefreshTimer);
    state.waveformRefreshTimer = null;
  }
  if (state.modalWaveformRenderTimer) {
    window.clearInterval(state.modalWaveformRenderTimer);
    state.modalWaveformRenderTimer = null;
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
  const repeatedName = isDefaultChannelName(channel);
  modalChannelNumber.textContent = repeatedName ? "" : `CH ${channel.number}`;
  modalChannelName.textContent = repeatedName ? `CH ${channel.number}` : channel.name;
  modalChannelMeta.textContent = `${getInputLabel(channel)} • ${channel.is_record_enabled ? "Rolling record on" : "Rolling record off"}`;
  modalTransportStatus.textContent = transportState.statusText;
  modalPatchBadge.textContent = getInputLabel(channel);
  modalRecordBadge.textContent = `${formatGainDb(getCombinedGainDb(channel))} trim`;
  modalScrubLabel.textContent = state.modalScrubSeconds > 0
    ? `${formatPlaybackOffset(state.modalScrubSeconds)} behind live`
    : "Click anywhere on the graph to scrub — click near Live to snap back";
  scheduleMonitorViewportLayout();
}

function updateModalWaveformDisplay() {
  if (!state.modalWaveform) {
    return;
  }

  const elapsedMs = Math.max(0, performance.now() - state.modalWaveformLastFetchedAt);
  state.modalWaveformDisplayPoints = computeWaveformDisplayPoints(
    state.modalWaveform.points,
    elapsedMs,
    MODAL_WAVEFORM_WINDOW_SECONDS,
    state.modalWaveform.points.at(-1) ?? 0,
  );
  drawWaveform();
}

function requestModalWaveformRefresh(channelId = state.modalChannelId) {
  if (channelId === null || channelId === undefined) {
    return;
  }

  state.modalWaveformRequestToken += 1;
  void refreshModalWaveform(channelId, state.modalWaveformRequestToken);
}

async function refreshModalWaveform(requestedChannelId = state.modalChannelId, requestToken = state.modalWaveformRequestToken) {
  if (requestedChannelId === null || requestedChannelId === undefined) {
    return;
  }

  try {
    const waveform = await fetchJson(
      `/api/channels/${requestedChannelId}/waveform?seconds=${MODAL_WAVEFORM_WINDOW_SECONDS}&points=${MODAL_WAVEFORM_POINTS}`,
    );
    if (state.modalChannelId !== requestedChannelId || requestToken !== state.modalWaveformRequestToken) {
      return;
    }
    state.modalWaveform = waveform;
    state.modalWaveformDisplayPoints = [...waveform.points];
    state.modalWaveformLastFetchedAt = performance.now();
    updateModalContent();
    drawWaveform();
  } catch (error) {
    console.error(error);
  }
}

function cancelProgramRowSave(channelId) {
  const timers = scheduleProgramRowSave.timers;
  if (!timers?.has(channelId)) {
    return;
  }

  window.clearTimeout(timers.get(channelId));
  timers.delete(channelId);
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

  const values = state.modalWaveformDisplayPoints ?? state.modalWaveform.points;
  const availableSeconds = Math.min(state.modalWaveform.seconds, MODAL_WAVEFORM_WINDOW_SECONDS);
  const occupiedWidth = width * (availableSeconds / MODAL_WAVEFORM_WINDOW_SECONDS);
  const startX = width - occupiedWidth;
  const baseline = height - 12;

  if (values.length > 0 && occupiedWidth > 0) {
    context.beginPath();
    context.moveTo(startX, baseline);
    for (let index = 0; index < values.length; index += 1) {
      const value = values[index];
      const x = startX + ((occupiedWidth * index) / Math.max(values.length - 1, 1));
      const y = baseline - Math.max(2, value * (height - 26));
      context.lineTo(x, y);
    }
    context.lineTo(startX + occupiedWidth, baseline);
    context.closePath();
    context.fillStyle = "rgba(56, 189, 248, 0.16)";
    context.fill();

    context.beginPath();
    for (let index = 0; index < values.length; index += 1) {
      const value = values[index];
      const x = startX + ((occupiedWidth * index) / Math.max(values.length - 1, 1));
      const y = baseline - Math.max(2, value * (height - 26));
      if (index === 0) {
        context.moveTo(x, y);
      } else {
        context.lineTo(x, y);
      }
    }
    context.strokeStyle = "rgba(56, 189, 248, 0.95)";
    context.lineWidth = 2;
    context.stroke();
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
  const snappedReplaySeconds = replaySeconds < 1.25 ? 0 : replaySeconds;
  state.modalScrubSeconds = snappedReplaySeconds;
  state.selectedChannelIds.clear();
  state.selectedChannelIds.add(state.modalChannelId);
  drawWaveform();
  updateModalContent();
  await syncListening(snappedReplaySeconds);
}

function scheduleProgramRowSave(channelId, delay = PROGRAM_AUTOSAVE_DELAY_MS) {
  if (!scheduleProgramRowSave.timers) {
    scheduleProgramRowSave.timers = new Map();
  }
  cancelProgramRowSave(channelId);
  const timer = window.setTimeout(() => {
    scheduleProgramRowSave.timers.delete(channelId);
    void saveProgramRow(channelId);
  }, delay);
  scheduleProgramRowSave.timers.set(channelId, timer);
}

function getProgramRowPayload(channelId) {
  const row = programTableBody.querySelector(`[data-channel-id="${channelId}"]`);
  if (!row) {
    return null;
  }

  const existingChannel = getChannelById(channelId);
  return {
    name: row.querySelector('[data-field="name"]').value.trim() || existingChannel?.name || `Channel ${channelId}`,
    input_index: row.querySelector('[data-field="input_index"]').value === ""
      ? null
      : Number(row.querySelector('[data-field="input_index"]').value),
    gain_db: clampGainDb(Number(row.querySelector('[data-field="gain_db"]').value)),
    is_record_enabled: row.querySelector('[data-field="is_record_enabled"]').checked,
  };
}

async function saveProgramRow(channelId) {
  cancelProgramRowSave(channelId);
  const payload = getProgramRowPayload(channelId);
  if (!payload) {
    return;
  }

  const updatedChannel = await fetchJson(`/api/channels/${channelId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
  state.channels = state.channels.map((channel) => (channel.id === channelId ? updatedChannel : channel));
  renderAll();
  if (state.modalChannelId === channelId) {
    requestModalWaveformRefresh(channelId);
  }
  if (state.selectedChannelIds.has(channelId)) {
    await syncListening(state.modalScrubSeconds);
  }
}

async function saveMasterGain() {
  const nextGainDb = clampGainDb(Number(masterGainInput.value));
  masterGainInput.value = String(nextGainDb);
  if (!state.settings) {
    return;
  }
  if (nextGainDb === clampGainDb(Number(state.settings.master_gain_db ?? 0))) {
    return;
  }

  state.settings = await fetchJson("/api/settings", {
    method: "PATCH",
    body: JSON.stringify({ master_gain_db: nextGainDb }),
  });
  renderAll();
  if (state.modalChannelId !== null) {
    requestModalWaveformRefresh(state.modalChannelId);
  }
  if (state.selectedChannelIds.size > 0) {
    await syncListening(state.modalScrubSeconds);
  }
}

async function refreshData() {
  const [channels, scenes, syncStatus] = await Promise.all([
    fetchJson("/api/channels"),
    fetchJson("/api/scenes"),
    fetchJson("/api/sync/status"),
  ]);
  state.channels = channels;
  state.scenes = scenes;
  state.syncStatus = syncStatus;
  syncActiveSceneId();
  reconcileChannelState();
  renderAll();
}

async function addChannel() {
  addChannelButton.disabled = true;
  try {
    await fetchJson("/api/channels", { method: "POST", body: JSON.stringify({}) });
    await refreshData();
  } finally {
    addChannelButton.disabled = false;
  }
}

async function removeChannel(channelId) {
  cancelProgramRowSave(channelId);
  await fetchJson(`/api/channels/${channelId}`, { method: "DELETE" });
  await refreshData();
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
    changedChannels.map((channel) => fetchJson(`/api/channels/${channel.id}`, {
      method: "PATCH",
      body: JSON.stringify({ sort_index: channel.sort_index }),
    })),
  );
}

async function loadSortableLibrary() {
  if (state.sortableImportPromise) {
    return state.sortableImportPromise;
  }

  state.sortableImportPromise = import("https://cdn.jsdelivr.net/npm/sortablejs@1.15.6/+esm")
    .then((module) => module.default ?? module.Sortable ?? null)
    .catch(() => null);

  return state.sortableImportPromise;
}

async function initialiseLayoutSorting() {
  if (state.sortable) {
    state.sortable.option("disabled", !state.layoutMode || state.activeView !== "monitor");
    return;
  }

  const Sortable = await loadSortableLibrary();
  if (!Sortable || state.sortable) {
    return;
  }

  state.sortable = Sortable.create(channelGrid, {
    animation: 180,
    easing: "cubic-bezier(0.22, 1, 0.36, 1)",
    draggable: ".channel-card",
    dataIdAttr: "data-channel-id",
    ghostClass: "channel-card--ghost",
    chosenClass: "channel-card--chosen",
    dragClass: "channel-card--dragging",
    fallbackClass: "channel-card--fallback",
    forceFallback: true,
    fallbackOnBody: true,
    fallbackTolerance: 4,
    swapThreshold: 0.72,
    invertedSwapThreshold: 0.78,
    touchStartThreshold: 4,
    disabled: !state.layoutMode || state.activeView !== "monitor",
    onStart: (event) => {
      state.draggedChannelId = Number(event.item.dataset.channelId);
      closeChannelModal();
    },
    onEnd: async () => {
      const orderedIds = state.sortable.toArray().map(Number);
      state.draggedChannelId = null;
      await persistChannelOrder(orderedIds);
    },
  });
}

function getDropReference(clientX, clientY) {
  if (state.sortable) {
    return null;
  }

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

  const referenceInRow = hoveredRow.cards.find(
    ({ rect }) => clientX < rect.left + Math.min(rect.width * 0.38, 72),
  );
  if (referenceInRow) {
    return referenceInRow.card;
  }

  const rowIndex = rows.indexOf(hoveredRow);
  const nextRow = rows[rowIndex + 1];
  return nextRow ? nextRow.cards[0].card : null;
}

function captureMonitorCardRects() {
  return new Map(
    [...channelGrid.querySelectorAll(".channel-card")]
      .filter((card) => card !== layoutDragSourceCard)
      .map((card) => [card.dataset.channelId || "__placeholder__", card.getBoundingClientRect()]),
  );
}

function animateMonitorCards(previousRects) {
  for (const card of [...channelGrid.querySelectorAll(".channel-card")].filter((item) => item !== layoutDragSourceCard)) {
    const key = card.dataset.channelId || "__placeholder__";
    const previousRect = previousRects.get(key);
    if (!previousRect) {
      continue;
    }

    const currentRect = card.getBoundingClientRect();
    const deltaX = previousRect.left - currentRect.left;
    const deltaY = previousRect.top - currentRect.top;
    if (Math.abs(deltaX) < 1 && Math.abs(deltaY) < 1) {
      continue;
    }

    card.animate(
      [
        { transform: `translate(${deltaX}px, ${deltaY}px)` },
        { transform: "translate(0, 0)" },
      ],
      {
        duration: 180,
        easing: "cubic-bezier(0.22, 1, 0.36, 1)",
      },
    );
  }
}

function handleLayoutDragStart(event, channelId) {
  if (state.sortable) {
    return;
  }

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
  if (state.sortable || !state.layoutMode || state.draggedChannelId === null || !layoutPlaceholder) {
    return;
  }

  event.preventDefault();
  const previousRects = captureMonitorCardRects();
  const previousParent = layoutPlaceholder.parentNode;
  const previousSibling = layoutPlaceholder.nextSibling;
  const referenceCard = getDropReference(event.clientX, event.clientY);
  if (referenceCard) {
    channelGrid.insertBefore(layoutPlaceholder, referenceCard);
  } else {
    channelGrid.appendChild(layoutPlaceholder);
  }

  if (previousParent !== layoutPlaceholder.parentNode || previousSibling !== layoutPlaceholder.nextSibling) {
    animateMonitorCards(previousRects);
  }
}

async function handleLayoutDrop(event) {
  if (state.sortable || !state.layoutMode || state.draggedChannelId === null || !layoutPlaceholder) {
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
  state.sceneModeEnabled = Boolean(state.settings.scene_mode_enabled);
  syncActiveSceneId(state.settings.active_scene_id ?? state.activeSceneId);
  state.activeView = normaliseActiveView(state.settings.active_mode);
  state.syncStatus = await fetchJson("/api/sync/status");
  renderAll();
}

async function setActiveView(view) {
  if (view !== "monitor" && view !== "show") {
    closeChannelModal();
  }
  if (view !== "monitor" && state.layoutMode) {
    state.layoutMode = false;
    cleanupLayoutDrag();
    state.sortable?.option("disabled", true);
  }

  state.activeView = view;
  renderAll();
  await patchSettings({
    active_mode: view === "setup" ? "setup" : view,
    scene_mode_enabled: view === "show",
  });
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
  if (state.activeView !== "monitor") {
    return;
  }
  state.layoutMode = !state.layoutMode;
  if (state.layoutMode) {
    closeChannelModal();
    void initialiseLayoutSorting();
  } else {
    cleanupLayoutDrag();
  }
  state.sortable?.option("disabled", !state.layoutMode || state.activeView !== "monitor");
  renderAll();
}

function setSetupTab(tab) {
  state.setupTab = tab;
  renderAll();
}

async function setActiveScene(sceneId) {
  if (sceneId === state.activeSceneId) {
    return;
  }
  state.activeSceneId = sceneId;
  renderAll();
  await patchSettings({ active_scene_id: sceneId });
}

async function navigateScene(offset) {
  const orderedScenes = getOrderedScenes();
  const currentIndex = getActiveSceneIndex();
  const nextIndex = currentIndex === -1 ? 0 : Math.max(0, Math.min(currentIndex + offset, orderedScenes.length - 1));
  const targetScene = orderedScenes[nextIndex];
  if (targetScene) {
    await setActiveScene(targetScene.id);
  }
}

function getActiveSceneAssignmentsPayload() {
  return [...sceneTableBody.querySelectorAll("tr[data-channel-id]")].map((row) => ({
    channel_id: Number(row.dataset.channelId),
    state: row.querySelector('[data-field="scene_state"]')?.value ?? "off",
  }));
}

async function saveActiveSceneAssignments() {
  const activeScene = getActiveScene();
  if (!activeScene) {
    return;
  }

  const updatedScene = await fetchJson(`/api/scenes/${activeScene.id}`, {
    method: "PATCH",
    body: JSON.stringify({ channel_assignments: getActiveSceneAssignmentsPayload() }),
  });
  state.scenes = state.scenes.map((scene) => (scene.id === activeScene.id ? updatedScene : scene));
  renderAll();
}

async function saveSceneCueMapping() {
  const activeScene = getActiveScene();
  if (!activeScene) {
    return;
  }

  const updatedScene = await fetchJson(`/api/scenes/${activeScene.id}`, {
    method: "PATCH",
    body: JSON.stringify({
      sync_osc_address: sceneSyncOscAddressInput.value.trim() || null,
      sync_osc_argument: sceneSyncOscArgumentInput.value.trim() || null,
      sync_midi_pattern: sceneSyncMidiPatternInput.value.trim() || null,
    }),
  });
  state.scenes = state.scenes.map((scene) => (scene.id === activeScene.id ? updatedScene : scene));
  renderAll();
}

async function saveActiveSceneName() {
  const activeScene = getActiveScene();
  if (!activeScene) {
    return;
  }

  const nextName = sceneNameInput.value.trim() || activeScene.name;
  if (nextName === activeScene.name) {
    sceneNameInput.value = activeScene.name;
    return;
  }

  const updatedScene = await fetchJson(`/api/scenes/${activeScene.id}`, {
    method: "PATCH",
    body: JSON.stringify({ name: nextName }),
  });
  state.scenes = state.scenes.map((scene) => (scene.id === activeScene.id ? updatedScene : scene));
  renderAll();
}

async function addScene() {
  addSceneButton.disabled = true;
  try {
    const createdScene = await fetchJson("/api/scenes", { method: "POST", body: JSON.stringify({}) });
    await refreshData();
    await setActiveScene(createdScene.id);
    await setActiveView("setup");
    setSetupTab("scenes");
  } finally {
    addSceneButton.disabled = false;
  }
}

async function deleteActiveScene() {
  const activeScene = getActiveScene();
  if (!activeScene) {
    return;
  }

  deleteSceneButton.disabled = true;
  try {
    await fetchJson(`/api/scenes/${activeScene.id}`, { method: "DELETE" });
    await refreshData();
    await patchSettings({ active_scene_id: state.activeSceneId });
  } finally {
    deleteSceneButton.disabled = false;
  }
}

function toggleSceneChecklist(channelId, desiredState = null) {
  const activeScene = getActiveScene();
  if (!activeScene) {
    return;
  }

  const sceneState = getSceneAssignmentState(activeScene, channelId);
  if (sceneState === "off") {
    return;
  }

  const checklist = getSceneChecklist(activeScene.id);
  const shouldCheck = desiredState === null ? !checklist.has(channelId) : desiredState;
  if (shouldCheck) {
    checklist.add(channelId);
  } else {
    checklist.delete(channelId);
  }
  renderAll();
}

async function saveExternalSyncSettings() {
  state.settings = await fetchJson("/api/settings", {
    method: "PATCH",
    body: JSON.stringify({
      external_sync_enabled: externalSyncEnabledInput.checked,
      external_sync_transport: externalSyncTransportSelect.value,
      external_sync_osc_host: externalSyncOscHostInput.value.trim() || "0.0.0.0",
      external_sync_osc_port: Number(externalSyncOscPortInput.value || 53001),
      external_sync_midi_input_name: externalSyncMidiInputNameInput.value.trim() || null,
    }),
  });
  state.syncStatus = await fetchJson("/api/sync/status");
  renderAll();
}

async function refreshSyncStatus() {
  try {
    const previousStatus = state.syncStatus;
    const nextStatus = await fetchJson("/api/sync/status");
    state.syncStatus = nextStatus;

    if (nextStatus.last_matched_scene_id !== null && nextStatus.last_matched_scene_id !== state.activeSceneId) {
      syncActiveSceneId(nextStatus.last_matched_scene_id);
      renderAll();
      return;
    }

    if (buildExternalSyncStatusText(previousStatus) !== buildExternalSyncStatusText(nextStatus)) {
      externalSyncStatus.textContent = buildExternalSyncStatusText(nextStatus);
    }
  } catch (error) {
    console.warn("Sync status refresh failed", error);
  }
}

function connectMeterSocket() {
  const protocol = window.location.protocol === "https:" ? "wss" : "ws";
  const meterSocket = new WebSocket(`${protocol}://${window.location.host}/ws/meters`);
  meterSocket.onmessage = (event) => updateMeters(JSON.parse(event.data));
  meterSocket.onopen = () => {
    if (state.selectedChannelIds.size === 0) {
      statusText.textContent = "Online";
    }
  };
  meterSocket.onerror = () => {
    statusText.textContent = "Meter socket error";
  };
}

function handleGlobalKeydown(event) {
  const target = event.target;
  if (
    target instanceof HTMLElement
    && (
      target.isContentEditable
      || target.tagName === "INPUT"
      || target.tagName === "TEXTAREA"
      || target.tagName === "SELECT"
    )
  ) {
    return;
  }

  if (!isShowModeActive()) {
    return;
  }

  const focusedChannelId = getFocusedShowChannelId();
  if (focusedChannelId === null) {
    return;
  }

  if (event.key.toLowerCase() === "y") {
    event.preventDefault();
    toggleSceneChecklist(focusedChannelId, true);
  }
  if (event.key.toLowerCase() === "n") {
    event.preventDefault();
    toggleSceneChecklist(focusedChannelId, false);
  }
}

async function bootstrap() {
  stopListeningButton.addEventListener("click", () => {
    void handleStopAudioClick();
  });
  listenModeToggle.addEventListener("click", () => {
    void toggleListenMode();
  });
  layoutModeToggle.addEventListener("click", toggleLayoutMode);
  scenePrevButton.addEventListener("click", () => {
    void navigateScene(-1);
  });
  sceneNextButton.addEventListener("click", () => {
    void navigateScene(1);
  });
  viewMonitorButton.addEventListener("click", () => {
    void setActiveView("monitor");
  });
  viewShowButton.addEventListener("click", () => {
    void setActiveView("show");
  });
  viewSetupButton.addEventListener("click", () => {
    void setActiveView("setup");
  });
  setupTabProgramButton.addEventListener("click", () => setSetupTab("program"));
  setupTabScenesButton.addEventListener("click", () => setSetupTab("scenes"));
  addChannelButton.addEventListener("click", () => {
    void addChannel();
  });
  addSceneButton.addEventListener("click", () => {
    void addScene();
  });
  masterGainInput.addEventListener("change", () => {
    void saveMasterGain();
  });
  masterGainInput.addEventListener("blur", () => {
    void saveMasterGain();
  });
  sceneNameInput.addEventListener("change", () => {
    void saveActiveSceneName();
  });
  sceneNameInput.addEventListener("blur", () => {
    void saveActiveSceneName();
  });
  deleteSceneButton.addEventListener("click", () => {
    void deleteActiveScene();
  });
  sceneSyncOscAddressInput.addEventListener("change", () => {
    void saveSceneCueMapping();
  });
  sceneSyncOscArgumentInput.addEventListener("change", () => {
    void saveSceneCueMapping();
  });
  sceneSyncMidiPatternInput.addEventListener("change", () => {
    void saveSceneCueMapping();
  });
  externalSyncEnabledInput.addEventListener("change", () => {
    void saveExternalSyncSettings();
  });
  externalSyncTransportSelect.addEventListener("change", () => {
    void saveExternalSyncSettings();
  });
  externalSyncOscHostInput.addEventListener("change", () => {
    void saveExternalSyncSettings();
  });
  externalSyncOscPortInput.addEventListener("change", () => {
    void saveExternalSyncSettings();
  });
  externalSyncMidiInputNameInput.addEventListener("change", () => {
    void saveExternalSyncSettings();
  });
  closeModalButton.addEventListener("click", closeChannelModal);
  waveformCanvas.addEventListener("click", (event) => {
    void scrubModalWaveform(event);
  });
  channelGrid.addEventListener("dragover", handleLayoutDragOver);
  channelGrid.addEventListener("drop", (event) => {
    void handleLayoutDrop(event);
  });
  window.addEventListener("resize", () => {
    drawWaveform();
    scheduleMonitorViewportLayout();
  });
  window.addEventListener("keydown", handleGlobalKeydown);

  const [health, settings, channels, scenes, latestMeters, syncStatus] = await Promise.all([
    fetchJson("/api/health"),
    fetchJson("/api/settings"),
    fetchJson("/api/channels"),
    fetchJson("/api/scenes"),
    fetchJson("/api/meters/latest"),
    fetchJson("/api/sync/status"),
  ]);

  statusText.textContent = health.audio_engine_running ? "Online" : "Starting";
  state.settings = settings;
  state.channels = channels;
  state.scenes = scenes;
  state.syncStatus = syncStatus;
  state.multiListen = settings.multi_listen_enabled;
  state.sceneModeEnabled = Boolean(settings.scene_mode_enabled);
  syncActiveSceneId(settings.active_scene_id);
  state.activeView = normaliseActiveView(settings.active_mode);
  for (const channelMeter of latestMeters.channels) {
    state.meterMap.set(channelMeter.channel, channelMeter);
  }

  renderAll();
  connectMeterSocket();
  void initialiseLayoutSorting();
  void ensureAudioTransport().catch((error) => {
    console.warn("Audio prewarm failed", error);
  });

  state.syncStatusRefreshTimer = window.setInterval(() => {
    void refreshSyncStatus();
  }, SYNC_STATUS_REFRESH_MS);
}

bootstrap().catch((error) => {
  console.error(error);
  statusText.textContent = "Startup failed";
});
