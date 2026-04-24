import { formatGainDb, formatPlaybackOffset, getInputLabel, isDefaultChannelName } from '../lib/format';
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
          <span>Select a channel to hear it live or scrub back through the last five minutes.</span>
        </div>
        <section id="channel-modal" className="monitor-dock-panel is-hidden" role="dialog" aria-modal="false" aria-hidden="true"></section>
      </>
    );
  }

  const repeatedName = isDefaultChannelName(channel);
  const modalScrubLabel = modalScrubSeconds > 0
    ? `${formatPlaybackOffset(modalScrubSeconds)} behind live`
    : 'Click anywhere on the graph to scrub — click near Live to snap back';

  return (
    <>
      <div id="channel-modal-empty" className="monitor-dock-empty is-hidden">
        <strong>Channel inspector</strong>
        <span>Select a channel to hear it live or scrub back through the last five minutes.</span>
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
              {getInputLabel(channel)} • {channel.is_record_enabled ? 'Rolling record on' : 'Rolling record off'}
            </p>
            <p id="modal-transport-status" className="modal-transport-status">{transportStatusText}</p>
          </div>
          <div className="modal-badges">
            <span id="modal-patch-badge" className="info-badge">{getInputLabel(channel)}</span>
            <span id="modal-record-badge" className="info-badge">{formatGainDb(combinedGainDb)} trim</span>
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
            <span>5:00</span>
            <span>4:00</span>
            <span>3:00</span>
            <span>2:00</span>
            <span>1:00</span>
            <span>Live</span>
          </div>
          <div className="waveform-footer">
            <div className="waveform-footer-text">
              <span>Last 5 minutes</span>
              <strong id="modal-scrub-label">{modalScrubLabel}</strong>
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
