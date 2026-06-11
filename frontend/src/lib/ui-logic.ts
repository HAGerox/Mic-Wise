import type { SceneResponse, SceneSyncStatusResponse } from '../types/api';
import type { ActiveView, ShowChannelVisualState } from '../types/ui';

export interface WaveformRulerMark {
  position: number;
  label: string | null;
  kind: 'major' | 'minor' | 'live';
}

export function normaliseActiveView(activeMode: string | null | undefined): ActiveView {
  const mode = String(activeMode ?? 'monitor').trim().toLowerCase();
  if (mode === 'configure' || mode === 'program' || mode === 'setup') {
    return 'setup';
  }
  if (mode === 'scene' || mode === 'show') {
    return 'show';
  }
  return mode === 'monitor' ? 'monitor' : 'monitor';
}

export function getShowChannelVisualState(
  sceneState: string,
  isChecked: boolean,
): ShowChannelVisualState {
  if (sceneState === 'off') {
    return 'off';
  }
  return isChecked ? 'checked' : 'pending';
}

export function getSceneChecklistStats(
  scene: Pick<SceneResponse, 'channel_assignments'> | null | undefined,
  checklist: Pick<Set<number>, 'has'> | null | undefined,
): { total: number; checked: number } {
  const activeAssignments = (scene?.channel_assignments ?? []).filter(
    (assignment) => assignment.state && assignment.state !== 'off',
  );
  const checkedCount = activeAssignments.filter((assignment) => checklist?.has?.(assignment.channel_id)).length;
  return {
    total: activeAssignments.length,
    checked: checkedCount,
  };
}

function formatSyncTransportLabel(transport: string): string {
  if (transport === 'osc') {
    return 'OSC';
  }
  if (transport === 'midi') {
    return 'MIDI';
  }
  if (transport === 'both') {
    return 'OSC + MIDI';
  }
  return String(transport ?? 'off').toUpperCase();
}

export function buildExternalSyncStatusText(syncStatus: SceneSyncStatusResponse | null | undefined): string {
  if (!syncStatus) {
    return 'Checking…';
  }
  if (syncStatus.error) {
    return `Sync error: ${syncStatus.error}`;
  }
  const transport = String(syncStatus.transport ?? 'off').trim().toLowerCase();
  if (!syncStatus.enabled || transport === 'off') {
    return 'Disabled';
  }
  return `${formatSyncTransportLabel(transport)} ready${syncStatus.last_event_summary ? ` · ${syncStatus.last_event_summary}` : ''}`;
}

function sortScenesByOrder(scenes: SceneResponse[]): SceneResponse[] {
  return [...scenes].sort((left, right) => {
    if (left.order_index === right.order_index) {
      return left.id - right.id;
    }
    return left.order_index - right.order_index;
  });
}

export function resolveActiveSceneId(
  activeSceneId: number | string | null | undefined,
  scenes: SceneResponse[],
): number | null {
  const orderedScenes = sortScenesByOrder(Array.isArray(scenes) ? scenes : []);
  if (orderedScenes.length === 0) {
    return null;
  }

  const hasPreferredSceneId = activeSceneId !== null && activeSceneId !== undefined && activeSceneId !== '';
  const preferredSceneId = hasPreferredSceneId ? Number(activeSceneId) : null;
  if (Number.isInteger(preferredSceneId) && orderedScenes.some((scene) => scene.id === preferredSceneId)) {
    return preferredSceneId;
  }

  return orderedScenes[0].id;
}

export function calculateWaveformPointShift(
  elapsedMs: number,
  windowSeconds: number,
  pointCount: number,
): number {
  if (!Number.isFinite(elapsedMs) || elapsedMs <= 0 || !Number.isFinite(windowSeconds) || windowSeconds <= 0) {
    return 0;
  }
  if (!Number.isFinite(pointCount) || pointCount <= 1) {
    return 0;
  }
  return (elapsedMs / 1000) * ((pointCount - 1) / windowSeconds);
}

function clampIndex(index: number, lastIndex: number): number {
  if (index <= 0) {
    return 0;
  }
  if (index >= lastIndex) {
    return lastIndex;
  }
  return index;
}

export function shiftWaveformPoints(
  points: number[],
  pointShift: number,
  tailValue: number | null = null,
): number[] {
  if (!Array.isArray(points) || points.length === 0) {
    return [];
  }

  const lastIndex = points.length - 1;
  const resolvedTail = typeof tailValue === 'number' && Number.isFinite(tailValue)
    ? tailValue
    : points[lastIndex];
  const safeShift = Number.isFinite(pointShift) && pointShift > 0 ? pointShift : 0;

  return points.map((_, index) => {
    const sourceIndex = index + safeShift;
    if (sourceIndex > lastIndex) {
      return resolvedTail;
    }

    const lowerIndex = clampIndex(Math.floor(sourceIndex), lastIndex);
    const upperIndex = clampIndex(Math.ceil(sourceIndex), lastIndex);
    if (lowerIndex === upperIndex) {
      return points[lowerIndex];
    }

    const fraction = sourceIndex - lowerIndex;
    return points[lowerIndex] + ((points[upperIndex] - points[lowerIndex]) * fraction);
  });
}

export function computeWaveformDisplayPoints(
  points: number[],
  elapsedMs: number,
  windowSeconds: number,
  liveTailValue: number | null = null,
): number[] {
  const safePoints = Array.isArray(points) ? points : [];
  if (safePoints.length === 0) {
    return [];
  }

  const pointShift = calculateWaveformPointShift(elapsedMs, windowSeconds, safePoints.length);
  return shiftWaveformPoints(safePoints, pointShift, liveTailValue);
}

export function appendMeterHistoryPoint(
  history: number[],
  nextValue: number,
  maxPoints: number,
): number[] {
  const safeHistory = Array.isArray(history) ? history : [];
  const safeMaxPoints = Math.max(1, Math.floor(maxPoints));
  const safeValue = Math.max(0, Number.isFinite(nextValue) ? nextValue : 0);
  return [...safeHistory, safeValue].slice(-safeMaxPoints);
}

export function normaliseNumberOrder(candidateIds: number[], fallbackIds: number[]): number[] {
  const safeFallbackIds = Array.isArray(fallbackIds)
    ? fallbackIds.filter((value) => Number.isInteger(value))
    : [];
  const fallbackSet = new Set<number>(safeFallbackIds);
  const seenIds = new Set<number>();
  const orderedIds: number[] = [];

  for (const candidateId of Array.isArray(candidateIds) ? candidateIds : []) {
    if (!Number.isInteger(candidateId) || !fallbackSet.has(candidateId) || seenIds.has(candidateId)) {
      continue;
    }

    seenIds.add(candidateId);
    orderedIds.push(candidateId);
  }

  return orderedIds.length === safeFallbackIds.length ? orderedIds : safeFallbackIds;
}

function formatRulerLabel(seconds: number): string {
  if (seconds <= 0) {
    return 'Live';
  }
  const minutes = Math.floor(seconds / 60);
  const remainingSeconds = seconds % 60;
  return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`;
}

export function buildWaveformRulerMarks(
  windowSeconds: number,
  majorStepSeconds = 60,
  minorStepSeconds = 30,
  labelStepSeconds = minorStepSeconds,
): WaveformRulerMark[] {
  const safeWindowSeconds = Math.max(1, Math.floor(windowSeconds));
  const safeMajor = Math.max(1, Math.floor(majorStepSeconds));
  const safeMinor = Math.max(1, Math.floor(minorStepSeconds));
  const safeLabelStep = Math.max(1, Math.floor(labelStepSeconds));
  const marks: WaveformRulerMark[] = [];

  for (let seconds = safeWindowSeconds; seconds > 0; seconds -= safeMinor) {
    const kind = seconds % safeMajor === 0 ? 'major' : 'minor';
    marks.push({
      position: 1 - (seconds / safeWindowSeconds),
      label: kind === 'major' || seconds % safeLabelStep === 0 ? formatRulerLabel(seconds) : null,
      kind,
    });
  }

  marks.push({
    position: 1,
    label: 'Live',
    kind: 'live',
  });

  return marks;
}
