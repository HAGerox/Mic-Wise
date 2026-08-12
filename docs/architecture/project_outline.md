# Mic-Wise: Project Outline & Architecture

## 1. Project Overview

**Mic-Wise** is a browser-based monitoring tool for live sound and theatre radio microphone workflows. The current repository ships a FastAPI backend plus a React + Vite + TypeScript frontend, with live metering, browser listening, scene-aware workflows, and show/setup tooling.

### Current design goals

- **Isolate audio capture from the web stack** so UI activity does not disturb audio ingestion.
- **Use one shared audio boundary** via the memory-mapped ring buffer in `backend/app/audio/buffer.py`.
- **Keep production deployment simple** by serving a built frontend from the backend.
- **Preserve operator workflows** for monitoring, show operation, and setup/programming.

## 2. What changed recently

The frontend architecture has changed substantially from the original prototype.

- The old browser UI was a vanilla JavaScript frontend centered around `frontend/app.js` and `frontend/ui_logic.mjs`.
- The current UI now lives in `frontend/src/` as a Vite-powered React + TypeScript application.
- FastAPI still serves the production frontend, but it now serves the Vite build output from `frontend/dist`.

That means any architecture notes that talk about the frontend as a single static JS file are historical, not current.

## 3. Implemented feature set

### Audio ingestion and buffering

- shared-memory rolling audio buffer implemented with `mmap`
- separate audio engine process in `backend/app/audio/engine.py`
- deterministic synthetic audio mode for hardware-free development
- optional `sounddevice` audio input path
- five-minute rolling replay window by default

### Monitoring and playback

- live RMS / peak metering delivered to browsers over WebSocket
- WebRTC browser listening with live and scrub-back playback
- single-listen and multi-listen workflows
- waveform preview for recent audio history

### Show and setup workflows

- **Monitor** view for channel grid monitoring and listening
- **Show** view for scene-focused workflows and checklist tracking
- **Setup** view for channel programming, scene editing, cue mapping, and sync settings

### Persistence and integrations

- SQLite show file for settings, channels, and scenes
- optional Zeroconf service discovery
- optional OSC / MIDI scene sync runtime via `backend/app/sync/service.py`
- optional RChat UDP alert delivery via `backend/app/network/rchat.py`

## 4. Runtime architecture

Mic-Wise currently runs as one backend service with a clear internal runtime split.

### A. Shared audio buffer

- **Module:** `backend/app/audio/buffer.py`
- **Role:** The integration boundary between the audio writer and backend async services.
- **Format:** interleaved `int16` PCM audio with a monotonic `write_head` and wraparound-safe reads.

### B. Audio engine process

- **Module:** `backend/app/audio/engine.py`
- **Role:** Runs in its own `multiprocessing.Process`.
- **Responsibilities:** acquire audio frames from the configured source and write them into the shared buffer with minimal overhead.

### C. FastAPI application process

- **Entry point:** `backend/app/main.py`
- **Responsibilities:**
  - create runtime state and shared services
  - initialise the show database
  - start the audio engine process
  - start the meter analysis service
  - host REST and WebSocket APIs
  - host the WebRTC stream manager
  - optionally start Zeroconf discovery and scene sync services
  - send optional alert notifications to RChat over local UDP broadcast

### D. Database layer

- **Modules:** `backend/app/database/models.py`, `repository.py`, `session.py`
- **Role:** persist show settings, channels, scenes, and scene ordering in SQLite via async SQLAlchemy.

### E. Frontend application

- **Source root:** `frontend/src/`
- **Build tool:** Vite
- **UI runtime:** React + TypeScript
- **Production hosting:** built to `frontend/dist` and served by FastAPI

## 5. Frontend architecture

The frontend is no longer a single-file DOM script. It is split by responsibility:

### Application shell

- `frontend/src/App.tsx` orchestrates the overall application
- `frontend/src/main.tsx` boots the React app
- `frontend/index.html` is the Vite entry shell

### Server-facing modules

- `frontend/src/api/` contains typed wrappers for REST endpoints and WebRTC offer flow
- TanStack Query is used for REST-backed server state such as channels, scenes, settings, sync status, and waveform requests

### Transport hooks

- `frontend/src/hooks/useMeters.ts` manages the `/ws/meters` feed
- `frontend/src/hooks/useAudioTransport.ts` manages the persistent WebRTC transport and control data channel
- `frontend/src/hooks/useWaveform.ts` manages waveform polling and interpolation state

### Local UI state

- `frontend/src/state/appStateReducer.ts` owns reducer-based UI state transitions
- `frontend/src/state/AppStateContext.tsx` provides that state to the component tree

### Pure UI logic and rendering helpers

- `frontend/src/lib/ui-logic.ts` contains pure helper logic ported from the old frontend
- `frontend/src/lib/format.ts` contains formatting helpers
- `frontend/styles.css` remains the shared stylesheet for the current UI

### Component structure

Key components currently include:

- `Toolbar.tsx`
- `ChannelGrid.tsx`
- `ChannelCard.tsx`
- `ChannelModal.tsx`
- `WaveformCanvas.tsx`
- `ShowSidebar.tsx`
- `SetupView.tsx`

## 6. End-to-end data flow

### Live metering

1. The audio engine writes audio into `AudioBuffer`.
2. `MeterAnalysisService` reads recent audio windows from the buffer.
3. Meter snapshots are pushed to browsers over `/ws/meters`.
4. The React frontend updates channel cards and show views from that live stream.

### Browser listening

1. The browser requests a WebRTC offer via the backend.
2. `backend/app/streaming/webrtc.py` creates the stream and control channel.
3. The frontend keeps the peer connection alive and sends selection/playback updates over the `micwise-control` data channel.
4. The backend reads the requested channels and playback position from the shared buffer.

### Show editing and scene sync

1. The frontend updates channels, scenes, and settings through REST endpoints.
2. The repository layer persists those changes to the SQLite show file.
3. Optional OSC / MIDI cue matching updates sync state inside the backend.
4. The frontend surfaces the current sync status in the setup workflow.

## 7. Development workflow

### Backend-served production flow

- build the frontend with `cd frontend && npm run build`
- run the backend with `python backend/run.py`
- FastAPI serves the built frontend from `frontend/dist`

### Frontend development flow

- run the backend on port `8000`
- run `npm run dev` inside `frontend/`
- Vite proxies `/api/*` and `/ws/*` to the backend during development

## 8. Tests and validation

### Backend

- `pytest backend/tests`

### Frontend

- `cd frontend && npm run test`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run build`

Frontend tests currently live alongside the source modules, for example:

- `frontend/src/lib/ui-logic.test.ts`
- `frontend/src/state/appStateReducer.test.ts`

## 9. Future directions

The repository still has room to grow, but these are future ideas rather than implemented features:

- richer browser component tests for high-risk workflows
- deeper scene/show collaboration features
- additional operator UX polish and styling refactors
- more advanced audio analysis beyond the current metering path
