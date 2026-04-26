# Mic-Wise

Mic-Wise is a browser-based monitoring tool for live sound and theatre radio microphone workflows.

The current repository is a Python backend plus a React + Vite + TypeScript frontend. It already includes live metering, browser listening, scene-aware show views, and setup tooling for channel programming and optional external cue sync.

## What is implemented today

- a shared-memory rolling audio buffer in `backend/app/audio/buffer.py`
- a separate audio engine process in `backend/app/audio/engine.py`
- synthetic multichannel audio for hardware-free development, plus `sounddevice` input support
- live RMS / peak meter analysis in `backend/app/audio/analysis.py`
- REST API routes, WebSocket meter updates, and WebRTC listening sessions from the FastAPI app
- a seeded SQLite show file storing settings, channels, and scenes
- a React browser UI built with Vite and served by the backend as static assets, with **Monitor**, **Show**, and **Setup** views
- waveform preview and scrub-back listening for the last five minutes
- optional Zeroconf discovery
- optional OSC / MIDI scene sync runtime in `backend/app/sync/service.py`

## Runtime architecture

Mic-Wise currently runs as one backend service with a clear internal split:

- `backend/app/audio/engine.py` runs as its own `multiprocessing.Process` and writes audio into the shared buffer.
- `backend/app/audio/buffer.py` exposes the shared `mmap` ring buffer used by the rest of the system.
- `backend/app/main.py` hosts the FastAPI application and starts the async runtime services.
- `backend/app/audio/analysis.py`, `backend/app/streaming/webrtc.py`, `backend/app/api/`, `backend/app/network/discovery.py`, and `backend/app/sync/service.py` run inside the FastAPI process.
- the frontend source lives under `frontend/` as a Vite app and the production build is served by FastAPI from `frontend/dist`

## Quick start

Create a virtual environment, install the backend dependencies, install the frontend dependencies, build the frontend, and start the server:

```text
python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r backend/requirements.txt
cd frontend && npm install && npm run build && cd ..
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

## Frontend development

During frontend development, use the repo-local helper to run the FastAPI backend on port `8000` and the Vite dev server on port `5173`:

```text
scripts/micwise-dev start
scripts/micwise-dev stop
scripts/micwise-dev restart
scripts/micwise-dev status
scripts/micwise-dev logs
```

Open the development UI at:

```text
http://127.0.0.1:5173/
```

The helper starts Uvicorn with reload enabled, so backend changes restart automatically. Vite hot-reloads frontend source changes.

You can also run the two services manually in separate terminals:

```text
cd frontend
npm install
npm run dev
```

The Vite dev server proxies `/api/*` and `/ws/*` traffic to the backend, so the browser still talks to a single origin during development.

For normal backend-served runs, FastAPI serves the production frontend build from `frontend/dist`, so rebuild with `npm run build` after frontend changes when you are not using the Vite dev server.

## Tests

Backend and frontend logic are covered by lightweight tests and validation scripts:

```text
pytest backend/tests
cd frontend && npm run test
cd frontend && npm run typecheck
cd frontend && npm run build
```

## Current scope

The current codebase already goes beyond a bare monitoring prototype. It includes:

- shared-buffer audio ingest and replay
- browser metering and WebRTC listening
- show-file backed channel and scene programming
- optional OSC / MIDI scene sync hooks

Future work can still deepen the system from here, but the code in this branch is already centered on a backend-served React UI with monitor, show, and setup workflows.
