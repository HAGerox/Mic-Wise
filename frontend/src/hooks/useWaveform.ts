import { useEffect, useState } from 'react';

import { useQuery } from '@tanstack/react-query';

import { getChannelWaveform } from '../api/channels';
import type { ChannelWaveformResponse } from '../types/api';

export const MODAL_WAVEFORM_WINDOW_SECONDS = 300;
export const MODAL_WAVEFORM_POINTS = 1200;
const MODAL_WAVEFORM_REFRESH_MS = 750;

export function useWaveform(channelId: number | null): {
  waveform: ChannelWaveformResponse | null;
  displayPoints: number[];
  isLoading: boolean;
} {
  const [displayPoints, setDisplayPoints] = useState<number[]>([]);

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
      return;
    }

    setDisplayPoints([...waveformQuery.data.points]);
  }, [waveformQuery.data]);

  return {
    waveform: waveformQuery.data ?? null,
    displayPoints,
    isLoading: waveformQuery.isLoading,
  };
}
