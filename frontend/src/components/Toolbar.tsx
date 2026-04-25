import type { ActiveView } from '../types/ui';

interface ToolbarProps {
  activeView: ActiveView;
  layoutMode: boolean;
  multiListen: boolean;
  selectedCount: number;
  statusText: string;
  activeSceneName: string;
  showCheckedCount: number;
  showTotalCount: number;
  onSetActiveView: (view: ActiveView) => void;
  onToggleListenMode: () => void;
  onToggleLayoutMode: () => void;
  onStopListening: () => void;
}

export function Toolbar({
  activeView,
  layoutMode,
  multiListen,
  selectedCount,
  statusText,
  activeSceneName,
  showCheckedCount,
  showTotalCount,
  onSetActiveView,
  onToggleListenMode,
  onToggleLayoutMode,
  onStopListening,
}: ToolbarProps): JSX.Element {
  return (
    <section className="controls toolbar">
      <div className="toolbar-main">
        <div className="control-group segmented-control" role="tablist" aria-label="Main views">
          <button
            id="view-monitor"
            className={`segment-button ${activeView === 'monitor' ? 'is-active' : ''}`}
            type="button"
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
            onClick={() => onSetActiveView('show')}
          >
            <span className="button-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" focusable="false"><path d="M4 6h16"></path><path d="M4 12h16"></path><path d="M4 18h10"></path><path d="m17 14 4 4-4 4"></path></svg>
            </span>
            <span className="button-label">Show</span>
          </button>
        </div>

        <div id="toolbar-actions" className="control-group button-row">
          <button id="listen-mode-toggle" type="button" className={multiListen ? 'is-active' : ''} onClick={onToggleListenMode}>
            <span className="button-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" focusable="false"><path d="M12 4a8 8 0 0 0-8 8v3a3 3 0 0 0 3 3h1v-7H7a5 5 0 0 1 10 0h-1v7h1a3 3 0 0 0 3-3v-3a8 8 0 0 0-8-8Z"></path></svg>
            </span>
            <span className="button-label">{multiListen ? 'Multi listen' : 'Single listen'}</span>
          </button>

          <button
            id="layout-mode-toggle"
            className={`secondary ${layoutMode ? 'is-active' : ''} ${activeView === 'monitor' ? '' : 'is-hidden'}`}
            type="button"
            disabled={activeView === 'show'}
            onClick={onToggleLayoutMode}
          >
            <span className="button-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" focusable="false"><path d="m4 20 4-1 10-10-3-3L5 16l-1 4Z"></path><path d="m14 6 3 3"></path></svg>
            </span>
            <span className="button-label">{layoutMode ? 'Done arranging' : 'Arrange'}</span>
          </button>

          <button
            id="stop-listening"
            className={`secondary ${selectedCount > 0 ? 'is-armed' : ''}`}
            type="button"
            onClick={onStopListening}
          >
            <span className="button-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" focusable="false"><path d="M6 6h12v12H6z"></path></svg>
            </span>
            <span className="button-label">Clear</span>
          </button>
        </div>

        <button
          id="view-setup"
          className={`secondary toolbar-utility ${activeView === 'setup' ? 'is-active' : ''}`}
          type="button"
          onClick={() => onSetActiveView('setup')}
        >
          <span className="button-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" focusable="false"><path d="M12 3v3"></path><path d="M12 18v3"></path><path d="m4.93 4.93 2.12 2.12"></path><path d="m16.95 16.95 2.12 2.12"></path><path d="M3 12h3"></path><path d="M18 12h3"></path><path d="m4.93 19.07 2.12-2.12"></path><path d="m16.95 7.05 2.12-2.12"></path><circle cx="12" cy="12" r="3.5"></circle></svg>
          </span>
          <span className="button-label">Setup</span>
        </button>
      </div>

      <div className="toolbar-status-strip" aria-label="Current system status">
        <span className="toolbar-pill">Audio <strong id="status-text">{statusText}</strong></span>
        <span className="toolbar-pill">Selected <strong id="selection-count-text">{selectedCount} channel{selectedCount === 1 ? '' : 's'}</strong></span>
        <span id="show-scene-pill" className={`toolbar-pill ${activeView === 'show' ? '' : 'is-hidden'}`}>
          Scene <strong id="scene-status-text">{activeSceneName}</strong>
        </span>
        <span id="show-progress-pill" className={`toolbar-pill ${activeView === 'show' ? '' : 'is-hidden'}`}>
          Mic check <strong id="show-progress-text">{showCheckedCount}/{showTotalCount} checked</strong>
        </span>
      </div>
    </section>
  );
}
