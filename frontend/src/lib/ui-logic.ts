import type { SceneAssignmentState, SceneResponse, SceneSyncStatusResponse } from '../types/api';
import type { ActiveView, ShowChannelVisualState } from '../types/ui';

interface ChannelSelectionRequest {
  orderedChannelIds: number[];
  selectedChannelIds: ReadonlySet<number>;
  anchorChannelId: number | null;
  channelId: number;
  additive: boolean;
  range: boolean;
}

export interface ChannelSelectionResult {
  selectedChannelIds: number[];
  anchorChannelId: number | null;
}

export function getScenePaintStrokeState(
  currentState: SceneAssignmentState,
  brush: SceneAssignmentState,
): SceneAssignmentState {
  return brush !== 'off' && currentState === brush ? 'off' : brush;
}

export interface PointerStrokePoint {
  x: number;
  y: number;
}

export function getPointerStrokeSamplePoints(
  start: PointerStrokePoint,
  end: PointerStrokePoint,
  maximumStep = 10,
): PointerStrokePoint[] {
  const safeStep = Math.max(1, Number.isFinite(maximumStep) ? maximumStep : 10);
  const distance = Math.hypot(end.x - start.x, end.y - start.y);
  const stepCount = Math.max(1, Math.ceil(distance / safeStep));
  return Array.from({ length: stepCount }, (_, index) => {
    const ratio = (index + 1) / stepCount;
    return {
      x: start.x + ((end.x - start.x) * ratio),
      y: start.y + ((end.y - start.y) * ratio),
    };
  });
}

export interface ChannelGridPosition {
  channelId: number;
  left: number;
  top: number;
}

export type ChannelGridDirection = 'left' | 'right' | 'up' | 'down';

export function getChannelGridNavigationTarget(
  positions: ChannelGridPosition[],
  currentChannelId: number,
  direction: ChannelGridDirection,
): number | null {
  const orderedPositions = positions.filter((position, index) => (
    Number.isInteger(position.channelId)
    && positions.findIndex((candidate) => candidate.channelId === position.channelId) === index
  ));
  const currentPosition = orderedPositions.find((position) => position.channelId === currentChannelId);
  if (!currentPosition) {
    return null;
  }

  const rows: ChannelGridPosition[][] = [];
  for (const position of orderedPositions) {
    const row = rows.find((candidateRow) => Math.abs(candidateRow[0].top - position.top) <= 8);
    if (row) {
      row.push(position);
    } else {
      rows.push([position]);
    }
  }
  rows.sort((left, right) => left[0].top - right[0].top);
  rows.forEach((row) => row.sort((left, right) => left.left - right.left));

  const rowIndex = rows.findIndex((row) => row.some((position) => position.channelId === currentChannelId));
  const columnIndex = rows[rowIndex]?.findIndex((position) => position.channelId === currentChannelId) ?? -1;
  if (rowIndex === -1 || columnIndex === -1) {
    return null;
  }

  if (direction === 'left') {
    return rows[rowIndex][columnIndex - 1]?.channelId
      ?? rows[rowIndex - 1]?.at(-1)?.channelId
      ?? currentChannelId;
  }
  if (direction === 'right') {
    return rows[rowIndex][columnIndex + 1]?.channelId
      ?? rows[rowIndex + 1]?.[0]?.channelId
      ?? currentChannelId;
  }

  const targetRow = direction === 'up' ? rows[rowIndex - 1] : rows[rowIndex + 1];
  if (!targetRow) {
    return currentChannelId;
  }
  return targetRow.reduce((nearest, candidate) => (
    Math.abs(candidate.left - currentPosition.left) < Math.abs(nearest.left - currentPosition.left)
      ? candidate
      : nearest
  )).channelId;
}

export function getChannelSelectionAfterInteraction({
  orderedChannelIds,
  selectedChannelIds,
  anchorChannelId,
  channelId,
  additive,
  range,
}: ChannelSelectionRequest): ChannelSelectionResult {
  const validOrderedIds = orderedChannelIds.filter((id, index) => (
    Number.isInteger(id) && orderedChannelIds.indexOf(id) === index
  ));
  if (!validOrderedIds.includes(channelId)) {
    return {
      selectedChannelIds: validOrderedIds.filter((id) => selectedChannelIds.has(id)),
      anchorChannelId,
    };
  }

  if (range) {
    const fallbackAnchor = validOrderedIds.find((id) => selectedChannelIds.has(id)) ?? channelId;
    const resolvedAnchor = anchorChannelId !== null && validOrderedIds.includes(anchorChannelId)
      ? anchorChannelId
      : fallbackAnchor;
    const startIndex = validOrderedIds.indexOf(resolvedAnchor);
    const endIndex = validOrderedIds.indexOf(channelId);
    const rangeStart = Math.min(startIndex, endIndex);
    const rangeEnd = Math.max(startIndex, endIndex);
    const nextSelection = new Set<number>(selectedChannelIds);
    validOrderedIds.slice(rangeStart, rangeEnd + 1).forEach((id) => nextSelection.add(id));
    return {
      selectedChannelIds: validOrderedIds.filter((id) => nextSelection.has(id)),
      anchorChannelId: resolvedAnchor,
    };
  }

  if (additive) {
    const nextSelection = new Set<number>(selectedChannelIds);
    if (nextSelection.has(channelId)) {
      nextSelection.delete(channelId);
    } else {
      nextSelection.add(channelId);
    }
    return {
      selectedChannelIds: validOrderedIds.filter((id) => nextSelection.has(id)),
      anchorChannelId: channelId,
    };
  }

  const shouldClear = selectedChannelIds.size === 1 && selectedChannelIds.has(channelId);
  return {
    selectedChannelIds: shouldClear ? [] : [channelId],
    anchorChannelId: channelId,
  };
}

export interface WaveformRulerMark {
  position: number;
  label: string | null;
  kind: 'major' | 'minor' | 'live';
}

export function maxPoolValues(values: number[], targetCount: number): number[] {
  const safeTargetCount = Math.max(1, Math.floor(targetCount));
  if (values.length <= safeTargetCount) {
    return values.map((value) => Math.min(1, Math.max(0, Number.isFinite(value) ? value : 0)));
  }

  return Array.from({ length: safeTargetCount }, (_, index) => {
    const start = Math.floor((index * values.length) / safeTargetCount);
    const end = Math.max(start + 1, Math.floor(((index + 1) * values.length) / safeTargetCount));
    let peak = 0;
    for (let valueIndex = start; valueIndex < end; valueIndex += 1) {
      const value = values[valueIndex];
      peak = Math.max(peak, Number.isFinite(value) ? value : 0);
    }
    return Math.min(1, Math.max(0, peak));
  });
}

export function buildEnergyLinePath(
  values: number[],
  targetCount = 96,
  width = 100,
  height = 24,
): string {
  const safeTargetCount = Math.max(1, Math.floor(targetCount));
  const pooledValues = maxPoolValues(values.length > 0 ? values : [0], safeTargetCount);
  const displayValues = pooledValues.length < safeTargetCount
    ? [...Array<number>(safeTargetCount - pooledValues.length).fill(0), ...pooledValues]
    : pooledValues;
  const baseline = height - 2;
  const chartHeight = Math.max(1, height - 4);
  const pointSpan = displayValues.length > 1 ? width / (displayValues.length - 1) : 0;

  return displayValues.map((value, index) => {
    const x = index * pointSpan;
    const y = baseline - (value * chartHeight);
    return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join('');
}

export function normaliseActiveView(activeMode: string | null | undefined): ActiveView {
  const mode = String(activeMode ?? 'monitor').trim().toLowerCase();
  if (mode === 'setup') {
    return 'setup';
  }
  if (mode === 'show') {
    return 'show';
  }
  return 'monitor';
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

export function getSceneChecklistFromAssignments(
  assignments: Pick<SceneResponse['channel_assignments'][number], 'channel_id' | 'checked'>[] | null | undefined,
): Set<number> {
  const checked = new Set<number>();
  for (const assignment of assignments ?? []) {
    if (assignment.checked) {
      checked.add(assignment.channel_id);
    }
  }
  return checked;
}

export interface StageBackupLinkRequest {
  host?: string | null;
  port?: number | null;
  showName?: string | null;
}

export function buildStageBackupUri(request: StageBackupLinkRequest = {}): string {
  const params = new URLSearchParams({ target: 'micwise' });
  if (request.host) {
    params.set('host', request.host);
  }
  if (request.port != null) {
    params.set('port', String(request.port));
  }
  if (request.showName) {
    params.set('show', request.showName);
  }
  return `stage-backup://backup?${params.toString()}`;
}

export function describeImportSummary(summary: {
  channels: number;
  scenes: number;
  assets?: number;
  format?: string;
}): string {
  const parts = [`${summary.channels} channels`, `${summary.scenes} scenes`];
  if (summary.assets) {
    parts.push(`${summary.assets} photos`);
  }
  return `Imported ${parts.join(', ')}`;
}
