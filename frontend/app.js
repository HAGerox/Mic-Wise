const state = {
  channels: [],
  meterMap: new Map(),
  selectedChannels: new Set(),
  peerConnection: null,
};

const channelGrid = document.getElementById("channel-grid");
const statusText = document.getElementById("status-text");
const writeHeadText = document.getElementById("write-head");
const modeText = document.getElementById("mode-text");
const replaySlider = document.getElementById("replay-seconds");
const replayLabel = document.getElementById("replay-label");
const audioElement = document.getElementById("monitor-audio");
const listenSelectedButton = document.getElementById("listen-selected");
const stopListeningButton = document.getElementById("stop-listening");

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

function updateReplayLabel() {
  const seconds = Number(replaySlider.value);
  replayLabel.textContent = seconds === 0 ? "0s (live)" : `${seconds}s behind live`;
}

function renderChannels() {
  channelGrid.innerHTML = "";
  for (const channel of state.channels) {
    const card = document.createElement("article");
    card.className = "channel-card";
    card.dataset.channel = String(channel.number);
    card.innerHTML = `
      <header>
        <div>
          <div class="channel-number">CH ${channel.number}</div>
          <h2 class="channel-name">${channel.name}</h2>
        </div>
        <label>
          <input type="checkbox" data-select-channel="${channel.number}" />
          Select
        </label>
      </header>
      <div>
        <div class="meter"><div class="meter-bar" id="meter-${channel.number}"></div></div>
      </div>
      <div class="channel-actions">
        <button data-listen-channel="${channel.number}">Listen</button>
        <span data-meter-label="${channel.number}">RMS 0.000</span>
      </div>
    `;
    channelGrid.appendChild(card);
  }

  for (const checkbox of document.querySelectorAll("[data-select-channel]")) {
    checkbox.addEventListener("change", (event) => {
      const channelNumber = Number(event.target.dataset.selectChannel);
      if (event.target.checked) {
        state.selectedChannels.add(channelNumber);
      } else {
        state.selectedChannels.delete(channelNumber);
      }
    });
  }

  for (const button of document.querySelectorAll("[data-listen-channel]")) {
    button.addEventListener("click", async (event) => {
      const channelNumber = Number(event.target.dataset.listenChannel);
      state.selectedChannels.clear();
      state.selectedChannels.add(channelNumber);
      syncCheckboxes();
      await startListening([channelNumber]);
    });
  }
}

function syncCheckboxes() {
  for (const checkbox of document.querySelectorAll("[data-select-channel]")) {
    const channelNumber = Number(checkbox.dataset.selectChannel);
    checkbox.checked = state.selectedChannels.has(channelNumber);
  }
}

function updateMeters(snapshot) {
  writeHeadText.textContent = String(snapshot.write_head);
  for (const channelMeter of snapshot.channels) {
    state.meterMap.set(channelMeter.channel, channelMeter);
    const bar = document.getElementById(`meter-${channelMeter.channel}`);
    const label = document.querySelector(`[data-meter-label="${channelMeter.channel}"]`);
    if (!bar || !label) continue;

    const level = Math.min(channelMeter.rms * 100, 100);
    bar.style.width = `${level}%`;
    label.textContent = `RMS ${channelMeter.rms.toFixed(3)} · Peak ${channelMeter.peak.toFixed(3)}`;
  }
}

async function stopListening() {
  if (state.peerConnection) {
    state.peerConnection.getReceivers().forEach((receiver) => receiver.track?.stop());
    await state.peerConnection.close();
    state.peerConnection = null;
  }
  audioElement.srcObject = null;
}

async function startListening(channelNumbers) {
  await stopListening();

  const pc = new RTCPeerConnection();
  state.peerConnection = pc;

  pc.addTransceiver("audio", { direction: "recvonly" });
  pc.ontrack = (event) => {
    const [stream] = event.streams;
    audioElement.srcObject = stream ?? new MediaStream([event.track]);
  };
  pc.onconnectionstatechange = () => {
    statusText.textContent = `Streaming (${pc.connectionState})`;
  };

  const offer = await pc.createOffer();
  await pc.setLocalDescription(offer);

  const answer = await fetchJson("/api/streaming/webrtc/offer", {
    method: "POST",
    body: JSON.stringify({
      sdp: pc.localDescription.sdp,
      type: pc.localDescription.type,
      channel_numbers: channelNumbers,
      replay_seconds: Number(replaySlider.value),
    }),
  });

  await pc.setRemoteDescription(answer);
}

async function bootstrap() {
  updateReplayLabel();
  replaySlider.addEventListener("input", updateReplayLabel);
  listenSelectedButton.addEventListener("click", async () => {
    const selection = [...state.selectedChannels].sort((a, b) => a - b);
    if (selection.length === 0) {
      return;
    }
    await startListening(selection);
  });
  stopListeningButton.addEventListener("click", stopListening);

  const [health, settings, channels, latestMeters] = await Promise.all([
    fetchJson("/api/health"),
    fetchJson("/api/settings"),
    fetchJson("/api/channels"),
    fetchJson("/api/meters/latest"),
  ]);

  statusText.textContent = health.audio_engine_running ? "Online" : "Starting";
  modeText.textContent = settings.active_mode;
  state.channels = channels;
  renderChannels();
  updateMeters(latestMeters);

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

bootstrap().catch((error) => {
  console.error(error);
  statusText.textContent = "Startup failed";
});
