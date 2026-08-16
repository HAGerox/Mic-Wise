import { render, screen } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ChannelModal } from './ChannelModal';
import type { ChannelResponse } from '../types/api';

const channel: ChannelResponse = {
  id: 1,
  number: 1,
  name: 'Vocal 1',
  photo_path: null,
  input_index: 0,
  gain_db: 0,
  is_record_enabled: true,
  sort_index: 0,
  position_x: 0,
  position_y: 0,
};

function renderModal() {
  return render(
    <ChannelModal
      channel={channel}
      visible={true}
      combinedGainDb={0}
      transportStatusText="ready"
      modalScrubSeconds={0}
      waveform={null}
      displayPoints={[]}
      onClose={vi.fn()}
      onScrub={vi.fn()}
    />,
  );
}

const canvasContext = {
  beginPath: vi.fn(),
  clearRect: vi.fn(),
  fill: vi.fn(),
  fillRect: vi.fn(),
  lineTo: vi.fn(),
  moveTo: vi.fn(),
  setLineDash: vi.fn(),
  setTransform: vi.fn(),
  stroke: vi.fn(),
  closePath: vi.fn(),
  fillStyle: '',
  globalCompositeOperation: 'source-over',
  lineWidth: 1,
  strokeStyle: '',
} as unknown as CanvasRenderingContext2D;

beforeEach(() => {
  vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(canvasContext);
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ChannelModal waveform ruler', () => {
  it('shows a channel identity image when one is configured', () => {
    const photoChannel = { ...channel, photo_path: 'https://example.com/vocal-1.jpg' };
    const { container } = render(
      <ChannelModal
        channel={photoChannel}
        visible={true}
        combinedGainDb={0}
        transportStatusText="Live"
        modalScrubSeconds={0}
        waveform={null}
        displayPoints={[]}
        onClose={vi.fn()}
        onScrub={vi.fn()}
      />,
    );

    expect(container.querySelector('.modal-channel-photo')).toHaveClass('has-photo');
    expect(container.querySelector('.modal-channel-photo')).toHaveStyle({
      backgroundImage: 'url("https://example.com/vocal-1.jpg")',
    });
  });

  it('shows the channel number inline before a custom channel name', () => {
    renderModal();

    const heading = screen.getByRole('heading', { name: 'CH 01 Vocal 1' });
    const channelNumber = screen.getByText('CH 01');

    expect(heading).toContainElement(channelNumber);
    expect(channelNumber).toHaveClass('modal-kicker');
  });

  it('uses minute-based history copy and pins edge labels inside the scale', () => {
    const { container } = renderModal();

    expect(screen.getByText('5 min rolling peak history')).toBeInTheDocument();
    expect(screen.queryByText('300 s rolling peak history')).not.toBeInTheDocument();

    const startMark = screen.getByText('5:00').closest('.waveform-scale-mark');
    const liveMark = screen.getAllByText('Live')[1].closest('.waveform-scale-mark');

    expect(startMark).toHaveClass('is-edge-start');
    expect(startMark).toHaveClass('is-major');
    expect(liveMark).toHaveClass('is-edge-end');
    expect(liveMark).toHaveClass('is-live');
    expect(container.querySelectorAll('.waveform-scale-mark.is-edge-start')).toHaveLength(1);
    expect(container.querySelectorAll('.waveform-scale-mark.is-edge-end')).toHaveLength(1);
  });
});
