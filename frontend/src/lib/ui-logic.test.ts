import { describe, expect, it } from 'vitest';

import {
  appendMeterHistoryPoint,
  buildEnergyLinePath,
  buildWaveformRulerMarks,
  buildExternalSyncStatusText,
  calculateWaveformPointShift,
  computeWaveformDisplayPoints,
  getSceneChecklistStats,
  getChannelSelectionAfterInteraction,
  getShowChannelVisualState,
  maxPoolValues,
  normaliseNumberOrder,
  normaliseActiveView,
  resolveActiveSceneId,
  shiftWaveformPoints,
} from './ui-logic';

describe('ui-logic helpers', () => {
  it('uses single selection by default and toggles the sole active channel off', () => {
    expect(getChannelSelectionAfterInteraction({
      orderedChannelIds: [1, 2, 3, 4],
      selectedChannelIds: new Set([1, 2]),
      anchorChannelId: 2,
      channelId: 3,
      additive: false,
      range: false,
    })).toEqual({ selectedChannelIds: [3], anchorChannelId: 3 });

    expect(getChannelSelectionAfterInteraction({
      orderedChannelIds: [1, 2, 3, 4],
      selectedChannelIds: new Set([3]),
      anchorChannelId: 3,
      channelId: 3,
      additive: false,
      range: false,
    })).toEqual({ selectedChannelIds: [], anchorChannelId: 3 });
  });

  it('command-click toggles individual channels without clearing the selection', () => {
    expect(getChannelSelectionAfterInteraction({
      orderedChannelIds: [1, 2, 3, 4],
      selectedChannelIds: new Set([1, 3]),
      anchorChannelId: 3,
      channelId: 4,
      additive: true,
      range: false,
    })).toEqual({ selectedChannelIds: [1, 3, 4], anchorChannelId: 4 });
  });

  it('shift-click adds the ordered range from the selection anchor', () => {
    expect(getChannelSelectionAfterInteraction({
      orderedChannelIds: [1, 2, 3, 4, 5],
      selectedChannelIds: new Set([1, 3]),
      anchorChannelId: 3,
      channelId: 5,
      additive: false,
      range: true,
    })).toEqual({ selectedChannelIds: [1, 3, 4, 5], anchorChannelId: 3 });
  });

  it('max-pools signal history so short transients remain visible', () => {
    expect(maxPoolValues([0.1, 0.9, 0.2, 0.4], 2)).toEqual([0.9, 0.4]);
    expect(maxPoolValues([-1, Number.NaN, 2], 3)).toEqual([0, 0, 1]);
  });

  it('builds one continuous signal line across the energy history', () => {
    const path = buildEnergyLinePath([0, 1], 2, 100, 24);

    expect(path).toBe('M0.00,22.00L100.00,2.00');
  });

  it('normaliseActiveView preserves new modes and maps legacy names', () => {
    expect(normaliseActiveView('monitor')).toBe('monitor');
    expect(normaliseActiveView('show')).toBe('show');
    expect(normaliseActiveView('setup')).toBe('setup');
    expect(normaliseActiveView('configure')).toBe('setup');
    expect(normaliseActiveView('scene')).toBe('show');
  });

  it('getShowChannelVisualState maps scene inclusion and checklist state', () => {
    expect(getShowChannelVisualState('off', false)).toBe('off');
    expect(getShowChannelVisualState('ready', false)).toBe('pending');
    expect(getShowChannelVisualState('onstage', true)).toBe('checked');
  });

  it('getSceneChecklistStats counts active scene assignments only', () => {
    const scene = {
      channel_assignments: [
        { channel_id: 1, state: 'onstage' as const },
        { channel_id: 2, state: 'ready' as const },
        { channel_id: 3, state: 'off' as const },
      ],
    };
    const checklist = new Set([2]);

    expect(getSceneChecklistStats(scene, checklist)).toEqual({ total: 2, checked: 1 });
  });

  it('buildExternalSyncStatusText reflects disabled, ready, and error states', () => {
    expect(buildExternalSyncStatusText(null)).toBe('Checking…');
    expect(
      buildExternalSyncStatusText({
        enabled: false,
        transport: 'off',
        error: null,
        last_event_summary: null,
        osc_listening: false,
        osc_endpoint: null,
        midi_listening: false,
        midi_input_name: null,
        last_matched_scene_id: null,
      }),
    ).toBe('Disabled');
    expect(
      buildExternalSyncStatusText({
        enabled: true,
        transport: 'osc',
        error: null,
        last_event_summary: '/qlab/go',
        osc_listening: true,
        osc_endpoint: '127.0.0.1:53001',
        midi_listening: false,
        midi_input_name: null,
        last_matched_scene_id: null,
      }),
    ).toBe('OSC ready · /qlab/go');
    expect(
      buildExternalSyncStatusText({
        enabled: true,
        transport: 'midi',
        error: 'Port unavailable',
        last_event_summary: null,
        osc_listening: false,
        osc_endpoint: null,
        midi_listening: false,
        midi_input_name: null,
        last_matched_scene_id: null,
      }),
    ).toBe('Sync error: Port unavailable');
  });

  it('resolveActiveSceneId keeps valid ids and falls back to the first ordered scene', () => {
    const scenes = [
      { id: 30, order_index: 2 },
      { id: 10, order_index: 0 },
      { id: 20, order_index: 1 },
    ] as Array<{ id: number; order_index: number }>;

    expect(resolveActiveSceneId(20, scenes as never)).toBe(20);
    expect(resolveActiveSceneId('30', scenes as never)).toBe(30);
    expect(resolveActiveSceneId(null, scenes as never)).toBe(10);
    expect(resolveActiveSceneId(999, scenes as never)).toBe(10);
    expect(resolveActiveSceneId(null, [])).toBeNull();
  });

  it('calculateWaveformPointShift maps one second to roughly one point in a five-minute window', () => {
    expect(calculateWaveformPointShift(0, 300, 300)).toBe(0);
    expect(calculateWaveformPointShift(1000, 300, 300)).toBe(299 / 300);
  });

  it('shiftWaveformPoints scrolls left with interpolation and preserves the live tail', () => {
    expect(shiftWaveformPoints([0, 10, 20, 30], 1)).toEqual([10, 20, 30, 30]);
    expect(shiftWaveformPoints([0, 10, 20, 30], 0.5)).toEqual([5, 15, 25, 30]);
    expect(shiftWaveformPoints([0, 10, 20, 30], 1.5, 40)).toEqual([15, 25, 40, 40]);
  });

  it('computeWaveformDisplayPoints combines time shift and live tail refresh', () => {
    const points = [0, 10, 20, 30];
    expect(computeWaveformDisplayPoints(points, 1000, 3, 45)).toEqual([10, 20, 30, 45]);
  });

  it('computeWaveformDisplayPoints handles empty inputs safely', () => {
    expect(computeWaveformDisplayPoints([], 500, 10, 12)).toEqual([]);
  });

  it('appendMeterHistoryPoint keeps a capped sliding window', () => {
    expect(appendMeterHistoryPoint([0.1, 0.2], 0.3, 2)).toEqual([0.2, 0.3]);
    expect(appendMeterHistoryPoint([], -1, 3)).toEqual([0]);
  });

  it('normaliseNumberOrder falls back when drag ordering is partial or invalid', () => {
    expect(normaliseNumberOrder([3, 2, 1], [1, 2, 3])).toEqual([3, 2, 1]);
    expect(normaliseNumberOrder([3, 2], [1, 2, 3])).toEqual([1, 2, 3]);
    expect(normaliseNumberOrder([3, 2, 2, 7], [1, 2, 3])).toEqual([1, 2, 3]);
  });

  it('buildWaveformRulerMarks creates major, minor, and live markers', () => {
    expect(buildWaveformRulerMarks(120, 60, 30)).toEqual([
      { position: 0, label: '2:00', kind: 'major' },
      { position: 0.25, label: '1:30', kind: 'minor' },
      { position: 0.5, label: '1:00', kind: 'major' },
      { position: 0.75, label: '0:30', kind: 'minor' },
      { position: 1, label: 'Live', kind: 'live' },
    ]);
  });
});
