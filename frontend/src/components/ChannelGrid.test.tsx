import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ChannelGrid } from './ChannelGrid';
import type { ChannelResponse } from '../types/api';

const sortableMock = vi.hoisted(() => ({
  options: null as {
    onStart?: () => void;
    onEnd?: (event: { to: HTMLElement }) => Promise<void>;
  } | null,
  instance: {
    option: vi.fn(),
    destroy: vi.fn(),
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
    layoutMode: true,
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
  vi.clearAllMocks();
});

describe('ChannelGrid layout ordering', () => {
  it('persists dropped strip order with the latest callback after channels load', async () => {
    const initialPersistOrder = vi.fn().mockResolvedValue(undefined);
    const latestPersistOrder = vi.fn().mockResolvedValue(undefined);
    const { container, rerender } = renderGrid([], { onPersistOrder: initialPersistOrder });

    rerender(
      <ChannelGrid
        channels={[buildChannel(1, 0), buildChannel(2, 1)]}
        meterMap={new Map()}
        meterHistoryMap={new Map()}
        activeAlertsByChannelId={new Map()}
        selectedChannelIds={new Set()}
        activeView="monitor"
        layoutMode={true}
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

    await sortableMock.options?.onEnd?.({ to: container.querySelector('#channel-grid') as HTMLElement });

    expect(initialPersistOrder).not.toHaveBeenCalled();
    expect(latestPersistOrder).toHaveBeenCalledWith([1, 2]);
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
        layoutMode={true}
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
});
