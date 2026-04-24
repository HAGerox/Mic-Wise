import { fetchJson } from './client';
import type { MeterSnapshotResponse } from '../types/api';

export function getLatestMeters(): Promise<MeterSnapshotResponse> {
  return fetchJson<MeterSnapshotResponse>('/api/meters/latest');
}
