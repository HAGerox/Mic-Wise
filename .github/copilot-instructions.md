# GitHub Copilot Instructions

## Priority Guidelines

When generating code for this repository:

1. **Version Compatibility**: Target **Python 3.11+** and **Node.js 20+**.
2. **Context Files**: Prioritize the architecture defined in `docs/architecture/project_outline.md`.
3. **Architectural Consistency**: Maintain the strict separation between the **Audio Engine** (Multiprocessing, shared memory) and the **Web Server** (Asyncio).
4. **Code Quality**: 
   - **Audio Engine**: Prioritize **Performance** and **Zero-Latency** (avoid allocations in hot loops).
   - **Web/API**: Prioritize **Maintainability** and **Async I/O**.

## Technology Stack & Versions

1. **Language Versions**:
   - Python: 3.11+
   - JavaScript/TypeScript: ES2022+

2. **Frameworks**:
   - Backend: **FastAPI**
   - Frontend: **React** (via Vite)
   - Audio: **PortAudio** (via `sounddevice`)

3. **Key Libraries**:
   - `numpy`: For audio buffer manipulation.
   - `aiortc`: For WebRTC streaming.
   - `zeroconf`: For service discovery.
   - `sqlalchemy` + `aiosqlite`: For database interactions.

## Codebase Patterns & Structure

### Folder Structure
- `backend/`: Python backend code.
  - `app/audio/`: Real-time audio processing (Multiprocessing).
  - `app/api/`: FastAPI web server (Asyncio).
  - `app/database/`: Database models and logic.
- `frontend/`: React application.

### Python Guidelines
- **Type Hinting**: Use strict type hints (`typing` module) for all function signatures.
- **Concurrency**: 
  - Use `async`/`await` for all I/O bound operations (API, DB).
  - Use `multiprocessing` for CPU-bound or real-time audio tasks.
  - **NEVER** block the asyncio event loop with heavy computation.
- **Error Handling**: Use custom exception classes in `app/core/exceptions.py` (to be created).

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

## Documentation Requirements

- **Standard**: Document all public API endpoints and complex audio logic.
- **Architecture**: Update `docs/architecture/` if introducing new system components.

## Testing Approach

### Unit Testing
- Use `pytest`.
- Mock hardware interfaces (`sounddevice`) for logic tests.
- Test asyncio coroutines using `pytest-asyncio`.

## Version Control Guidelines

- **Semantic Versioning**: Follow SemVer.
- **Commits**: Use conventional commits (e.g., `feat:`, `fix:`, `docs:`).
