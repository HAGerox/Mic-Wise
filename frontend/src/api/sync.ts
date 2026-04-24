import { fetchJson } from './client';
import type { SceneSyncStatusResponse } from '../types/api';

export function getSyncStatus(): Promise<SceneSyncStatusResponse> {
  return fetchJson<SceneSyncStatusResponse>('/api/sync/status');
}
