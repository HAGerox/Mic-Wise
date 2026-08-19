import { memo, useEffect, useRef } from 'react';

import { formatDbfs, getChannelInitials, getInputLabel } from '../lib/format';
import { buildEnergyLinePath } from '../lib/ui-logic';
import type { ChannelCardState } from '../types/ui';

const LONG_PRESS_MS = 420;

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
        ? 'Listening'
        : 'Live';
  const channelIdentity = `CH ${channel.number.toString().padStart(2, '0')}`;
  const energyPath = buildEnergyLinePath(metrics.historyRatios);
  const photoStyle = channel.photo_path
    ? { backgroundImage: `url(${JSON.stringify(channel.photo_path)})` }
    : undefined;

  const handleInteraction = (): void => {
    if (isLayoutMode || longPressTriggeredRef.current) {
      longPressTriggeredRef.current = false;
      return;
    }
    onInteract(channel.id);
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
        `is-status-${statusTone}`,
      ].filter(Boolean).join(' ')}
      data-channel-id={String(channel.id)}
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
      <button
        type="button"
        className="channel-card-listen-target"
        disabled={isLayoutMode}
        aria-pressed={isSelected}
        aria-label={`${channelIdentity} ${channel.name}, ${statusLabel}, peak ${formatDbfs(metrics.peakDbfs)} dBFS`}
        onClick={handleInteraction}
      />
      <div className="channel-card-visual">
        <div className={`channel-photo-layer ${channel.photo_path ? 'has-photo' : ''}`} style={photoStyle}>
          {!channel.photo_path ? <span>{getChannelInitials(channel)}</span> : null}
        </div>
        <div className="channel-photo-shade"></div>

        <div className="channel-signal-shell" aria-hidden="true">
          <svg className="channel-signal-trace" viewBox="0 0 100 24" preserveAspectRatio="none">
            <path d={energyPath} vectorEffect="non-scaling-stroke" />
          </svg>
        </div>

        <footer className="channel-nameplate">
          <div className="channel-title-group">
            <h2 className="channel-name">{channel.name}</h2>
            <span className="channel-secondary">{getInputLabel(channel)}</span>
          </div>
          {activeAlert ? (
            <div className="channel-meta-row">
              <span className={`channel-alert-badge is-${activeAlert.severity}`}>{activeAlert.kind}</span>
            </div>
          ) : visualState ? (
            <div className="channel-meta-row">
              {visualState === 'off' ? (
                <span className="tag tag--scene-muted">Muted</span>
              ) : (
                <button
                  type="button"
                  className={`tag channel-check-action ${visualState === 'checked' ? 'tag--scene-checked' : 'tag--scene-pending'}`}
                  aria-pressed={visualState === 'checked'}
                  aria-label={`${visualState === 'checked' ? 'Mark unchecked' : 'Mark checked'}: ${channel.name}`}
                  onPointerDown={(event) => {
                    event.stopPropagation();
                    clearLongPress();
                  }}
                  onClick={(event) => {
                    event.stopPropagation();
                    onToggleChecklist(channel.id);
                  }}
                >
                  {visualState === 'checked' ? 'Checked' : 'Check'}
                </button>
              )}
            </div>
          ) : null}
        </footer>
      </div>
    </article>
  );
}

export const ChannelCard = memo(ChannelCardComponent);
