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
- Zeroconf discovery advertising `_micwise._tcp` so Stage Backup finds this show automatically
- optional OSC / MIDI scene sync runtime in `backend/app/sync/service.py`
- optional RChat UDP alert notifications with configurable sender name and network interface

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

## Standalone app builds

For show computers you can build a self-contained app that needs no Python or
Node install. On the platform you are targeting (PyInstaller does not
cross-compile, so build on macOS for macOS, Windows for Windows, Linux for
Linux), run:

```text
python packaging/build.py
```

This builds the frontend, then bundles the backend, the UI, and all native
dependencies into a single artifact per platform:

- **macOS**: `dist/MicWise-0.1.0-alpha.4-macOS-arm64.dmg` on Apple Silicon
  (or an `x86_64.dmg` on Intel). Release builds require macOS 14 or later.
  Open the disk image, drag `MicWise.app` to
  Applications, eject the image, and open the app. No Python or Node installation
  is needed. The operator interface opens in your default browser. Click the Dock
  icon or choose **Open Mic-Wise** to reopen it; quit with Dock → Quit or Cmd-Q.
  Startup failures appear in a dialog and details go to the server log.
- **Windows**: `dist/MicWise.exe` — a single file. Double-click to run; a
  console window shows the server log, and closing it stops the server.
- **Linux**: `dist/MicWise` — a single executable file.

In all cases the server starts and the operator UI opens in the default
browser; other machines on the network can connect to
`http://<host-ip>:8000/`.

The build derives the native app icon from
`packaging/assets/micwise-icon-source.png`, centre-cropping it to a square
before embedding an `.icns` in the macOS app or an `.ico` in the Windows
executable. Linux remains a single executable without a separate icon file.

Standalone builds keep show files (and `micwise-server.log` for the macOS
app) in the per-user data directory (`~/Library/Application
Support/Mic-Wise` on macOS, `%APPDATA%\Mic-Wise` on Windows,
`~/.local/share/Mic-Wise` on Linux) instead of `backend/data`. All
`MICWISE_*` environment variables still apply, e.g. `MICWISE_PORT=9000` or
`MICWISE_NO_BROWSER=1`.

To update on macOS, quit Mic-Wise, replace `/Applications/MicWise.app` with the
new app, and reopen it. Show data, photos, and mic-check ticks remain in
`~/Library/Application Support/Mic-Wise`; replacing the app never removes them.
While monitoring, the app prevents App Nap and automatic idle sleep so closing
the browser does not pause the audio service. Only one app may own a data
directory, and the launcher reserves its HTTP port before starting audio so duplicate launches cannot truncate an active buffer.

Local alpha builds are ad-hoc signed and **not notarized**. On a receiving Mac,
if Gatekeeper blocks launch, attempt to open the app, then use **System Settings
→ Privacy & Security → Open Anyway**. A normal trusted first launch requires an
Apple-issued Developer ID Application certificate and notarization. For that
build, set `MICWISE_SIGNING_IDENTITY` to the certificate name and
`MICWISE_NOTARY_PROFILE` to a `notarytool` Keychain profile before running the
build command. The build verifies signing, submits the app, staples the ticket,
and assesses Gatekeeper before making the disk image. Do not use the local
self-signed T3 identity as a distribution certificate.

For macOS release builds, use a clean Python 3.11 environment as in release CI;
Homebrew Python may impose a newer macOS requirement. The build derives the
minimum macOS version from bundled native libraries.

On Intel Macs, the current cryptography dependency builds from source. Install
`openssl@3` and `rust` with Homebrew, then set `OPENSSL_STATIC=1` and
`OPENSSL_DIR="$(brew --prefix openssl@3)"` when installing the backend requirements.
This keeps the bundled crypto library independent of the build Mac's Homebrew
installation. Release CI performs this setup automatically.

The alpha release identity lives in `backend/app/version.py`; increment it for
each release. `MICWISE_BUILD_NUMBER` supplies the macOS bundle build number.
The installer includes a checksum and `dist/release-info.json` records the source
revision, whether working-tree changes were included, and notarization status.
The release workflow tests the software and builds separate Intel and Apple
Silicon installers. This first alpha no longer migrates pre-alpha database
schemas or imports version 1 showfiles, and removes retired RadioWorld field
names and UI modes. The `hardware` UI/API alias remains supported and normalises to `sounddevice`.

Standalone apps ignore working-directory `.env` files; explicit `MICWISE_*`
environment variables still apply. Discovery is enabled by default. Stage Backup
(the `sound-backup` project) identifies the app through `GET /api/health` and
pulls `GET /api/showfile/export?format=archive`. That archive includes photos,
scene staging, mic-check ticks, and SHA-256 checksums, and can be restored with
**Setup → Import show**. Its **Back up now** link launches Stage Backup on the
same Mac; network backups are initiated from the Stage Backup hub.

The source-checkout workflow above is unchanged and remains the development
path.

## Default runtime behaviour

On a clean first run, the current backend defaults are:

- audio source mode: `synthetic`
- sample rate: `48000`
- channel count: `16`
- rolling buffer duration: `300` seconds
- block size: `480` frames
- Zeroconf discovery: enabled
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
- tracks a mic-check style checklist for scene members, persisted with the show
- supports keyboard shortcuts for checking and unchecking channels

### Setup

- programs channel names, patching, trim, and rolling-record flags
- uploads channel photos into the show's local asset library, so they travel with backups
- creates, reorders, and edits scenes
- maps scene cues to OSC and/or MIDI patterns
- gives each scene a portable `/micwise/scene/{scene-number}` OSC trigger by default; send the address without arguments from a one-shot QLab Network cue, and add an argument only when an extra match filter is useful
- leaves MIDI patterns unset by default
- configures optional external scene sync settings
- configures optional RChat alert delivery, flash/hold behaviour, display name, and network interface

## Show backups and Stage Backup

Export produces a self-contained show archive:

```text
<show name>.micwise.zip
├── micwise-showfile.micwise.json   # portable showfile (format version 2)
├── assets/photos/<sha256>.<ext>    # embedded channel photos
└── backup.json                     # member sizes + SHA-256 checksums
```

Restoring that archive into any Mic-Wise session reproduces the show exactly:
channels, photos, scene staging, mic-check ticks, and every setting. Every member
is size- and checksum-verified on import, and paths that would escape the photo
library are rejected. A plain `.micwise.json` showfile is still accepted for
lightweight sharing using the current format (version 2). Pre-alpha version 1
showfiles are no longer supported.

Photos can be a remote URL or an upload. Uploaded photos live under
`data_directory/assets/photos/` and are embedded in the archive; remote URLs are
snapshotted into the archive when reachable and otherwise carried as URLs.

**Stage Backup** finds this show automatically. Mic-Wise advertises
`_micwise._tcp` over Zeroconf (disable with `MICWISE_ZEROCONF_ENABLED=false`)
with the show name in its TXT records, and `GET /api/health` answers an HTTP
probe with `{app, version, show_name, show_filename}`. Stage Backup pulls
`GET /api/showfile/export?format=archive` and writes
`<backup folder>/Mic-Wise/<UTC timestamp>_<Show>.micwise.zip`.

Setup → General → Showfile has a **Back up now** link (`stage-backup://backup?target=micwise`)
that opens Stage Backup and runs a one-click backup of this show, when Stage Backup
is installed on the same machine. Across the network, use the single **Back up now**
button in Stage Backup itself.

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
- `MICWISE_PHOTO_UPLOAD_MAX_BYTES`

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
