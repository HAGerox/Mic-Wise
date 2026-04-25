import { describe, expect, it } from 'vitest';

import { appStateReducer, initialAppState } from './appStateReducer';

describe('appStateReducer', () => {
  it('toggles single-listen selection and opens the modal', () => {
    const firstPass = appStateReducer(initialAppState, {
      type: 'interactChannelCard',
      payload: { channelId: 12 },
    });

    expect([...firstPass.selectedChannelIds]).toEqual([12]);
    expect(firstPass.modalChannelId).toBe(12);
    expect(firstPass.modalScrubSeconds).toBe(0);

    const secondPass = appStateReducer(firstPass, {
      type: 'interactChannelCard',
      payload: { channelId: 12 },
    });

    expect([...secondPass.selectedChannelIds]).toEqual([]);
    expect(secondPass.modalChannelId).toBe(12);
  });

  it('preserves multiple selections in multi-listen mode', () => {
    const multiListenState = appStateReducer(initialAppState, {
      type: 'setMultiListen',
      payload: true,
    });
    const firstSelection = appStateReducer(multiListenState, {
      type: 'interactChannelCard',
      payload: { channelId: 1 },
    });
    const secondSelection = appStateReducer(firstSelection, {
      type: 'interactChannelCard',
      payload: { channelId: 2 },
    });

    expect([...secondSelection.selectedChannelIds]).toEqual([1, 2]);
  });

  it('drops layout mode and closes the modal when switching to setup view', () => {
    const populatedState = {
      ...initialAppState,
      activeView: 'monitor' as const,
      layoutMode: true,
      modalChannelId: 9,
      modalScrubSeconds: 42,
    };

    const nextState = appStateReducer(populatedState, {
      type: 'setActiveView',
      payload: 'setup',
    });

    expect(nextState.layoutMode).toBe(false);
    expect(nextState.modalChannelId).toBeNull();
    expect(nextState.modalScrubSeconds).toBe(0);
  });

  it('tracks scene checklist state per scene id', () => {
    const firstToggle = appStateReducer(initialAppState, {
      type: 'toggleSceneChecklist',
      payload: { sceneId: 7, channelId: 3 },
    });
    expect(firstToggle.sceneChecklistById.get(7)?.has(3)).toBe(true);

    const secondToggle = appStateReducer(firstToggle, {
      type: 'toggleSceneChecklist',
      payload: { sceneId: 7, channelId: 3, desiredState: false },
    });
    expect(secondToggle.sceneChecklistById.get(7)?.has(3)).toBe(false);
  });

  it('can reset all scene checklist state at once', () => {
    const populatedState = {
      ...initialAppState,
      sceneChecklistById: new Map([
        [1, new Set([1, 2])],
        [2, new Set([4])],
      ]),
    };

    const nextState = appStateReducer(populatedState, {
      type: 'resetAllSceneChecklists',
    });

    expect(nextState.sceneChecklistById.size).toBe(0);
  });

  it('reconciles selection and modal ids when channels disappear', () => {
    const populatedState = {
      ...initialAppState,
      selectedChannelIds: new Set([1, 2, 3]),
      modalChannelId: 2,
      modalScrubSeconds: 18,
    };

    const nextState = appStateReducer(populatedState, {
      type: 'reconcileChannelIds',
      payload: [1, 3],
    });

    expect([...nextState.selectedChannelIds]).toEqual([1, 3]);
    expect(nextState.modalChannelId).toBeNull();
    expect(nextState.modalScrubSeconds).toBe(0);
  });
});
