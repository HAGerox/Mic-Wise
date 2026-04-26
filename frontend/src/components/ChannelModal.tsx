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
  const channelIdentity = `CH ${channel.number.toString().padStart(2, '0')}`;

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
        <button id="close-modal" className="icon-button inspector-close-button" type="button" aria-label="Close channel details" onClick={onClose}>×</button>
        <header className="modal-header">
          <div className="modal-header-copy">
            <p id="modal-channel-number" className="modal-kicker">{repeatedName ? '' : channelIdentity}</p>
            <h2 id="modal-channel-name">{repeatedName ? channelIdentity : channel.name}</h2>
            <p id="modal-channel-meta" className="modal-meta">
              {channel.is_record_enabled ? 'Rolling capture armed' : 'Rolling capture off'}
            </p>
          </div>
          <div className="modal-badges">
            <span id="modal-patch-badge" className="info-badge">{getInputLabel(channel)}</span>
            <span id="modal-record-badge" className="info-badge">{formatGainDb(combinedGainDb)} total trim</span>
            <span id="modal-transport-status" className="info-badge">Transport {transportStatusText}</span>
          </div>
        </header>

        <div className="inspector-layout">
          <div className="waveform-shell">
            <div className="waveform-header-row">
              <div>
                <strong id="modal-scrub-label">{modalScrubLabel}</strong>
              </div>
              <span className="waveform-meta-note">300 s rolling peak history</span>
            </div>

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
          </div>
        </div>
      </section>
    </>
  );
}
