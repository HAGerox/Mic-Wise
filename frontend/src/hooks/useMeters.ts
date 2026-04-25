import { useCallback, useEffect, useRef, useState } from 'react';

import { appendMeterHistoryPoint } from '../lib/ui-logic';
import type { MeterChannelSnapshot, MeterSnapshotResponse } from '../types/api';

export const METER_HISTORY_POINTS = 280;

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

export function useMeters(
  { initialSnapshot, onOpen, onError }: UseMetersOptions,
): { meterMap: Map<number, MeterChannelSnapshot>; meterHistoryMap: Map<number, number[]> } {
  const [meterMap, setMeterMap] = useState<Map<number, MeterChannelSnapshot>>(() => snapshotToMap(initialSnapshot));
  const [meterHistoryMap, setMeterHistoryMap] = useState<Map<number, number[]>>(() => new Map());
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
    setMeterHistoryMap((currentHistoryMap) => {
      const nextHistoryMap = new Map<number, number[]>();
      for (const channelMeter of snapshot.channels) {
        nextHistoryMap.set(
          channelMeter.channel,
          appendMeterHistoryPoint(
            currentHistoryMap.get(channelMeter.channel) ?? [],
            channelMeter.peak,
            METER_HISTORY_POINTS,
          ),
        );
      }
      return nextHistoryMap;
    });
  }, []);

  useEffect(() => {
    setMeterMap(snapshotToMap(initialSnapshot));
    setMeterHistoryMap(
      new Map(
        (initialSnapshot?.channels ?? []).map((channelMeter) => [channelMeter.channel, [Math.max(0, channelMeter.peak)]])
      ),
    );
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

  return {
    meterMap,
    meterHistoryMap,
  };
}
