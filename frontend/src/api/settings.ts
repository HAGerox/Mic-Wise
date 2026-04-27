import { fetchJson } from './client';
import type {
  AudioInputDeviceResponse,
  AudioAlertResponse,
  HealthResponse,
  NetworkInterfaceResponse,
  RadioWorldTestResponse,
  SettingsResponse,
  SettingsUpdateRequest,
} from '../types/api';

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

export function listAudioInputDevices(): Promise<AudioInputDeviceResponse[]> {
  return fetchJson<AudioInputDeviceResponse[]>('/api/audio/devices');
}

export function listNetworkInterfaces(): Promise<NetworkInterfaceResponse[]> {
  return fetchJson<NetworkInterfaceResponse[]>('/api/network/interfaces');
}

export function testAlerts(): Promise<AudioAlertResponse> {
  return fetchJson<AudioAlertResponse>('/api/alerts/test', { method: 'POST' });
}

export function testRadioWorld(): Promise<RadioWorldTestResponse> {
  return fetchJson<RadioWorldTestResponse>('/api/radioworld/test', { method: 'POST' });
}
