# Mic-Wise: Project Outline & Architecture

## 1. Project Overview
**Mic-Wise** is a professional audio monitoring application designed for live sound and theatre environments. It allows operators to monitor a large number of radio microphones (16-64 channels) remotely via a web interface.

### Core Philosophy
- **Headless Backend:** The audio engine runs on a dedicated machine connected to the audio hardware (Dante, MADI, etc.).
- **Networked Frontend:** The user interface is a web application accessible from any device (laptop, tablet) on the local network.
- **Resilience:** The audio recording and monitoring must be rock-solid, decoupled from the UI performance.

## 2. Functional Requirements

### Audio Ingestion
- **Input:** Support for 16 to 64 channels of live audio.
- **Drivers:** Cross-platform support via PortAudio (`sounddevice`):
  - macOS: CoreAudio
  - Windows: ASIO (via `SD_ENABLE_ASIO`), WDM
  - Linux: ALSA, Jack
- **Format:** 16-bit PCM (to optimize memory usage).

### Recording & Buffering
- **Rolling Buffer:** Continuous 5-minute loop recording for every channel.
- **Storage:** High-performance memory-mapped ring buffer (RAM/Disk hybrid).
- **Configuration:** "Show Files" (SQLite databases) store channel counts and sample rates.

### Monitoring & Playback
- **Live Listen:** Low-latency streaming of selected channels to the web client.
- **Instant Replay:** Ability to "scrub" back up to 5 minutes in time to verify audio artifacts.
- **Solo/Multi-Listen:** Toggle between listening to a single channel or a mix of selected channels.

### Analysis & Visualization
- **Metering:** Real-time RMS energy metering for all channels on the frontend.
- **Artifact Detection:** Machine Learning (ML) analysis to detect "pops", clicks, or dropouts.
- **Timeline:** Visual representation of audio energy and detected events on the replay timeline.

### User Interface Modes
1.  **Monitor Mode:**
    - Grid view of all channels.
    - Drag-and-drop arrangement (synced across all clients).
    - Channel metadata: Name, Photo, Input Patch.
2.  **Scene-by-Scene Mode:**
    - Theatre-specific workflow.
    - Filters view to show only characters in the current or next scene.
    - Visual distinction for "On Stage" vs "Standby" vs "Off".

### System
- **Discovery:** Zero-configuration networking (mDNS/Zeroconf) so frontends automatically find the backend.
- **Cross-Platform:** Compatible with macOS, Windows, and Linux.

## 3. High-Level Architecture

The system uses a **Split-Process Architecture** to bypass Python's Global Interpreter Lock (GIL) and ensure audio stability.

### A. The Data Layer (Shared Memory)
- **Technology:** `mmap` (Memory Mapped File).
- **Structure:** Interleaved Ring Buffer.
- **Role:** Acts as the central "source of truth" for audio data. The Audio Engine writes to it; the Streamer and Analyzer read from it. Zero-copy access ensures high performance.

### B. Process 1: Audio Engine (Critical Priority)
- **Library:** `sounddevice`.
- **Responsibility:**
  - Connects to audio hardware.
  - Reads raw audio frames.
  - Writes frames to the Shared Ring Buffer.
  - *Does nothing else to ensure zero dropouts.*

### C. Process 2: Analysis Worker
- **Responsibility:**
  - Reads the "head" of the Ring Buffer periodically.
  - Calculates RMS levels for UI meters.
  - Runs ML inference for artifact detection.
  - Writes events to the Database and pushes meter data to Redis/Queue (or directly to WebSocket process).

### D. Process 3: Web & Streaming Server
- **Library:** `FastAPI` + `aiortc` (WebRTC).
- **Responsibility:**
  - **API:** Serves the React frontend and handles REST/WebSocket requests.
  - **Streaming:** Establishes WebRTC connections to stream audio to clients.
  - **Discovery:** Broadcasts service via `zeroconf`.
  - **State Management:** Manages the SQLite "Show File" (Channels, Scenes, Settings).

### E. Frontend
- **Technology:** React (Vite).
- **Responsibility:**
  - Renders the UI (Meters, Grid, Timeline).
  - Connects via WebSocket for control/meters.
  - Connects via WebRTC for audio playback.

## 4. Implementation Plan

### Phase 1: Core Audio Infrastructure
1.  **Project Skeleton:** Setup directory structure and dependencies.
2.  **Buffer Logic:** Implement the `mmap` ring buffer class (`buffer.py`).
3.  **Audio Engine:** Create the `sounddevice` process to fill the buffer (`engine.py`).

### Phase 2: Data & State
1.  **Database Schema:** Define SQLite models for `Settings`, `Channels`, and `Scenes`.
2.  **Show Management:** Implement logic to load/save `.micwise` database files.

### Phase 3: Analysis & API
1.  **FastAPI Setup:** Create the web server and WebSocket endpoints.
2.  **Metering:** Implement RMS calculation and pipe it to the frontend via WebSockets.

### Phase 4: Streaming
1.  **WebRTC:** Implement `aiortc` tracks that read from the ring buffer.
2.  **Playback Control:** Add logic for "Live" vs "Replay" reading pointers.

### Phase 5: Frontend & Polish
1.  **React App:** Build the visual interface.
2.  **Discovery:** Add `zeroconf` broadcasting.
3.  **Packaging:** (Future) PyInstaller/Electron wrapping.
