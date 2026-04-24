import { useCallback, useEffect, useRef, useState } from 'react';

import type { MeterChannelSnapshot, MeterSnapshotResponse } from '../types/api';

function snapshotToMap(
  snapshot: MeterSnapshotResponse | null | undefined,
): Map<number, MeterChannelSnapshot> {
  return new Map((snapshot?.channels ?? []).map((channelMeter) => [channelMeter.channel, channelMeter]));
}

interface UseMetersOptions {
  initialSnapshot?: MeterSnapshotResponse | null;
  onOpen?: () => void;
  onError?: () => void;
}

export function useMeters({ initialSnapshot, onOpen, onError }: UseMetersOptions): Map<number, MeterChannelSnapshot> {
  const [meterMap, setMeterMap] = useState<Map<number, MeterChannelSnapshot>>(() => snapshotToMap(initialSnapshot));
  const onOpenRef = useRef(onOpen);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onOpenRef.current = onOpen;
  }, [onOpen]);

  useEffect(() => {
    onErrorRef.current = onError;
  }, [onError]);

  const applySnapshot = useCallback((snapshot: MeterSnapshotResponse) => {
    setMeterMap(snapshotToMap(snapshot));
  }, []);

  useEffect(() => {
    setMeterMap(snapshotToMap(initialSnapshot));
  }, [initialSnapshot]);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const meterSocket = new WebSocket(`${protocol}://${window.location.host}/ws/meters`);

    meterSocket.onmessage = (event) => {
      applySnapshot(JSON.parse(event.data) as MeterSnapshotResponse);
    };
    meterSocket.onopen = () => {
      onOpenRef.current?.();
    };
    meterSocket.onerror = () => {
      onErrorRef.current?.();
    };

    return () => {
      meterSocket.close();
    };
  }, [applySnapshot]);

  return meterMap;
}
