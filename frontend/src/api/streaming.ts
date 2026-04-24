import { fetchJson } from './client';
import type { WebRtcAnswerResponse, WebRtcOfferRequest } from '../types/api';

export function createWebRtcOffer(payload: WebRtcOfferRequest): Promise<WebRtcAnswerResponse> {
  return fetchJson<WebRtcAnswerResponse>('/api/streaming/webrtc/offer', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}
