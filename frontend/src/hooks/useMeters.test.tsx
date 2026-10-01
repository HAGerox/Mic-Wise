import { act, cleanup, renderHook } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { useMeters } from './useMeters';
import type { MeterSnapshotResponse } from '../types/api';

class MockWebSocket {
  static instances: MockWebSocket[] = [];
  onmessage: ((event: MessageEvent) => void) | null = null;
  onopen: (() => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();

  constructor() {
    MockWebSocket.instances.push(this);
  }

  sendSnapshot(peak: number): void {
    const snapshot: MeterSnapshotResponse = {
      write_head: 100,
      window_frames: 100,
      channels: [{ channel: 1, peak, rms: peak / 2 }],
    };
    this.onmessage?.({ data: JSON.stringify(snapshot) } as MessageEvent);
  }
}

describe('useMeters', () => {
  beforeEach(() => {
    MockWebSocket.instances = [];
    vi.stubGlobal('WebSocket', MockWebSocket);
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  it('does not subscribe while Setup is active', () => {
    renderHook(() => useMeters({ enabled: false }));
    expect(MockWebSocket.instances).toHaveLength(0);
  });

  it('stops updates in Setup and resumes with fresh meters when monitoring returns', () => {
    const { result, rerender } = renderHook(
      ({ enabled }) => useMeters({ enabled }),
      { initialProps: { enabled: true } },
    );
    const firstSocket = MockWebSocket.instances[0];
    act(() => firstSocket.sendSnapshot(0.25));
    expect(result.current.meterMap.get(1)?.peak).toBe(0.25);

    rerender({ enabled: false });
    expect(firstSocket.close).toHaveBeenCalledOnce();
    expect(firstSocket.onmessage).toBeNull();
    const pausedHistory = result.current.meterHistoryMap;
    act(() => firstSocket.sendSnapshot(0.9));
    expect(result.current.meterHistoryMap).toBe(pausedHistory);

    rerender({ enabled: true });
    expect(MockWebSocket.instances).toHaveLength(2);
    act(() => MockWebSocket.instances[1].sendSnapshot(0.5));
    expect(result.current.meterMap.get(1)?.peak).toBe(0.5);
  });

  it('keeps one subscription across ordinary rerenders and closes it on unmount', () => {
    const { rerender, unmount } = renderHook(() => useMeters({}));
    rerender();
    expect(MockWebSocket.instances).toHaveLength(1);
    unmount();
    expect(MockWebSocket.instances[0].close).toHaveBeenCalledOnce();
    expect(MockWebSocket.instances[0].onmessage).toBeNull();
  });
});
