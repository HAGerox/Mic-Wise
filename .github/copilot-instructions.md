# GitHub Copilot Instructions

## Priority Guidelines

When generating code for this repository:

1. **Version Compatibility**: Target **Python 3.11+** and **Node.js 20+**.
2. **Context Files**: Prioritize the architecture defined in `docs/architecture/project_outline.md`.
3. **Architectural Consistency**: Maintain the strict separation between the **Audio Engine** (Multiprocessing, shared memory) and the **Web Server** (Asyncio).
4. **Code Quality**: 
   - **Audio Engine**: Prioritize **Performance** and **Zero-Latency** (avoid allocations in hot loops).
   - **Web/API/UI**: Prioritize **Maintainability**, **Async I/O**, and predictable state updates across polling/WebSocket/WebRTC flows.

## Technology Stack & Versions

1. **Language Versions**:
   - Python: 3.11+
   - JavaScript/TypeScript: ES2022+

2. **Frameworks**:
   - Backend: **FastAPI**
   - Frontend: **Vanilla HTML/CSS/JavaScript modules** served directly by the backend
   - Audio: **PortAudio** (via `sounddevice`)

3. **Key Libraries**:
   - `numpy`: For audio buffer manipulation.
   - `aiortc`: For WebRTC streaming.
   - `mido` + `python-osc`: For optional external scene-sync integrations.
   - `zeroconf`: For service discovery.
   - `sqlalchemy` + `aiosqlite`: For database interactions.

## Codebase Patterns & Structure

### Folder Structure
- `backend/`: Python backend code.
  - `app/audio/`: Real-time audio processing (Multiprocessing).
  - `app/api/`: FastAPI web server (Asyncio).
   - `app/sync/`: Optional external scene-sync runtime services.
  - `app/database/`: Database models and logic.
- `frontend/`: Static browser client (`index.html`, `styles.css`, `app.js`, pure helpers in `ui_logic.mjs`).

### Python Guidelines
- **Type Hinting**: Use strict type hints (`typing` module) for all function signatures.
- **Concurrency**: 
  - Use `async`/`await` for all I/O bound operations (API, DB).
  - Use `multiprocessing` for CPU-bound or real-time audio tasks.
  - **NEVER** block the asyncio event loop with heavy computation.
- **Runtime Files**: Keep the shared mmap audio buffer under the configured runtime directory, not the persistent show-data directory.

### Frontend Guidelines
- Keep the browser UI dependency-light and framework-free unless the user explicitly requests a stack change.
- Prefer extracting pure state/formatting helpers into `frontend/ui_logic.mjs` and cover them with `node --test` in `frontend/tests/`.
- The current UX is organized around three views: **Monitor**, **Show**, and **Setup**.
- Treat timer-driven async fetches defensively: ignore stale responses when the selected channel or scene changes.
- Preserve the persistent WebRTC transport plus control-data-channel model instead of rebuilding the transport for every selection change.

### React Guidelines (Future)
- Use **Functional Components** with Hooks.
- Use **Context API** for global state management.
- Use **CSS Modules** or **Tailwind** for styling.

## Code Quality Standards

### Performance (Audio Engine)
- **Zero-Copy**: Use `memoryview` and `mmap` for passing audio data between processes.
- **Pre-allocation**: Allocate buffers at startup. Avoid `malloc` inside the audio callback.
- **Vectorization**: Use `numpy` operations instead of Python loops for audio data processing.

### Maintainability
- **Docstrings**: Use Google-style docstrings for all modules, classes, and functions.
- **Configuration**: Use `pydantic` for settings management.
- **UI State**: Keep browser-side state transitions explicit and small; prefer helper functions for scene selection, sync status text, and waveform interpolation logic.

## Documentation Requirements

- **Standard**: Document all public API endpoints and complex audio logic.
- **Architecture**: Update `docs/architecture/` if introducing new system components.

## Testing Approach

### Unit Testing
- Use `pytest`.
- Mock hardware interfaces (`sounddevice`) for logic tests.
- Test asyncio coroutines using `pytest-asyncio`.
- Use `node --test frontend/tests/*.test.mjs` for pure frontend helper coverage.

## Version Control Guidelines

- **Semantic Versioning**: Follow SemVer.
- **Commits**: Use conventional commits (e.g., `feat:`, `fix:`, `docs:`).
