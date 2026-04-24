import { fetchJson } from './client';
import type { SceneCreateRequest, SceneResponse, SceneUpdateRequest } from '../types/api';

export function listScenes(): Promise<SceneResponse[]> {
  return fetchJson<SceneResponse[]>('/api/scenes');
}

export function createScene(payload: SceneCreateRequest = {}): Promise<SceneResponse> {
  return fetchJson<SceneResponse>('/api/scenes', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateScene(sceneId: number, payload: SceneUpdateRequest): Promise<SceneResponse> {
  return fetchJson<SceneResponse>(`/api/scenes/${sceneId}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteScene(sceneId: number): Promise<null> {
  return fetchJson<null>(`/api/scenes/${sceneId}`, {
    method: 'DELETE',
  });
}
