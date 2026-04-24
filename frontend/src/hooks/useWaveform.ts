import { useEffect, useRef, useState } from 'react';

import { useQuery } from '@tanstack/react-query';

import { getChannelWaveform } from '../api/channels';
import { computeWaveformDisplayPoints } from '../lib/ui-logic';
import type { ChannelWaveformResponse } from '../types/api';

export const MODAL_WAVEFORM_WINDOW_SECONDS = 300;
export const MODAL_WAVEFORM_POINTS = 360;
const MODAL_WAVEFORM_REFRESH_MS = 900;
const MODAL_WAVEFORM_RENDER_MS = 33;

export function useWaveform(channelId: number | null): {
  waveform: ChannelWaveformResponse | null;
  displayPoints: number[];
  isLoading: boolean;
} {
  const [displayPoints, setDisplayPoints] = useState<number[]>([]);
  const lastFetchedAtRef = useRef(0);

  const waveformQuery = useQuery({
    queryKey: ['waveform', channelId],
    queryFn: () => getChannelWaveform(channelId ?? -1, MODAL_WAVEFORM_WINDOW_SECONDS, MODAL_WAVEFORM_POINTS),
    enabled: channelId !== null,
    refetchInterval: channelId !== null ? MODAL_WAVEFORM_REFRESH_MS : false,
    refetchOnWindowFocus: false,
  });

  useEffect(() => {
    if (!waveformQuery.data) {
      setDisplayPoints([]);
      lastFetchedAtRef.current = 0;
      return;
    }

    setDisplayPoints([...waveformQuery.data.points]);
    lastFetchedAtRef.current = performance.now();
  }, [waveformQuery.data]);

  useEffect(() => {
    if (!waveformQuery.data) {
      return undefined;
    }

    const intervalId = window.setInterval(() => {
      const elapsedMs = Math.max(0, performance.now() - lastFetchedAtRef.current);
      setDisplayPoints(
        computeWaveformDisplayPoints(
          waveformQuery.data.points,
          elapsedMs,
          MODAL_WAVEFORM_WINDOW_SECONDS,
          waveformQuery.data.points[waveformQuery.data.points.length - 1] ?? 0,
        ),
      );
    }, MODAL_WAVEFORM_RENDER_MS);

    return () => {
      window.clearInterval(intervalId);
    };
  }, [waveformQuery.data]);

  return {
    waveform: waveformQuery.data ?? null,
    displayPoints,
    isLoading: waveformQuery.isLoading,
  };
}
