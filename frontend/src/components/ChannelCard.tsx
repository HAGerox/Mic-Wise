import { memo, useEffect, useRef } from 'react';

import { getInputLabel, isDefaultChannelName } from '../lib/format';
import type { AudioAlertResponse, ChannelResponse } from '../types/api';
import type { ShowChannelVisualState } from '../types/ui';

const LONG_PRESS_MS = 420;

function buildSparklinePoints(history: number[]): string {
  const safeHistory = history.length > 0 ? history : [0, 0, 0, 0];
  return safeHistory
    .map((value, index) => {
      const x = safeHistory.length === 1 ? 50 : (index / (safeHistory.length - 1)) * 100;
      const y = 22 - (Math.min(Math.max(value, 0), 1) * 18);
      return `${x},${y}`;
    })
    .join(' ');
}

function getBadgeMarkup(visualState: ShowChannelVisualState | null): JSX.Element | null {
  if (!visualState) {
    return null;
  }
  if (visualState === 'off') {
    return <span className="tag tag--scene-muted">Out</span>;
  }
  if (visualState === 'checked') {
    return <span className="tag tag--scene-checked">Checked</span>;
  }
  return <span className="tag tag--scene-pending">Pending</span>;
}

interface ChannelCardProps {
  channel: ChannelResponse;
  level: number;
  rmsHistory: number[];
  activeAlert: AudioAlertResponse | null;
  isSelected: boolean;
  isLayoutMode: boolean;
  isShowMode: boolean;
  visualState: ShowChannelVisualState | null;
  onInteract: (channelId: number) => void;
  onToggleChecklist: (channelId: number) => void;
}

function ChannelCardComponent({
  channel,
  level,
  rmsHistory,
  activeAlert,
  isSelected,
  isLayoutMode,
  isShowMode,
  visualState,
  onInteract,
  onToggleChecklist,
}: ChannelCardProps): JSX.Element {
  const longPressTimerRef = useRef<number | null>(null);
  const longPressTriggeredRef = useRef(false);

  useEffect(() => () => {
    if (longPressTimerRef.current !== null) {
      window.clearTimeout(longPressTimerRef.current);
    }
  }, []);

  const repeatedName = isDefaultChannelName(channel);

  const clearLongPress = (): void => {
    if (longPressTimerRef.current !== null) {
      window.clearTimeout(longPressTimerRef.current);
      longPressTimerRef.current = null;
    }
  };

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
      <header>
        <div className="channel-title-group">
          {repeatedName ? (
            <h2 className="channel-name">CH {channel.number}</h2>
          ) : (
            <>
              <div className="channel-number">CH {channel.number}</div>
              <h2 className="channel-name">{channel.name}</h2>
            </>
          )}
        </div>
        <span className="channel-chip">{getInputLabel(channel)}</span>
      </header>
      <div className="channel-sparkline-shell" aria-hidden="true">
        <svg className="channel-sparkline" viewBox="0 0 100 24" preserveAspectRatio="none">
          <polyline points={buildSparklinePoints(rmsHistory)} />
        </svg>
      </div>
      <div className="meter"><div className="meter-mask" style={{ width: `${Math.max(0, 100 - level)}%` }}></div></div>
      <div className="channel-meta-row">
        <div className="channel-meta-copy">
          <span className="channel-actions">{isLayoutMode ? 'Hold and move' : 'Tap to listen'}</span>
          {activeAlert ? (
            <span className={`channel-alert-badge is-${activeAlert.severity}`}>{activeAlert.kind}</span>
          ) : null}
        </div>
        {getBadgeMarkup(visualState)}
      </div>
    </article>
  );
}

export const ChannelCard = memo(ChannelCardComponent);
