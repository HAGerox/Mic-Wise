import { memo, useEffect, useRef } from 'react';

import { getInputLabel, isDefaultChannelName } from '../lib/format';
import type { ChannelResponse } from '../types/api';
import type { ShowChannelVisualState } from '../types/ui';

const LONG_PRESS_MS = 420;

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
      <div className="meter"><div className="meter-mask" style={{ width: `${Math.max(0, 100 - level)}%` }}></div></div>
      <div className="channel-meta-row">
        <span className="channel-actions">{isLayoutMode ? 'Hold and move' : 'Tap to listen'}</span>
        {getBadgeMarkup(visualState)}
      </div>
    </article>
  );
}

export const ChannelCard = memo(ChannelCardComponent);
