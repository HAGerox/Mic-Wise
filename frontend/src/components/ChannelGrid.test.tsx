import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ChannelGrid } from './ChannelGrid';
import type { ChannelResponse } from '../types/api';

const sortableMock = vi.hoisted(() => ({
  options: null as {
    handle?: string;
    disabled?: boolean;
    animation?: number;
    easing?: string;
    fallbackOnBody?: boolean;
    fallbackTolerance?: number;
    swapThreshold?: number;
    invertedSwapThreshold?: number;
    onChoose?: () => void;
    onUnchoose?: () => void;
    onStart?: () => void;
    onEnd?: () => Promise<void>;
  } | null,
  instance: {
    option: vi.fn(),
    destroy: vi.fn(),
    toArray: vi.fn(),
  },
}));

vi.mock('sortablejs', () => ({
  default: {
    create: vi.fn((_element: HTMLElement, options: typeof sortableMock.options) => {
      sortableMock.options = options;
      return sortableMock.instance;
    }),
  },
}));

function buildChannel(id: number, sortIndex: number): ChannelResponse {
  return {
    id,
    number: id,
    name: `Channel ${id}`,
    photo_path: null,
    input_index: null,
    gain_db: 0,
    is_record_enabled: true,
    sort_index: sortIndex,
    position_x: 0,
    position_y: 0,
  };
}

function renderGrid(channels: ChannelResponse[], overrides: Partial<Parameters<typeof ChannelGrid>[0]> = {}) {
  const props: Parameters<typeof ChannelGrid>[0] = {
    channels,
    meterMap: new Map(),
    meterHistoryMap: new Map(),
    activeAlertsByChannelId: new Map(),
    selectedChannelIds: new Set(),
    activeView: 'monitor',
    activeScene: null,
    checklist: new Set(),
    masterGainDb: 0,
    onInteractChannel: vi.fn(),
    onToggleChecklist: vi.fn(),
    onPersistOrder: vi.fn().mockResolvedValue(undefined),
    onCloseModal: vi.fn(),
    ...overrides,
  };

  return render(<ChannelGrid {...props} />);
}

afterEach(() => {
  sortableMock.options = null;
  sortableMock.instance.option.mockClear();
  sortableMock.instance.destroy.mockClear();
  sortableMock.instance.toArray.mockReset();
  vi.clearAllMocks();
});

describe('ChannelGrid layout ordering', () => {
  it('uses one image-backed signal trace instead of a redundant loudness meter', () => {
    const channel = { ...buildChannel(1, 0), photo_path: 'https://example.com/performer.jpg' };
    const { container } = renderGrid([channel]);

    const card = screen.getByRole('button', { name: /CH 01 Channel 1, Live/ });
    const photoLayer = container.querySelector('.channel-photo-layer');

    expect(card).toBeInTheDocument();
    expect(container.querySelector('.channel-signal-trace path')).not.toHaveAttribute('fill');
    expect(container.querySelector('.meter--vertical')).not.toBeInTheDocument();
    expect(screen.queryByText('CH 01')).not.toBeInTheDocument();
    expect(screen.queryByText('Live')).not.toBeInTheDocument();
    expect(screen.queryByText(/dBFS/)).not.toBeInTheDocument();
    expect(photoLayer).toHaveClass('has-photo');
    expect(photoLayer).toHaveStyle({ backgroundImage: 'url("https://example.com/performer.jpg")' });
  });

  it('persists dropped strip order with the latest callback after channels load', async () => {
    const initialPersistOrder = vi.fn().mockResolvedValue(undefined);
    const latestPersistOrder = vi.fn().mockResolvedValue(undefined);
    const { rerender } = renderGrid([], { onPersistOrder: initialPersistOrder });

    rerender(
      <ChannelGrid
        channels={[buildChannel(1, 0), buildChannel(2, 1), buildChannel(3, 2)]}
        meterMap={new Map()}
        meterHistoryMap={new Map()}
        activeAlertsByChannelId={new Map()}
        selectedChannelIds={new Set()}
        activeView="monitor"
        activeScene={null}
        checklist={new Set()}
        masterGainDb={0}
        onInteractChannel={vi.fn()}
        onToggleChecklist={vi.fn()}
        onPersistOrder={latestPersistOrder}
        onCloseModal={vi.fn()}
      />,
    );

    expect(screen.getByText('Channel 1')).toBeInTheDocument();
    expect(screen.getByText('Channel 2')).toBeInTheDocument();
    expect(screen.getByText('Channel 3')).toBeInTheDocument();

    sortableMock.instance.toArray.mockReturnValue(['1', '3', '2']);
    await sortableMock.options?.onEnd?.();

    expect(initialPersistOrder).not.toHaveBeenCalled();
    expect(latestPersistOrder).toHaveBeenCalledWith([1, 3, 2]);
  });

  it('closes the modal with the latest callback when dragging starts', () => {
    const initialCloseModal = vi.fn();
    const latestCloseModal = vi.fn();
    const { rerender } = renderGrid([buildChannel(1, 0)], { onCloseModal: initialCloseModal });

    rerender(
      <ChannelGrid
        channels={[buildChannel(1, 0)]}
        meterMap={new Map()}
        meterHistoryMap={new Map()}
        activeAlertsByChannelId={new Map()}
        selectedChannelIds={new Set()}
        activeView="monitor"
        activeScene={null}
        checklist={new Set()}
        masterGainDb={0}
        onInteractChannel={vi.fn()}
        onToggleChecklist={vi.fn()}
        onPersistOrder={vi.fn().mockResolvedValue(undefined)}
        onCloseModal={latestCloseModal}
      />,
    );

    sortableMock.options?.onStart?.();

    expect(initialCloseModal).not.toHaveBeenCalled();
    expect(latestCloseModal).toHaveBeenCalledTimes(1);
  });

  it('uses an always-available handle instead of a reorder mode', () => {
    const { container } = renderGrid([buildChannel(1, 0)]);

    expect(sortableMock.options?.handle).toBe('.channel-reorder-handle');
    expect(sortableMock.options?.disabled).toBe(false);
    expect(sortableMock.options?.animation).toBe(180);
    expect(sortableMock.options?.easing).toBe('cubic-bezier(0.22, 1, 0.36, 1)');
    expect(sortableMock.options?.fallbackOnBody).toBe(true);
    expect(sortableMock.options?.fallbackTolerance).toBe(4);
    expect(sortableMock.options?.swapThreshold).toBe(0.72);
    expect(sortableMock.options?.invertedSwapThreshold).toBe(0.78);
    expect(container.querySelector('.channel-reorder-handle')).toBeInTheDocument();
  });

  it('disables full-card pointer targets while Sortable is hit-testing insertions', () => {
    const { container } = renderGrid([buildChannel(1, 0), buildChannel(2, 1)]);
    const grid = container.querySelector('#channel-grid') as HTMLElement;

    sortableMock.options?.onChoose?.();
    expect(grid).toHaveClass('is-reordering');

    sortableMock.options?.onUnchoose?.();
    expect(grid).not.toHaveClass('is-reordering');
  });

  it('offers a visible show checklist action without starting a listen', async () => {
    const user = userEvent.setup();
    const onInteractChannel = vi.fn();
    const onToggleChecklist = vi.fn();
    const channel = buildChannel(1, 0);

    renderGrid([channel], {
      activeView: 'show',
      activeScene: {
        id: 4,
        name: 'Scene 4',
        order_index: 3,
        sync_osc_address: null,
        sync_osc_argument: null,
        sync_midi_pattern: null,
        channel_assignments: [{ channel_id: channel.id, state: 'ready' }],
      },
      onInteractChannel,
      onToggleChecklist,
    });

    await user.click(screen.getByRole('button', { name: 'Mark checked: Channel 1' }));

    expect(onToggleChecklist).toHaveBeenCalledWith(channel.id);
    expect(onInteractChannel).not.toHaveBeenCalled();
  });
});
