import { formatGainDb, formatPlaybackOffset, getInputLabel, isDefaultChannelName } from '../lib/format';
import { buildWaveformRulerMarks } from '../lib/ui-logic';
import { WaveformCanvas } from './WaveformCanvas';
import type { ChannelResponse, ChannelWaveformResponse } from '../types/api';

interface ChannelModalProps {
  channel: ChannelResponse | null;
  visible: boolean;
  combinedGainDb: number;
  transportStatusText: string;
  modalScrubSeconds: number;
  waveform: ChannelWaveformResponse | null;
  displayPoints: number[];
  onClose: () => void;
  onScrub: (replaySeconds: number) => void;
}

export function ChannelModal({
  channel,
  visible,
  combinedGainDb,
  transportStatusText,
  modalScrubSeconds,
  waveform,
  displayPoints,
  onClose,
  onScrub,
}: ChannelModalProps): JSX.Element {
  if (!visible || !channel) {
    return (
      <>
        <div id="channel-modal-empty" className="monitor-dock-empty">
          <strong>Channel inspector</strong>
          <span>Select a channel to listen, inspect recent history, or scrub back from live.</span>
        </div>
        <section id="channel-modal" className="monitor-dock-panel is-hidden" role="dialog" aria-modal="false" aria-hidden="true"></section>
      </>
    );
  }

  const repeatedName = isDefaultChannelName(channel);
  const modalScrubLabel = modalScrubSeconds > 0 ? `Replay ${formatPlaybackOffset(modalScrubSeconds)}` : 'Live';
  const rulerMarks = buildWaveformRulerMarks(300, 60, 15, 30);

  return (
    <>
      <div id="channel-modal-empty" className="monitor-dock-empty is-hidden">
        <strong>Channel inspector</strong>
        <span>Select a channel to listen, inspect recent history, or scrub back from live.</span>
      </div>
      <section
        id="channel-modal"
        className="monitor-dock-panel"
        role="dialog"
        aria-modal="false"
        aria-labelledby="modal-channel-name"
        aria-hidden="false"
      >
        <button id="close-modal" className="icon-button" type="button" aria-label="Close channel details" onClick={onClose}>×</button>
        <header className="modal-header">
          <div>
            <p id="modal-channel-number" className="modal-kicker">{repeatedName ? '' : `CH ${channel.number}`}</p>
            <h2 id="modal-channel-name">{repeatedName ? `CH ${channel.number}` : channel.name}</h2>
            <p id="modal-channel-meta" className="modal-meta">
              {channel.is_record_enabled ? 'Rolling record on' : 'Rolling record off'}
            </p>
          </div>
          <div className="modal-badges">
            <span id="modal-patch-badge" className="info-badge">{getInputLabel(channel)}</span>
            <span id="modal-record-badge" className="info-badge">{formatGainDb(combinedGainDb)} trim</span>
            <span id="modal-transport-status" className="info-badge">{transportStatusText}</span>
          </div>
        </header>

        <div className="waveform-shell">
          <WaveformCanvas
            waveform={waveform}
            displayPoints={displayPoints}
            scrubSeconds={modalScrubSeconds}
            onScrub={onScrub}
          />
          <div className="waveform-scale" aria-hidden="true">
            {rulerMarks.map((mark) => (
              <span
                key={`${mark.kind}-${mark.position}`}
                className={`waveform-scale-mark is-${mark.kind}`}
                style={{ left: `${mark.position * 100}%` }}
              >
                <span className="waveform-scale-tick"></span>
                {mark.label ? <span className="waveform-scale-label">{mark.label}</span> : null}
              </span>
            ))}
          </div>
          <div className="waveform-footer">
            <div className="waveform-footer-text">
              <strong id="modal-scrub-label">{modalScrubLabel}</strong>
              <span>Click the graph or ruler to scrub. Tap near Live to snap back.</span>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
