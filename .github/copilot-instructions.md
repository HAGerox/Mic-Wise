# GitHub Copilot Instructions

## Priority Guidelines

When generating code for this repository:

1. **Read the closest real examples first**: start with this file, `docs/architecture/project_outline.md`, and the nearest matching implementation and test files.
2. **Preserve the current runtime split**: `backend/app/audio/engine.py` is the separate audio process; the FastAPI app in `backend/app/main.py` owns API routes, metering, WebRTC, discovery, and scene sync.
3. **Treat `AudioBuffer` as the integration boundary**: the shared `mmap` ring buffer in `backend/app/audio/buffer.py` is the source of truth between the audio writer and the async/backend services.
4. **Keep the frontend backend-served, but work in the React/Vite source**: the current UI source lives under `frontend/src/`, builds with Vite, and is served by FastAPI from `frontend/dist`. Edit source files, not generated build output.
5. **Prefer consistency over cleanup**: the repo mixes tabs and spaces between files, so preserve the indentation and local style of the file you are editing instead of normalizing unrelated code.
6. **Prioritize the right quality axis for the layer**:
   - **Audio/buffer/streaming hot paths**: predictable behavior, vectorized math, and low overhead.
   - **API/database/frontend code**: maintainability, explicit state changes, and async-safe I/O.

## Technology Detection and Compatibility

### Language and toolchain facts visible in the repository

- **Python**: no explicit version file is checked in (`pyproject.toml`, `.python-version`, and lockfiles are absent), but the codebase uses modern Python features such as `str | None`, built-in generics, and `@dataclass(slots=True)`. Stay compatible with the existing modern Python style and avoid introducing 3.12+-only syntax unless the repo later adds a formal version pin.
- **Frontend**: the repo now has a checked-in `frontend/package.json` using React 18, Vite 5, TypeScript 5, TanStack Query, SortableJS, and Vitest/React Testing Library. Use the existing npm scripts and do not reintroduce legacy plain-JS frontend assumptions.
- **Dependencies**: `backend/requirements.txt` currently lists `fastapi`, `uvicorn[standard]`, `sounddevice`, `numpy`, `aiortc`, `zeroconf`, `sqlalchemy`, `greenlet`, `aiosqlite`, `pydantic-settings`, `mido`, `python-osc`, `pytest`, and `httpx`. Versions are not pinned in-repo, so do not assume newer APIs than the code already demonstrates.

### Context files to prioritize

- `docs/architecture/project_outline.md`
- `.github/copilot-instructions.md`
- matching implementation files in `backend/app/` or `frontend/`
- matching tests in `backend/tests/` or `frontend/src/`

There is no dedicated `.github/copilot/` context folder in this repository today, so use the existing implementation files as the source of truth.

## Architecture and Module Boundaries

- `backend/app/main.py` creates the FastAPI app, seeds runtime state, creates the shared buffer file, starts the audio engine process, and starts async runtime services.
- `backend/app/audio/buffer.py` implements the shared `mmap` ring buffer using interleaved `int16` PCM data and a monotonic `write_head`.
- `backend/app/audio/engine.py` is responsible for writing audio into the buffer from either a deterministic synthetic source or `sounddevice` input.
- `backend/app/audio/analysis.py`, `backend/app/streaming/webrtc.py`, `backend/app/api/`, `backend/app/network/discovery.py`, and `backend/app/sync/service.py` run inside the FastAPI process and read from shared state or the audio buffer.
- `backend/app/database/` uses async SQLAlchemy with `sqlite+aiosqlite` for the show file.
- `frontend/src/App.tsx` owns high-level UI orchestration across the **Monitor**, **Show**, and **Setup** workflows.
- `frontend/src/api/` contains typed browser-side access to backend REST and streaming endpoints.
- `frontend/src/hooks/` owns transport-specific logic such as meters, waveform polling, and WebRTC listening state.
- `frontend/src/state/` owns reducer/context based local UI state.
- `frontend/src/lib/ui-logic.ts` contains pure UI helper logic and remains a good place for logic that should stay testable outside the React tree.
- `frontend/styles.css` is the shared stylesheet; `frontend/index.html` is the Vite entry shell; `frontend/dist` is generated output.
- Persisted show data belongs under `data_directory`; the shared buffer belongs under `runtime_directory` (see `backend/app/core/settings.py`) and should stay local and disposable.

## Codebase Scanning Instructions

When context files are not enough, inspect the closest matching code before generating anything new.

1. **For API changes**, mirror `backend/app/api/routes.py`:
   - `APIRouter`
   - typed request/response models
   - `request.app.state` for shared services
   - `HTTPException` for route-level errors

2. **For database changes**, mirror `backend/app/database/repository.py` and `backend/app/database/models.py`:
   - async repository helpers
   - ORM-backed return values
   - normalization close to the data layer
   - explicit ordering and compaction rules

3. **For settings/configuration changes**, mirror `backend/app/core/settings.py`:
   - `pydantic-settings`
   - `MICWISE_` env prefix
   - optional `.env`
   - computed path properties

4. **For audio, metering, or streaming changes**, mirror `backend/app/audio/*.py` and `backend/app/streaming/webrtc.py`:
   - typed helpers
   - `numpy`-based operations
   - wraparound-safe reads
   - live-edge protection and replay handling

5. **For frontend behavior**, mirror the current React frontend under `frontend/src/`:
   - `App.tsx` for top-level orchestration
   - `frontend/src/components/` for view and interaction structure
   - `frontend/src/hooks/` for meters/WebRTC/waveform transport concerns
   - `frontend/src/state/` for reducer/context-driven UI state
   - `frontend/src/lib/ui-logic.ts` for pure logic that should remain easy to test

6. **For tests**, mirror the nearest test file instead of inventing a new style.

## Observed Code Patterns

### Python patterns

- Start modules with a short module docstring and `from __future__ import annotations`.
- Use built-in generics (`list[...]`, `dict[...]`) and `| None` unions.
- Use `@dataclass(slots=True)` for compact config/status payloads when it fits the existing pattern (`AudioEngineConfig`, `MeterSnapshot`, `ExternalSyncEvent`, `SceneSyncStatusSnapshot`).
- Keep public functions and methods typed.
- Prefer pragmatic error handling:
  - `ValueError` / `RuntimeError` in core logic
  - `HTTPException` in routes
  - graceful early returns for optional runtime features
- Import optional host-dependent integrations defensively, as in `backend/app/sync/service.py`.

### Audio, buffer, and streaming patterns

- Keep the audio engine hot path focused on audio acquisition and buffer writes.
- Favor `numpy` vectorized operations over Python loops (`engine.py`, `analysis.py`, `webrtc.py`).
- Preserve ring-buffer semantics: interleaved `int16` frames, monotonic write head, wraparound-safe reads, and clamped readable ranges.
- Keep browser metering and playback aligned via `playback_sync_delay_frames()` rather than inventing separate timing constants.
- Preserve the persistent WebRTC transport plus control-data-channel model; selection updates should reuse the existing connection when possible.

### Frontend patterns

- Keep the current React + TypeScript structure rather than mixing in ad-hoc DOM scripting.
- Preserve the three current UX modes: **Monitor**, **Show**, and **Setup**.
- Treat timer-driven async work defensively. Preserve request-token or selection checks before applying async results when polling or updating selected entities.
- Keep TanStack Query for REST-backed server state and reducer/context state for local UI state unless the task clearly requires a different split.
- Preserve the current transport separation: meter updates, waveform polling, and WebRTC/control-channel logic belong in hooks rather than in random components.
- Prefer extracting pure state/formatting helpers into `frontend/src/lib/ui-logic.ts` and covering them with Vitest.
- Preserve the existing accessibility baseline in the JSX markup: semantic buttons, labels, `aria-label`, `aria-hidden`, and tab semantics are already in use.
- Avoid adding large frontend dependencies or alternate state libraries unless the task genuinely needs them.

## Code Quality Standards

### Maintainability

- Follow the naming and organization conventions already present in the target file.
- Preserve explicit state transitions in frontend code and small focused helpers in backend code.
- Avoid broad refactors unless the task requires them.

### Performance

- In audio and streaming paths, avoid unnecessary allocations, blocking work, or extra abstraction layers.
- Reuse the current `numpy` and shared-buffer approach instead of introducing slower per-sample Python logic.
- Keep the sounddevice callback simple and dependency-light.

### Documentation

- Match the existing docstring style: concise module/class/function docstrings, with longer `Args`/`Raises` sections only where the behavior is non-obvious (for example `AudioBuffer`).
- Update `README.md` and `docs/architecture/project_outline.md` when a user-facing workflow or architectural boundary changes.

### Accessibility and UX robustness

- Preserve semantic HTML/JSX and keyboard-friendly controls already present in the React frontend.
- Maintain stale-response guards and selection checks in timer-driven UI flows.

## Testing Expectations

- Backend tests use `pytest` with focused unit tests and small integration tests under `backend/tests/`.
- Integration tests isolate runtime settings with `monkeypatch` and `tmp_path` (see `backend/tests/test_api.py`).
- Frontend tests use Vitest under `frontend/src/**/*.test.ts`, with React Testing Library available for component interactions.
- When adding browser logic that can be pure, prefer moving it into `frontend/src/lib/ui-logic.ts` (or a nearby pure helper module) and adding a Vitest test.
- Keep hardware-sensitive and network-sensitive tests deterministic; follow the existing pattern of testing audio and WebRTC logic directly without requiring real devices.

## Repository-Specific Guidance

- Use the existing npm-based frontend workflow (`frontend/package.json`, `package-lock.json`) rather than introducing an alternative package manager.
- Treat `frontend/dist`, `node_modules`, and `*.tsbuildinfo` files as generated artifacts; update source files instead.
- Do not commit generated local data files such as `backend/data/*.micwise` or `backend/data/*.buffer`.
- The implementation is the source of truth. If a document and the code disagree, follow the code and update the document.
- When in doubt, make the smallest change that preserves the existing architecture, data flow, and test style.
