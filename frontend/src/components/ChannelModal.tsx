import { formatPlaybackOffset, getChannelInitials, getInputLabel } from '../lib/format';
import { MODAL_WAVEFORM_WINDOW_SECONDS } from '../hooks/useWaveform';
import { buildWaveformRulerMarks } from '../lib/ui-logic';
import { WaveformCanvas } from './WaveformCanvas';
import type { ChannelResponse, ChannelWaveformResponse } from '../types/api';

interface ChannelModalProps {
  channel: ChannelResponse | null;
  visible: boolean;
  modalScrubSeconds: number;
  waveform: ChannelWaveformResponse | null;
  displayPoints: number[];
  onClose: () => void;
  onScrub: (replaySeconds: number) => void;
}

export function ChannelModal({
  channel,
  visible,
  modalScrubSeconds,
  waveform,
  displayPoints,
  onClose,
  onScrub,
}: ChannelModalProps): JSX.Element {
  if (!visible || !channel) {
    return (
      <section id="channel-modal" className="monitor-dock-panel is-hidden" role="dialog" aria-modal="false" aria-hidden="true"></section>
    );
  }

  const photoStyle = channel.photo_path
    ? { backgroundImage: `url(${JSON.stringify(channel.photo_path)})` }
    : undefined;
  const rulerMarks = buildWaveformRulerMarks(MODAL_WAVEFORM_WINDOW_SECONDS, 60, 15, 30);
  const replayPositionPercent = Math.min(
    96,
    Math.max(4, 100 * (1 - (modalScrubSeconds / MODAL_WAVEFORM_WINDOW_SECONDS))),
  );

  return (
    <section
      id="channel-modal"
      className="monitor-dock-panel"
      role="dialog"
      aria-modal="false"
      aria-labelledby="modal-channel-name"
      aria-hidden="false"
    >
        <button id="close-modal" className="icon-button inspector-close-button" type="button" aria-label="Close channel details" onClick={onClose}>×</button>
        <header className="modal-header">
          <div className="modal-identity">
            <div className={`modal-channel-photo ${channel.photo_path ? 'has-photo' : ''}`} style={photoStyle} aria-hidden="true">
              {!channel.photo_path ? getChannelInitials(channel) : null}
            </div>
            <div className="modal-header-copy">
              <h2 id="modal-channel-name">{channel.name}</h2>
              <p id="modal-channel-meta" className="modal-meta">{getInputLabel(channel)}</p>
            </div>
          </div>
        </header>

        <div className="inspector-layout">
          <div className="waveform-shell">
            <WaveformCanvas
              waveform={waveform}
              displayPoints={displayPoints}
              scrubSeconds={modalScrubSeconds}
              onScrub={onScrub}
            />
            <div className="waveform-scale" aria-hidden="true">
              {rulerMarks.map((mark, index) => {
                const edgeClassName = index === 0
                  ? ' is-edge-start'
                  : index === rulerMarks.length - 1
                    ? ' is-edge-end'
                    : '';

                return (
                  <span
                    key={`${mark.kind}-${mark.position}`}
                    className={`waveform-scale-mark is-${mark.kind}${edgeClassName}`}
                    style={{ left: `${mark.position * 100}%` }}
                  >
                    <span className="waveform-scale-tick"></span>
                    {mark.label ? (
                      <span className="waveform-scale-label">
                        <span className="waveform-scale-label-text">{mark.label}</span>
                      </span>
                    ) : null}
                  </span>
                );
              })}
            </div>
            {modalScrubSeconds > 0 ? (
              <output
                id="modal-replay-offset"
                className="waveform-replay-timer"
                aria-label={`${formatPlaybackOffset(modalScrubSeconds)} behind live`}
                aria-live="polite"
                style={{ left: `${replayPositionPercent}%` }}
              >
                −{formatPlaybackOffset(modalScrubSeconds)}
              </output>
            ) : null}
          </div>
        </div>
    </section>
  );
}
