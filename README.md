# Mic-Wise

Mic-Wise is a browser-based monitoring tool for live sound and theatre radio microphone workflows.

The current MVP includes:

- a Python backend with a shared-memory rolling audio buffer
- a seeded SQLite "show file" for channels, settings, and scenes
- a synthetic multichannel audio source for hardware-free development
- live RMS / peak meter analysis
- WebSocket meter updates for the browser UI
- WebRTC audio streaming from selected channels
- an optional Zeroconf discovery service
- a lightweight browser monitor page served directly by the backend

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

## Default MVP behaviour

- The backend starts in `synthetic` audio mode by default.
- A default  show file is created in the backend data directory on first run.
- The browser UI shows the seeded channels, live meters, and listening controls.
- Listening uses WebRTC and can stream either live audio or audio a few seconds behind live.

## Useful environment variables

Mic-Wise uses the `MICWISE_` prefix for runtime configuration.

- `MICWISE_HOST`
- `MICWISE_PORT`
- `MICWISE_DATA_DIRECTORY`
- `MICWISE_SHOW_FILENAME`
- `MICWISE_BUFFER_FILENAME`
- `MICWISE_DEFAULT_SAMPLE_RATE`
- `MICWISE_DEFAULT_CHANNEL_COUNT`
- `MICWISE_DEFAULT_BUFFER_DURATION_SEC`
- `MICWISE_DEFAULT_BLOCK_SIZE`
- `MICWISE_AUDIO_SOURCE_MODE` (`synthetic` or `sounddevice`)
- `MICWISE_ZEROCONF_ENABLED` (`true` / `false`)

## Current scope

This MVP focuses on the monitoring path first:

- ingest / generate audio
- retain a rolling buffer
- expose meters and audio to a browser client

Scene authoring, richer replay controls, ML artifact detection, and a fuller frontend workflow are the next layers to build on top of this foundation.
