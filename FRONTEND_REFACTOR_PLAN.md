# Frontend Refactor Plan

## Goal

Modernise the current vanilla frontend into a more maintainable and future-friendly frontend without adding unnecessary complexity.

The target is **better structure, safer typing, easier testing, and smoother future growth** while keeping the deployment model simple: the backend should still serve a built static frontend.

---

## Review outcome

The earlier draft was directionally correct, but it was slightly more complex than it needs to be on day one.

The main simplification is:

- **Keep React + Vite + TypeScript**
- **Keep TanStack Query for HTTP-backed server state**
- **Do not add Zustand or another client-state library initially**
- Use **native React state, reducers, and context** for UI state
- Treat the **meter WebSocket and WebRTC transport as dedicated hooks/services**, not global app state libraries

This gives a modern stack that is widely used, well supported by LLMs, and much easier to maintain than the current single-file vanilla frontend, without over-engineering the app.

---

## Recommended stack

### Core stack

- **React** — component model and ecosystem
- **Vite** — dev server, build pipeline, fast refresh
- **TypeScript** — typed frontend models matching backend schemas

### Supporting tools

- **TanStack Query** — for REST API data and mutations
- **Vitest** — test runner
- **React Testing Library** — UI/component testing
- **CSS Modules** — scoped styles while keeping CSS simple
- **SortableJS (npm package)** — keep the current layout-dragging capability, but install it properly instead of loading it from a CDN

### Deliberately not adding initially

- **No Next.js / SSR** — not needed for a LAN-served operational tool
- **No React Router** — the app has modes, not pages
- **No Redux / Zustand / XState initially** — unnecessary unless performance profiling later proves otherwise
- **No Tailwind or large UI kit** — would add migration churn without clear value for this custom interface
- **No form library** — current forms are manageable with normal React patterns

---

## Why this is the right level of complexity

This project is not a marketing website or a public SaaS dashboard.
It is a **specialist operational tool** with:

- a real-time meter stream
- a WebRTC audio path
- a shared set of backend-driven entities (`channels`, `scenes`, `settings`)
- some client-local behaviour (selected listen channels, modal state, current view)

That means the frontend should be:

- **structured enough** to stop the current `app.js` from growing further
- **typed enough** to make API contracts safer
- **testable enough** to preserve behaviour during refactoring
- **simple enough** that a single developer can still reason about it quickly

React + Vite + TypeScript is the sweet spot here.

---

## Current frontend snapshot

The existing frontend is already substantial:

- `frontend/app.js` is about **1912 lines** with **103 functions**
- `frontend/ui_logic.mjs` contains **8 pure exported helpers**
- `frontend/styles.css` is about **1075 lines**
- `frontend/tests/ui_logic.test.mjs` contains **9 existing tests**
- the frontend talks to **17 REST endpoints**, **1 WebSocket**, and **WebRTC**

This is beyond the point where plain DOM scripting is the easiest long-term option.

---

## Target architecture

### 1. React components for UI structure

Break the monolithic frontend into components such as:

- `AppShell`
- `Toolbar`
- `StatusStrip`
- `ChannelGrid`
- `ChannelCard`
- `ShowSidebar`
- `SetupView`
- `ProgramTable`
- `SceneEditor`
- `ChannelModal`
- `WaveformCanvas`

This reduces cognitive load and makes individual features easier to change safely.

### 2. Typed API layer

Create a small typed frontend API layer that mirrors backend schemas and routes.

Examples:

- `api/channels.ts`
- `api/scenes.ts`
- `api/settings.ts`
- `api/streaming.ts`
- `api/sync.ts`
- `types/api.ts`

The backend Pydantic schemas should become TypeScript interfaces/types.

### 3. Server state vs local UI state

Use a simple split:

#### Server state
Managed with **TanStack Query**:

- channels
- scenes
- settings
- sync status
- waveform fetches

#### Local UI state
Managed with **React state / reducers / context**:

- active view
- setup tab
- selected channel ids
- modal open state
- active scene id
- layout mode
- multi-listen toggle

#### Real-time transport state
Handled in dedicated hooks/services:

- meter WebSocket
- WebRTC peer connection
- audio data channel

This keeps responsibilities clear without introducing a second global state library too early.

---

## Migration principles

1. **Refactor in place, not as a rewrite-from-memory**
   - preserve existing behaviour first
   - improve structure second

2. **Move the pure logic first**
   - `ui_logic.mjs` should become a typed utility module early
   - migrate its tests before moving larger UI behaviour

3. **Keep FastAPI as the production host**
   - Vite is a dev/build tool
   - FastAPI still serves the built frontend in production

4. **Avoid premature abstraction**
   - build the component tree first
   - only add more state tooling if profiling proves it is needed

5. **Keep visual churn low during migration**
   - initially preserve the existing UI and CSS behaviour
   - do not redesign and refactor at the same time

---

## High-level migration phases

## Phase 1 — Tooling foundation

Set up a modern frontend build without changing product behaviour.

### Deliverables

- Vite React + TypeScript app scaffold inside `frontend/`
- `vitest` + React Testing Library configured
- CSS Modules enabled
- SortableJS installed from npm
- Vite dev proxy configured to forward API/WebSocket calls to FastAPI

### Outcome

The app can now be developed with fast refresh and typed code, but the migration risk is still low.

---

## Phase 2 — Port pure logic and tests first

Move the safest and most reusable pieces before UI conversion.

### Deliverables

- Convert `frontend/ui_logic.mjs` to `frontend/src/lib/ui-logic.ts`
- Convert `frontend/tests/ui_logic.test.mjs` to Vitest
- Preserve all existing test behaviour

### Outcome

The existing business logic becomes typed and remains verified throughout the refactor.

---

## Phase 3 — Build the data and transport layer

Create the foundations the components will sit on.

### Deliverables

- typed API client modules
- TypeScript types matching backend schemas
- `useMeters` hook for the `/ws/meters` stream
- `useAudioTransport` hook for WebRTC setup and listen control
- `useAppState` reducer/context for local UI state
- TanStack Query setup for REST-backed data

### Outcome

Data flow becomes explicit before the visual layer is migrated.

---

## Phase 4 — Migrate the UI by feature slice

Move from the outside in, keeping the app usable during migration.

### Recommended order

1. App shell and toolbar
2. Monitor channel grid and channel card
3. Modal / docked waveform panel
4. Show mode sidebar and scene summary
5. Setup mode panels
6. Scene editor and sync settings

### Outcome

The app gains structure incrementally instead of via a risky all-at-once rewrite.

---

## Phase 5 — Move styling into a maintainable structure

Keep the existing visual design, but split styling by responsibility.

### Deliverables

- global `tokens.css` / base stylesheet for theme variables and resets
- component-level CSS Modules for cards, toolbar, modal, tables, scenes, etc.
- preserve existing dark theme and responsive layout behaviour

### Outcome

Styles become easier to change without accidental regressions.

---

## Phase 6 — Cutover and cleanup

Switch fully from the old frontend to the new one only once feature parity is reached.

### Deliverables

- FastAPI updated to serve built assets from Vite output
- remove old `app.js`, `ui_logic.mjs`, and old test setup once no longer needed
- verify multi-client behaviour in browser tabs/devices
- update README setup instructions

### Outcome

The project ends with one clear frontend path instead of a half-migrated hybrid.

---

## Testing plan

The current tests should be preserved and expanded.

### Existing tests to migrate

Migrate the current `ui_logic` tests directly to Vitest.

### New tests to add during migration

Add focused tests for:

- channel selection behaviour
- scene filtering/checklist behaviour
- view switching
- waveform display logic where practical
- settings update flows
- sync status display logic

### Test strategy

- keep pure logic in utility modules where possible
- use React Testing Library for component interactions
- avoid over-testing markup details
- focus on behaviour the operator actually relies on

---

## Performance guidance

The only area that needs special care is the **meter stream**.

To keep the first version simple:

- avoid putting the whole meter snapshot into a broad React context
- memoise channel cards where needed
- keep meter updates isolated to the components that need them
- profile before introducing a dedicated external store library

If profiling later shows React state is insufficient for the meter path, then adding **Zustand** later is a valid second-step optimisation — but it should not be required from day one.

---

## Suggested project structure

```text
frontend/
  src/
    api/
      channels.ts
      scenes.ts
      settings.ts
      streaming.ts
      sync.ts
    components/
      ChannelCard/
      ChannelGrid/
      Toolbar/
      ShowSidebar/
      SetupView/
      SceneEditor/
      ChannelModal/
      WaveformCanvas/
    hooks/
      useMeters.ts
      useAudioTransport.ts
    lib/
      ui-logic.ts
      format.ts
    state/
      AppStateContext.tsx
      appStateReducer.ts
    styles/
      tokens.css
      globals.css
    types/
      api.ts
      ui.ts
    App.tsx
    main.tsx
  public/
  index.html
```

This is modern, but still small enough to stay understandable.

---

## Final recommendation

Use this stack for the migration:

- **React**
- **Vite**
- **TypeScript**
- **TanStack Query**
- **Vitest**
- **React Testing Library**
- **CSS Modules**
- **SortableJS (installed locally)**

And specifically **do not** start with:

- Redux
- Zustand
- Router
- Tailwind
- Next.js
- a component library

That keeps the refactor modern and future-compatible while still being appropriately lean for this project.

The right goal is not to make the frontend “fancy”; it is to make it **safer to grow**.
