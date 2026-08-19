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

function renderModal(overrides: Partial<Parameters<typeof ChannelModal>[0]> = {}) {
  const onScrub = vi.fn();
  return render(
    <ChannelModal
      channel={channel}
      visible={true}
      modalScrubSeconds={0}
      waveform={null}
      displayPoints={[]}
      onClose={vi.fn()}
      onScrub={onScrub}
      {...overrides}
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

describe('ChannelModal inspector', () => {
  it('shows a channel identity image when one is configured', () => {
    const photoChannel = { ...channel, photo_path: 'https://example.com/vocal-1.jpg' };
    const { container } = render(
      <ChannelModal
        channel={photoChannel}
        visible={true}
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

  it('puts the input directly under the channel name without redundant status copy', () => {
    renderModal();

    expect(screen.getByRole('heading', { name: 'Vocal 1' })).toBeInTheDocument();
    expect(screen.getByText('Input 1')).toHaveClass('modal-meta');
    expect(screen.queryByText('CH 01')).not.toBeInTheDocument();
    expect(screen.queryByText(/Rolling capture/)).not.toBeInTheDocument();
    expect(screen.queryByText(/total trim/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Transport/)).not.toBeInTheDocument();
  });

  it('shows only a replay offset timer when listening behind live', () => {
    renderModal({ modalScrubSeconds: 83 });

    const timer = screen.getByText('−1:23');
    expect(timer).toHaveTextContent('−1:23');
    expect(timer.tagName).toBe('OUTPUT');
    expect(screen.queryByText('5 min rolling peak history')).not.toBeInTheDocument();
    expect(screen.getByText('5:00')).toBeInTheDocument();
    expect(screen.getByText('Live')).toBeInTheDocument();
  });

  it('keeps the history ruler but does not show a transport timer at the live edge', () => {
    renderModal();

    expect(screen.getByText('5:00')).toBeInTheDocument();
    expect(screen.getByText('Live')).toBeInTheDocument();
    expect(screen.queryByText(/−\d/)).not.toBeInTheDocument();
  });
});
