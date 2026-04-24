# Mic-Wise

Mic-Wise is a browser-based monitoring tool for live sound and theatre radio microphone workflows.

The current repository is a single Python backend plus a static browser frontend. It already includes live metering, browser listening, scene-aware show views, and setup tooling for channel programming and optional external cue sync.

## What is implemented today

- a shared-memory rolling audio buffer in `backend/app/audio/buffer.py`
- a separate audio engine process in `backend/app/audio/engine.py`
- synthetic multichannel audio for hardware-free development, plus `sounddevice` input support
- live RMS / peak meter analysis in `backend/app/audio/analysis.py`
- REST API routes, WebSocket meter updates, and WebRTC listening sessions from the FastAPI app
- a seeded SQLite show file storing settings, channels, and scenes
- a static browser UI served directly by the backend with **Monitor**, **Show**, and **Setup** views
- waveform preview and scrub-back listening for the last five minutes
- optional Zeroconf discovery
- optional OSC / MIDI scene sync runtime in `backend/app/sync/service.py`

## Runtime architecture

Mic-Wise currently runs as one backend service with a clear internal split:

- `backend/app/audio/engine.py` runs as its own `multiprocessing.Process` and writes audio into the shared buffer.
- `backend/app/audio/buffer.py` exposes the shared `mmap` ring buffer used by the rest of the system.
- `backend/app/main.py` hosts the FastAPI application and starts the async runtime services.
- `backend/app/audio/analysis.py`, `backend/app/streaming/webrtc.py`, `backend/app/api/`, `backend/app/network/discovery.py`, and `backend/app/sync/service.py` run inside the FastAPI process.
- `frontend/index.html`, `frontend/styles.css`, `frontend/app.js`, and `frontend/ui_logic.mjs` are served directly by FastAPI without a frontend build step.

## Quick start

Create a virtual environment, install the backend dependencies, and start the server:

```text
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python backend/run.py
```

Then open the browser UI at:

```text
http://127.0.0.1:8000/
```

## Default runtime behaviour

On a clean first run, the current backend defaults are:

- audio source mode: `synthetic`
- sample rate: `48000`
- channel count: `16`
- rolling buffer duration: `300` seconds
- block size: `480` frames
- Zeroconf discovery: disabled
- show file: `backend/data/default.micwise`
- shared buffer file: a local runtime path under the system temp directory, namespaced by port

That last point is intentional: the SQLite show file lives under the persistent data directory, while the shared audio buffer lives under `runtime_directory` so the `mmap` file stays local and disposable.

## Browser UI modes

### Monitor

- shows the current channel grid and live meters
- supports single-listen and multi-listen
- keeps a persistent WebRTC audio transport with control updates for selection changes
- opens a docked channel inspector with waveform preview and scrub-back listening
- supports drag-reordering the channel layout

### Show

- filters the monitoring workflow through the active scene
- tracks a mic-check style checklist for scene members
- supports keyboard shortcuts for checking and unchecking channels

### Setup

- programs channel names, patching, trim, and rolling-record flags
- creates, reorders, and edits scenes
- maps scene cues to OSC and/or MIDI patterns
- configures optional external scene sync settings

## Configuration

`backend/app/core/settings.py` uses `pydantic-settings`, the `MICWISE_` prefix, and an optional repo-root `.env` file.

Current runtime settings include:

- `MICWISE_HOST`
- `MICWISE_PORT`
- `MICWISE_DATA_DIRECTORY`
- `MICWISE_RUNTIME_DIRECTORY`
- `MICWISE_SHOW_FILENAME`
- `MICWISE_BUFFER_FILENAME`
- `MICWISE_DEFAULT_SAMPLE_RATE`
- `MICWISE_DEFAULT_CHANNEL_COUNT`
- `MICWISE_DEFAULT_BUFFER_DURATION_SEC`
- `MICWISE_DEFAULT_BLOCK_SIZE`
- `MICWISE_AUDIO_SOURCE_MODE` (`synthetic` or `sounddevice`)
- `MICWISE_METER_WINDOW_MS`
- `MICWISE_METER_POLL_INTERVAL_MS`
- `MICWISE_ZEROCONF_ENABLED` (`true` / `false`)

## Tests

Backend and frontend helper logic are both covered by lightweight tests:

```text
pytest backend/tests
node --test frontend/tests/*.test.mjs
```

## Current scope

The current codebase already goes beyond a bare monitoring prototype. It includes:

- shared-buffer audio ingest and replay
- browser metering and WebRTC listening
- show-file backed channel and scene programming
- optional OSC / MIDI scene sync hooks

Future work can still deepen the system from here, but the code in this branch is already centered on a backend-served static UI with monitor, show, and setup workflows.
