import { fetchJson } from './client';
import type { HealthResponse, SettingsResponse, SettingsUpdateRequest } from '../types/api';

export function getHealth(): Promise<HealthResponse> {
  return fetchJson<HealthResponse>('/api/health');
}

export function getSettings(): Promise<SettingsResponse> {
  return fetchJson<SettingsResponse>('/api/settings');
}

export function updateSettings(payload: SettingsUpdateRequest): Promise<SettingsResponse> {
  return fetchJson<SettingsResponse>('/api/settings', {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}
