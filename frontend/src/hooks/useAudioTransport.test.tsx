import { act, renderHook, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { RefObject } from 'react';

import { useAudioTransport } from './useAudioTransport';
import { createWebRtcOffer } from '../api/streaming';

vi.mock('../api/streaming', () => ({
  createWebRtcOffer: vi.fn(),
}));

class MockRtcDataChannel {
  public readonly label: string;

  public readyState: RTCDataChannelState = 'open';

  public sentMessages: string[] = [];

  private listeners = new Map<string, Set<EventListener>>();

  public constructor(label: string) {
    this.label = label;
  }

  addEventListener(type: string, listener: EventListener): void {
    const listeners = this.listeners.get(type) ?? new Set<EventListener>();
    listeners.add(listener);
    this.listeners.set(type, listeners);
  }

  removeEventListener(type: string, listener: EventListener): void {
    this.listeners.get(type)?.delete(listener);
  }

  send(message: string): void {
    this.sentMessages.push(message);
  }
}

class MockRtcPeerConnection {
  public iceGatheringState: RTCIceGatheringState = 'complete';

  public connectionState: RTCPeerConnectionState = 'new';

  public localDescription: RTCSessionDescriptionInit | null = null;

  public ontrack: ((event: RTCTrackEvent) => void) | null = null;

  public onconnectionstatechange: (() => void) | null = null;

  createDataChannel(label: string): RTCDataChannel {
    return new MockRtcDataChannel(label) as unknown as RTCDataChannel;
  }

  addTransceiver(): void {}

  async createOffer(): Promise<RTCSessionDescriptionInit> {
    return { sdp: 'mock-offer', type: 'offer' };
  }

  async setLocalDescription(description: RTCSessionDescriptionInit | null): Promise<void> {
    this.localDescription = description;
  }

  async setRemoteDescription(): Promise<void> {
    this.connectionState = 'connected';
    this.onconnectionstatechange?.();
  }

  getReceivers(): RTCRtpReceiver[] {
    return [];
  }

  close(): void {
    this.connectionState = 'closed';
  }
}

describe('useAudioTransport', () => {
  let audioElement: HTMLAudioElement;
  let controlChannel: MockRtcDataChannel | null;

  beforeEach(() => {
    controlChannel = null;
    vi.mocked(createWebRtcOffer).mockResolvedValue({
      sdp: 'mock-answer',
      type: 'answer',
    });

    vi.stubGlobal(
      'RTCPeerConnection',
      class extends MockRtcPeerConnection {
        createDataChannel(label: string): RTCDataChannel {
          controlChannel = new MockRtcDataChannel(label);
          return controlChannel as unknown as RTCDataChannel;
        }
      } as unknown as typeof RTCPeerConnection,
    );

    audioElement = document.createElement('audio');
    audioElement.volume = 0.4;
    Object.defineProperty(audioElement, 'play', {
      configurable: true,
      value: vi.fn().mockResolvedValue(undefined),
    });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
    vi.clearAllMocks();
  });

  it('keeps browser volume unchanged while syncing selection updates', async () => {
    const audioElementRef = { current: audioElement } as RefObject<HTMLAudioElement>;
    const { result, unmount } = renderHook(() => useAudioTransport({ audioElementRef }));

    await waitFor(() => {
      expect(createWebRtcOffer).toHaveBeenCalledTimes(1);
    });

    await act(async () => {
      await result.current.syncSelection({ inputSources: [[2, -3]], replaySeconds: 0.5 });
    });

    expect(audioElement.volume).toBe(0.4);
    expect(audioElement.play).toHaveBeenCalledTimes(1);
    expect(controlChannel?.sentMessages).toEqual([
      JSON.stringify({ input_sources: [[2, -3]], replay_seconds: 0.5 }),
    ]);

    unmount();
  });
});