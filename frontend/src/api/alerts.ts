import { fetchJson } from './client';
import type { AudioAlertResponse } from '../types/api';

export function listActiveAlerts(): Promise<AudioAlertResponse[]> {
  return fetchJson<AudioAlertResponse[]>('/api/alerts/active');
}
