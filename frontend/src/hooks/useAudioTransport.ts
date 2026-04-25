import { useCallback, useEffect, useRef } from 'react';
import type { RefObject } from 'react';

import { createWebRtcOffer } from '../api/streaming';
import type { AudioInputSource } from '../types/ui';

const AUDIO_CONTROL_CHANNEL_LABEL = 'micwise-control';
const AUDIO_ELEMENT_FADE_SECONDS = 0.012;

type PendingAudioCommand = {
  input_sources: AudioInputSource[];
  replay_seconds: number;
};

async function waitForIceGatheringComplete(
  peerConnection: RTCPeerConnection,
  timeoutMs = 250,
): Promise<void> {
  if (peerConnection.iceGatheringState === 'complete') {
    return;
  }

  await new Promise<void>((resolve) => {
    const timeoutId = window.setTimeout(() => {
      peerConnection.removeEventListener('icegatheringstatechange', handleChange);
      resolve();
    }, timeoutMs);

    function handleChange(): void {
      if (peerConnection.iceGatheringState !== 'complete') {
        return;
      }

      window.clearTimeout(timeoutId);
      peerConnection.removeEventListener('icegatheringstatechange', handleChange);
      resolve();
    }

    peerConnection.addEventListener('icegatheringstatechange', handleChange);
  });
}

async function waitForDataChannelOpen(channel: RTCDataChannel | null, timeoutMs = 900): Promise<void> {
  if (!channel || channel.readyState === 'open') {
    return;
  }

  const safeChannel = channel;

  await new Promise<void>((resolve, reject) => {
    const timeoutId = window.setTimeout(() => {
      safeChannel.removeEventListener('open', handleOpen);
      reject(new Error('Audio control channel timed out'));
    }, timeoutMs);

    function handleOpen(): void {
      window.clearTimeout(timeoutId);
      safeChannel.removeEventListener('open', handleOpen);
      resolve();
    }

    safeChannel.addEventListener('open', handleOpen, { once: true });
  });
}

interface UseAudioTransportOptions {
  audioElementRef: RefObject<HTMLAudioElement>;
  onStatusChange?: (statusText: string) => void;
}

interface SyncSelectionPayload {
  inputSources: AudioInputSource[];
  replaySeconds?: number;
}

export function useAudioTransport({
  audioElementRef,
  onStatusChange,
}: UseAudioTransportOptions): {
  syncSelection: (payload: SyncSelectionPayload) => Promise<void>;
  closeAudioTransport: (options?: { preserveStatus?: boolean }) => Promise<void>;
} {
  const peerConnectionRef = useRef<RTCPeerConnection | null>(null);
  const audioControlChannelRef = useRef<RTCDataChannel | null>(null);
  const audioTransportPromiseRef = useRef<Promise<RTCPeerConnection> | null>(null);
  const pendingAudioCommandRef = useRef<PendingAudioCommand | null>(null);
  const listenRequestTokenRef = useRef(0);
  const statusChangeRef = useRef(onStatusChange);
  const fadeTimeoutRef = useRef<number | null>(null);

  useEffect(() => {
    statusChangeRef.current = onStatusChange;
  }, [onStatusChange]);

  const emitStatus = useCallback((statusText: string) => {
    statusChangeRef.current?.(statusText);
  }, []);

  const clearPendingFade = useCallback(() => {
    if (fadeTimeoutRef.current !== null) {
      window.clearTimeout(fadeTimeoutRef.current);
      fadeTimeoutRef.current = null;
    }
  }, []);

  const primeAudioElementGain = useCallback(() => {
    const audioElement = audioElementRef.current;
    if (!audioElement) {
      return;
    }

    clearPendingFade();
    audioElement.volume = 0;
    fadeTimeoutRef.current = window.setTimeout(() => {
      audioElement.volume = 1;
      fadeTimeoutRef.current = null;
    }, AUDIO_ELEMENT_FADE_SECONDS * 1000);
  }, [audioElementRef, clearPendingFade]);

  const flushPendingAudioCommand = useCallback(() => {
    if (!pendingAudioCommandRef.current || audioControlChannelRef.current?.readyState !== 'open') {
      return;
    }

    audioControlChannelRef.current.send(JSON.stringify(pendingAudioCommandRef.current));
    pendingAudioCommandRef.current = null;
  }, []);

  const closeAudioTransport = useCallback(
    async ({ preserveStatus = false }: { preserveStatus?: boolean } = {}) => {
      const peerConnection = peerConnectionRef.current;
      peerConnectionRef.current = null;
      audioControlChannelRef.current = null;
      audioTransportPromiseRef.current = null;
      pendingAudioCommandRef.current = null;

      if (peerConnection) {
        peerConnection.ontrack = null;
        peerConnection.onconnectionstatechange = null;
        peerConnection.getReceivers().forEach((receiver) => receiver.track?.stop());
        peerConnection.close();
      }

      if (audioElementRef.current) {
        clearPendingFade();
        audioElementRef.current.volume = 1;
        audioElementRef.current.srcObject = null;
      }

      if (!preserveStatus) {
        emitStatus('Online');
      }
    },
    [audioElementRef, clearPendingFade, emitStatus],
  );

  const ensureAudioTransport = useCallback(async (): Promise<RTCPeerConnection> => {
    if (peerConnectionRef.current && audioControlChannelRef.current?.readyState === 'open') {
      return peerConnectionRef.current;
    }

    if (audioTransportPromiseRef.current) {
      return audioTransportPromiseRef.current;
    }

    const transportPromise = (async () => {
      const peerConnection = new RTCPeerConnection({ iceServers: [] });
      const controlChannel = peerConnection.createDataChannel(AUDIO_CONTROL_CHANNEL_LABEL, { ordered: true });

      peerConnectionRef.current = peerConnection;
      audioControlChannelRef.current = controlChannel;

      peerConnection.addTransceiver('audio', { direction: 'recvonly' });
      peerConnection.ontrack = (event) => {
        if (peerConnection !== peerConnectionRef.current) {
          return;
        }

        const [stream] = event.streams;
        if (audioElementRef.current) {
          audioElementRef.current.srcObject = stream ?? new MediaStream([event.track]);
        }
      };
      peerConnection.onconnectionstatechange = () => {
        if (peerConnection !== peerConnectionRef.current) {
          return;
        }

        if (peerConnection.connectionState === 'failed' || peerConnection.connectionState === 'closed') {
          void closeAudioTransport({ preserveStatus: true });
          emitStatus('Audio link unavailable');
          return;
        }
        if (peerConnection.connectionState === 'connected') {
          emitStatus('Online');
        }
      };

      controlChannel.addEventListener('open', flushPendingAudioCommand);

      const offer = await peerConnection.createOffer();
      await peerConnection.setLocalDescription(offer);
      await waitForIceGatheringComplete(peerConnection, 180);

      const localDescription = peerConnection.localDescription;
      if (!localDescription) {
        throw new Error('Local WebRTC offer was not created');
      }

      const answer = await createWebRtcOffer({
        sdp: localDescription.sdp,
        type: localDescription.type,
        channel_ids: [],
        replay_seconds: 0,
      });

      await peerConnection.setRemoteDescription({
        sdp: answer.sdp,
        type: answer.type as RTCSdpType,
      });
      await waitForDataChannelOpen(controlChannel);
      flushPendingAudioCommand();
      return peerConnection;
    })();

    audioTransportPromiseRef.current = transportPromise;

    try {
      return await transportPromise;
    } catch (error) {
      await closeAudioTransport({ preserveStatus: true });
      throw error;
    } finally {
      if (audioTransportPromiseRef.current === transportPromise) {
        audioTransportPromiseRef.current = null;
      }
    }
  }, [audioElementRef, closeAudioTransport, emitStatus, flushPendingAudioCommand]);

  const sendSelection = useCallback(
    async ({ inputSources, replaySeconds = 0 }: SyncSelectionPayload): Promise<void> => {
      pendingAudioCommandRef.current = {
        input_sources: inputSources,
        replay_seconds: replaySeconds,
      };

      if (!peerConnectionRef.current && !audioTransportPromiseRef.current && inputSources.length === 0) {
        return;
      }

      await ensureAudioTransport();
      await waitForDataChannelOpen(audioControlChannelRef.current);
      flushPendingAudioCommand();
    },
    [ensureAudioTransport, flushPendingAudioCommand],
  );

  const syncSelection = useCallback(
    async ({ inputSources, replaySeconds = 0 }: SyncSelectionPayload): Promise<void> => {
      if (inputSources.length === 0) {
        await sendSelection({ inputSources: [], replaySeconds: 0 });
        emitStatus('Online');
        return;
      }

      const requestToken = ++listenRequestTokenRef.current;
      emitStatus(replaySeconds > 0 ? 'Cueing replay…' : 'Cueing audio…');

      try {
        await sendSelection({ inputSources, replaySeconds });
        primeAudioElementGain();
        void audioElementRef.current?.play().catch(() => {
          emitStatus('Audio ready');
        });
        if (requestToken !== listenRequestTokenRef.current) {
          return;
        }
        emitStatus('Streaming');
      } catch (error) {
        if (requestToken !== listenRequestTokenRef.current) {
          return;
        }
        console.error(error);
        emitStatus('Audio connection failed');
      }
    },
    [audioElementRef, emitStatus, primeAudioElementGain, sendSelection],
  );

  useEffect(() => {
    void ensureAudioTransport().catch((error) => {
      console.warn('Audio prewarm failed', error);
    });

    return () => {
      void closeAudioTransport({ preserveStatus: true });
    };
  }, [closeAudioTransport, ensureAudioTransport]);

  useEffect(() => () => {
    clearPendingFade();
  }, [clearPendingFade]);

  return {
    syncSelection,
    closeAudioTransport,
  };
}
