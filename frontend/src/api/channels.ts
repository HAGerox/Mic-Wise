import { fetchJson } from './client';
import type {
  ChannelCreateRequest,
  ChannelResponse,
  ChannelUpdateRequest,
  ChannelWaveformResponse,
} from '../types/api';

export function listChannels(): Promise<ChannelResponse[]> {
  return fetchJson<ChannelResponse[]>('/api/channels');
}

export function createChannel(payload: ChannelCreateRequest = {}): Promise<ChannelResponse> {
  return fetchJson<ChannelResponse>('/api/channels', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateChannel(channelId: number, payload: ChannelUpdateRequest): Promise<ChannelResponse> {
  return fetchJson<ChannelResponse>(`/api/channels/${channelId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteChannel(channelId: number): Promise<null> {
  return fetchJson<null>(`/api/channels/${channelId}`, {
    method: 'DELETE',
  });
}

export function getChannelWaveform(
  channelId: number,
  seconds: number,
  points: number,
): Promise<ChannelWaveformResponse> {
  const params = new URLSearchParams({
    seconds: String(seconds),
    points: String(points),
  });
  return fetchJson<ChannelWaveformResponse>(`/api/channels/${channelId}/waveform?${params.toString()}`);
}
