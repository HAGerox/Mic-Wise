import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildExternalSyncStatusText,
  calculateWaveformPointShift,
  computeWaveformDisplayPoints,
  getSceneChecklistStats,
  getShowChannelVisualState,
  normaliseActiveView,
  resolveActiveSceneId,
  shiftWaveformPoints,
} from '../ui_logic.mjs';

test('normaliseActiveView preserves new modes and maps legacy names', () => {
  assert.equal(normaliseActiveView('monitor'), 'monitor');
  assert.equal(normaliseActiveView('show'), 'show');
  assert.equal(normaliseActiveView('setup'), 'setup');
  assert.equal(normaliseActiveView('configure'), 'setup');
  assert.equal(normaliseActiveView('scene'), 'show');
});

test('getShowChannelVisualState maps scene inclusion and checklist state', () => {
  assert.equal(getShowChannelVisualState('off', false), 'off');
  assert.equal(getShowChannelVisualState('ready', false), 'pending');
  assert.equal(getShowChannelVisualState('onstage', true), 'checked');
});

test('getSceneChecklistStats counts active scene assignments only', () => {
  const scene = {
    channel_assignments: [
      { channel_id: 1, state: 'onstage' },
      { channel_id: 2, state: 'ready' },
      { channel_id: 3, state: 'off' },
    ],
  };
  const checklist = new Set([2]);

  assert.deepEqual(getSceneChecklistStats(scene, checklist), { total: 2, checked: 1 });
});

test('buildExternalSyncStatusText reflects disabled, ready, and error states', () => {
  assert.equal(buildExternalSyncStatusText(null), 'Checking…');
  assert.equal(
    buildExternalSyncStatusText({ enabled: false, transport: 'off', error: null, last_event_summary: null }),
    'Disabled',
  );
  assert.equal(
    buildExternalSyncStatusText({ enabled: true, transport: 'off', error: null, last_event_summary: null }),
    'Disabled',
  );
  assert.equal(
    buildExternalSyncStatusText({ enabled: true, transport: 'osc', error: null, last_event_summary: '/qlab/go' }),
    'OSC ready · /qlab/go',
  );
  assert.equal(
    buildExternalSyncStatusText({ enabled: true, transport: 'both', error: null, last_event_summary: null }),
    'OSC + MIDI ready',
  );
  assert.equal(
    buildExternalSyncStatusText({ enabled: true, transport: 'midi', error: 'Port unavailable', last_event_summary: null }),
    'Sync error: Port unavailable',
  );
});

test('resolveActiveSceneId keeps valid ids and falls back to the first ordered scene', () => {
  const scenes = [
    { id: 30, order_index: 2 },
    { id: 10, order_index: 0 },
    { id: 20, order_index: 1 },
  ];

  assert.equal(resolveActiveSceneId(20, scenes), 20);
  assert.equal(resolveActiveSceneId('30', scenes), 30);
  assert.equal(resolveActiveSceneId(null, scenes), 10);
  assert.equal(resolveActiveSceneId(999, scenes), 10);
  assert.equal(resolveActiveSceneId(null, []), null);
});

test('calculateWaveformPointShift maps one second to roughly one point in a five-minute window', () => {
  assert.equal(calculateWaveformPointShift(0, 300, 300), 0);
  assert.equal(calculateWaveformPointShift(1000, 300, 300), (299 / 300));
});

test('shiftWaveformPoints scrolls left with interpolation and preserves the live tail', () => {
  assert.deepEqual(shiftWaveformPoints([0, 10, 20, 30], 1), [10, 20, 30, 30]);
  assert.deepEqual(shiftWaveformPoints([0, 10, 20, 30], 0.5), [5, 15, 25, 30]);
  assert.deepEqual(shiftWaveformPoints([0, 10, 20, 30], 1.5, 40), [15, 25, 40, 40]);
});

test('computeWaveformDisplayPoints combines time shift and live tail refresh', () => {
  const points = [0, 10, 20, 30];
  const display = computeWaveformDisplayPoints(points, 1000, 3, 45);

  assert.deepEqual(display, [10, 20, 30, 45]);
});

test('computeWaveformDisplayPoints handles empty inputs safely', () => {
  assert.deepEqual(computeWaveformDisplayPoints([], 500, 10, 12), []);
});
