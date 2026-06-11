## Runtime architecture

- Preserve the FastAPI/audio split: `backend/app/audio/engine.py` runs in a separate `multiprocessing.Process`; API routes, WebSockets, metering, alerts, WebRTC, discovery, RadioWorld, and scene sync stay in the FastAPI process.
- Use `backend/app/audio/buffer.py` as the process boundary: the engine writes interleaved `int16` PCM to the shared `mmap` ring buffer, while analysis, alerts, waveform previews, and WebRTC read copied arrays from it.
- Keep the `mmap` buffer disposable under `runtime_directory/port-{port}`; persisted show data belongs under `data_directory`, because cloud-synced mapped files caused macOS `SIGBUS`/truncation failures and multi-instance collisions.
- Treat display channels as show-file rows independent of physical input capacity; deleting display channels is user intent and must not be undone by reseeding unless the show has no channels at all.
- Showfile import/export is portable by show semantics, not database IDs: scene assignments round-trip by channel number, and the active scene by scene order index.

## Audio and streaming

- Synthetic audio must pace blocks against a monotonic `time.perf_counter()` deadline, not a fixed sleep, to avoid long-listen WebRTC underruns/clicks near the live edge.
- Keep browser audio and meter timing aligned through `playback_sync_delay_frames()` rather than separate live-edge constants.
- Preserve the persistent WebRTC connection plus `micwise-control` data channel: selection/replay changes update the existing track with crossfades; rebuild the peer connection only after transport failure.
- WebRTC tests intentionally stub route-level signaling and test stream logic directly; avoid hardware/network-dependent integration tests for ICE, audio devices, OSC, MIDI, or UDP broadcast behavior.

## Persistence and integrations

- Route show-file mutations through `backend/app/database/repository.py` so migrations, normalization, ordering, and import/export semantics stay centralized.
- Optional host integrations fail soft: audio device discovery, Zeroconf, OSC, MIDI, network interface discovery, and RadioWorld UDP should degrade to empty status/error info rather than breaking core monitoring.
- RadioWorld follows the captured UDP protocol in `docs/Radio World UDP Protocol Specification.md`: source/destination port `1090`, payload `RWSENDIP{sender_ip}#{command}`, duplicate command packets about 39 ms apart, `KEYP{text}`/`KEYP{text}\n`, `COMM0` flash, `COMM1` unflash, `COMM8` clear.
- Audio input devices are persisted as stable `hostapi::device` selectors; `hardware` is only a UI/API alias that normalizes to `sounddevice`.
- Scene sync matches normalized OSC/MIDI events against persisted scene cue fields and only changes `settings.active_scene_id`; it does not mutate frontend checklist state.

## Frontend

- Preserve the operator workflows: `monitor` for all-channel monitoring, `show` for scene-focused mic checks, and `setup` for channel, scene, sync, alert, RadioWorld, and showfile programming.
- Keep server state in TanStack Query, local interaction state in `frontend/src/state/appStateReducer.ts`, and transport work in hooks such as `useMeters`, `useWaveform`, and `useAudioTransport`.
- Put pure browser workflow logic in `frontend/src/lib/ui-logic.ts` or a nearby pure helper with Vitest coverage rather than burying it in React components.
- Guard timer/transport-driven UI updates with request tokens or selected-entity checks before applying async results, so stale work cannot repaint the wrong selection.
- Keep the dark, Linear-inspired UI vocabulary in `DESIGN.md`/`frontend/styles.css`; prefer existing CSS variables/patterns over a component library or unrelated visual system.

## Working constraints

- No Python version is pinned; use the existing modern baseline (`str | None`, built-in generics, `@dataclass(slots=True)`) but avoid 3.12+-only syntax.
- If docs and implementation disagree, follow implementation; update `README.md` or `docs/architecture/project_outline.md` only when a user-facing workflow or architecture boundary changes.
- Use the closest existing tests as the behavior oracle: backend tests rely on isolated `tmp_path`/`monkeypatch` pytest patterns, and frontend tests use Vitest with React Testing Library or pure helper tests.
