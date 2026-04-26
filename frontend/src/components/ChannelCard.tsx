import { memo, useEffect, useRef } from 'react';

import type { ChannelCardState } from '../types/ui';

const LONG_PRESS_MS = 420;

function buildSparklinePoints(history: number[]): string {
  const safeHistory = history.length > 0 ? history : [0, 0, 0, 0];
  return safeHistory
    .map((value, index) => {
      const x = safeHistory.length === 1 ? 50 : (index / (safeHistory.length - 1)) * 100;
      const y = 23 - (Math.min(Math.max(value, 0), 1) * 20);
      return `${x},${y}`;
    })
    .join(' ');
}

function getBadgeMarkup(visualState: ChannelCardState['visualState']): JSX.Element | null {
  if (!visualState) {
    return null;
  }
  if (visualState === 'off') {
    return <span className="tag tag--scene-muted">Muted</span>;
  }
  if (visualState === 'checked') {
    return <span className="tag tag--scene-checked">Checked</span>;
  }
  return <span className="tag tag--scene-pending">Ready</span>;
}

interface ChannelCardProps {
  state: ChannelCardState;
  onInteract: (channelId: number) => void;
  onToggleChecklist: (channelId: number) => void;
}

function ChannelCardComponent({
  state,
  onInteract,
  onToggleChecklist,
}: ChannelCardProps): JSX.Element {
  const {
    channel,
    metrics,
    activeAlert,
    isSelected,
    isLayoutMode,
    isShowMode,
    visualState,
    statusTone,
  } = state;
  const longPressTimerRef = useRef<number | null>(null);
  const longPressTriggeredRef = useRef(false);

  useEffect(() => () => {
    if (longPressTimerRef.current !== null) {
      window.clearTimeout(longPressTimerRef.current);
    }
  }, []);

  const clampedRmsRatio = Math.min(Math.max(metrics.rmsRatio, 0), 1);

  const clearLongPress = (): void => {
    if (longPressTimerRef.current !== null) {
      window.clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  };

  const statusLabel = activeAlert
    ? activeAlert.severity === 'critical'
      ? 'Critical'
      : 'Warning'
    : visualState === 'off'
      ? 'Muted'
      : isSelected
        ? 'Armed'
        : 'Live';

  return (
    <article
      className={[
        'channel-card',
        isSelected ? 'is-selected' : '',
        activeAlert ? `has-alert is-alert-${activeAlert.severity}` : '',
        isLayoutMode ? 'is-layout-mode' : '',
        visualState === 'off' ? 'is-show-off' : '',
        visualState === 'pending' ? 'is-show-pending' : '',
        visualState === 'checked' ? 'is-show-checked' : '',
        `is-status-${statusTone}`,
      ].filter(Boolean).join(' ')}
      data-channel-id={String(channel.id)}
      onClick={() => {
        if (isLayoutMode || longPressTriggeredRef.current) {
          longPressTriggeredRef.current = false;
          return;
        }
        onInteract(channel.id);
      }}
      onPointerDown={() => {
        if (!isShowMode) {
          return;
        }
        clearLongPress();
        longPressTriggeredRef.current = false;
        longPressTimerRef.current = window.setTimeout(() => {
          longPressTriggeredRef.current = true;
          onToggleChecklist(channel.id);
        }, LONG_PRESS_MS);
      }}
      onPointerUp={clearLongPress}
      onPointerLeave={clearLongPress}
      onPointerCancel={clearLongPress}
    >
      <header className="channel-card-header">
        <div className="channel-chip-stack">
          <span className={`channel-status-badge is-${statusTone}`}>{statusLabel}</span>
        </div>
        <div className="channel-title-group">
          <h2 className="channel-name">{channel.name}</h2>
        </div>
      </header>

      <div className="channel-meter-row" aria-label="Live signal level">
        <div className="meter meter--vertical-shell">
          <div className="meter meter--vertical">
            <div className="meter-fill" style={{ height: `${(1 - clampedRmsRatio) * 100}%` }}></div>
            <div className="meter-peak-line" style={{ bottom: `${metrics.peakRatio * 100}%` }}></div>
          </div>
          <div className="meter-scale" aria-hidden="true">
            <span>0</span>
            <span>-20</span>
            <span>-40</span>
            <span>-60</span>
          </div>
        </div>

        <div className="channel-signal-stack">
          <div className="channel-sparkline-shell" aria-hidden="true">
            <svg className="channel-sparkline" viewBox="0 0 100 24" preserveAspectRatio="none">
              <polyline points={buildSparklinePoints(metrics.historyRatios)} />
            </svg>
          </div>

          <div className="channel-meta-row">
            <div className="channel-meta-copy">
              {activeAlert ? (
                <span className={`channel-alert-badge is-${activeAlert.severity}`}>{activeAlert.kind}</span>
              ) : null}
            </div>
            {getBadgeMarkup(visualState)}
          </div>
        </div>
      </div>
    </article>
  );
}

export const ChannelCard = memo(ChannelCardComponent);
