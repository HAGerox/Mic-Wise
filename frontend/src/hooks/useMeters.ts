import { useCallback, useEffect, useRef, useState } from 'react';

import { appendMeterHistoryHops } from '../lib/ui-logic';
import type { MeterChannelSnapshot, MeterSnapshotResponse } from '../types/api';

// Hops are 50 ms of audio each (METER_HISTORY_HOP_MS on the server).
export const METER_HISTORY_HOPS_PER_POINT = 3;
export const METER_TRACE_POINTS = 96;
export const METER_HISTORY_POINTS = METER_HISTORY_HOPS_PER_POINT * METER_TRACE_POINTS;

export interface MeterHistory {
  /** Absolute hop index just after the newest value; every channel shares this grid. */
  endHop: number | null;
  channels: Map<number, number[]>;
}

const EMPTY_METER_HISTORY: MeterHistory = { endHop: null, channels: new Map() };

function snapshotToMap(
  snapshot: MeterSnapshotResponse | null | undefined,
): Map<number, MeterChannelSnapshot> {
  return new Map((snapshot?.channels ?? []).map((channelMeter) => [channelMeter.channel, channelMeter]));
}

interface UseMetersOptions {
  enabled?: boolean;
  initialSnapshot?: MeterSnapshotResponse | null;
  onOpen?: () => void;
  onError?: () => void;
}

export function useMeters(
  { enabled = true, initialSnapshot, onOpen, onError }: UseMetersOptions,
): { meterMap: Map<number, MeterChannelSnapshot>; meterHistory: MeterHistory } {
  const [meterMap, setMeterMap] = useState<Map<number, MeterChannelSnapshot>>(() => snapshotToMap(initialSnapshot));
  const [meterHistory, setMeterHistory] = useState<MeterHistory>(EMPTY_METER_HISTORY);
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
    const hopFrames = snapshot.history_hop_frames ?? 0;
    const newHopCount = snapshot.channels[0]?.rms_history?.length ?? 0;
    if (hopFrames <= 0 || newHopCount === 0) {
      return;
    }
    const startHop = Math.round((snapshot.history_start_frame ?? 0) / hopFrames);
    setMeterHistory((currentHistory) => {
      const nextChannels = new Map<number, number[]>();
      for (const channelMeter of snapshot.channels) {
        nextChannels.set(
          channelMeter.channel,
          appendMeterHistoryHops(
            currentHistory.channels.get(channelMeter.channel) ?? [],
            currentHistory.endHop,
            startHop,
            channelMeter.rms_history ?? [],
            METER_HISTORY_POINTS,
          ),
        );
      }
      return { endHop: startHop + newHopCount, channels: nextChannels };
    });
  }, []);

  useEffect(() => {
    setMeterMap(snapshotToMap(initialSnapshot));
    setMeterHistory(EMPTY_METER_HISTORY);
  }, [initialSnapshot]);

  useEffect(() => {
    if (!enabled) {
      return;
    }
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
      meterSocket.onmessage = null;
      meterSocket.onopen = null;
      meterSocket.onerror = null;
      meterSocket.close();
    };
  }, [applySnapshot, enabled]);

  return {
    meterMap,
    meterHistory,
  };
}
