import type { ActiveView } from '../types/ui';

interface ToolbarProps {
  activeView: ActiveView;
  selectedCount: number;
  statusText: string;
  activeSceneName: string;
  nextSceneName: string | null;
  showCheckedCount: number;
  showTotalCount: number;
  canGoToPreviousScene: boolean;
  canGoToNextScene: boolean;
  onSetActiveView: (view: ActiveView) => void;
  onStopListening: () => void;
  onNavigateScene: (offset: number) => void;
}

export function Toolbar({
  activeView,
  selectedCount,
  statusText,
  activeSceneName,
  nextSceneName,
  showCheckedCount,
  showTotalCount,
  canGoToPreviousScene,
  canGoToNextScene,
  onSetActiveView,
  onStopListening,
  onNavigateScene,
}: ToolbarProps): JSX.Element {
  const showStatusText = statusText !== 'Online' && statusText !== 'Streaming';

  return (
    <section className={`controls toolbar ${activeView === 'show' ? 'is-show-view' : ''}`}>
      <div className="toolbar-main">
        <div className="toolbar-main-left">
          <nav className="control-group segmented-control" aria-label="Primary views">
            <button
              id="view-monitor"
              className={`segment-button ${activeView === 'monitor' ? 'is-active' : ''}`}
              type="button"
              aria-current={activeView === 'monitor' ? 'page' : undefined}
              aria-controls="monitor-view"
              onClick={() => onSetActiveView('monitor')}
            >
              <span className="button-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" focusable="false"><rect x="3" y="4" width="18" height="12" rx="2"></rect><path d="M8 20h8"></path><path d="M12 16v4"></path></svg>
              </span>
              <span className="button-label">Monitor</span>
            </button>
            <button
              id="view-show"
              className={`segment-button ${activeView === 'show' ? 'is-active' : ''}`}
              type="button"
              aria-current={activeView === 'show' ? 'page' : undefined}
              aria-controls="monitor-view"
              onClick={() => onSetActiveView('show')}
            >
              <span className="button-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" focusable="false"><path d="M4 6h16"></path><path d="M4 12h16"></path><path d="M4 18h10"></path><path d="m17 14 4 4-4 4"></path></svg>
              </span>
              <span className="button-label">Show</span>
            </button>
            <button
              id="view-setup"
              className={`segment-button ${activeView === 'setup' ? 'is-active' : ''}`}
              type="button"
              aria-current={activeView === 'setup' ? 'page' : undefined}
              aria-controls="setup-view"
              onClick={() => onSetActiveView('setup')}
            >
              <span className="button-icon" aria-hidden="true">
                <svg viewBox="0 0 24 24" focusable="false"><path d="M12 3v3"></path><path d="M12 18v3"></path><path d="m4.93 4.93 2.12 2.12"></path><path d="m16.95 16.95 2.12 2.12"></path><path d="M3 12h3"></path><path d="M18 12h3"></path><path d="m4.93 19.07 2.12-2.12"></path><path d="m16.95 7.05 2.12-2.12"></path><circle cx="12" cy="12" r="3.5"></circle></svg>
              </span>
              <span className="button-label">Setup</span>
            </button>
          </nav>
        </div>

        <div className="toolbar-main-center">
          {activeView === 'show' ? (
            <div className="toolbar-scene-control" aria-label="Scene controls">
              <button
                type="button"
                className="toolbar-scene-step"
                aria-label="Previous scene"
                disabled={!canGoToPreviousScene}
                onClick={() => onNavigateScene(-1)}
              >
                ‹
              </button>
              <div className="toolbar-scene-copy" aria-label={`Current scene ${activeSceneName}`}>
                <strong id="scene-status-text">{activeSceneName}</strong>
              </div>
              <span className="toolbar-scene-divider" aria-hidden="true"></span>
              <div className="toolbar-scene-copy toolbar-scene-copy--checklist" aria-label={`${showCheckedCount} of ${showTotalCount} channels checked`}>
                <strong id="show-progress-text">{showCheckedCount}/{showTotalCount}</strong>
              </div>
              <button
                type="button"
                className="toolbar-scene-next"
                aria-label="Advance to next scene"
                disabled={!canGoToNextScene}
                onClick={() => onNavigateScene(1)}
              >
                {nextSceneName ? `Next: ${nextSceneName}` : 'End of show'}
              </button>
            </div>
          ) : null}
        </div>

        <div id="toolbar-actions" className={`control-group button-row toolbar-main-right ${activeView === 'setup' ? 'is-setup-context' : ''}`}>
          <button
            id="stop-listening"
            className={`toolbar-stop-button ${activeView === 'setup' ? 'is-setup-context' : ''} ${selectedCount > 0 ? '' : 'is-hidden'}`}
            type="button"
            onClick={onStopListening}
          >
            <span className="button-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" focusable="false"><path d="M6 6h12v12H6z"></path></svg>
            </span>
            <span className="button-label">{activeView === 'setup' ? 'Stop audio' : 'Stop all'}</span>
          </button>
        </div>
      </div>

      {showStatusText ? (
        <div className="toolbar-status-strip" aria-label="Current context">
          <span id="status-text" className="toolbar-notice" role="status">{statusText}</span>
        </div>
      ) : null}
    </section>
  );
}
