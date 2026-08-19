import type { ActiveView, SceneChecklistById, SetupTab } from '../types/ui';
import type { ChannelSelectionModifiers } from '../types/ui';
import { getChannelSelectionAfterInteraction } from '../lib/ui-logic';

export interface AppState {
  activeView: ActiveView;
  setupTab: SetupTab;
  selectedChannelIds: Set<number>;
  selectionAnchorChannelId: number | null;
  modalChannelId: number | null;
  modalScrubSeconds: number;
  activeSceneId: number | null;
  sceneChecklistById: SceneChecklistById;
  statusText: string;
}

export type AppStateAction =
  | {
      type: 'hydrateFromSettings';
      payload: {
        activeView: ActiveView;
        activeSceneId: number | null;
      };
    }
  | { type: 'setStatusText'; payload: string }
  | { type: 'setSetupTab'; payload: SetupTab }
  | { type: 'setActiveView'; payload: ActiveView }
  | { type: 'setActiveSceneId'; payload: number | null }
  | {
      type: 'interactChannelCard';
      payload: {
        channelId: number;
        orderedChannelIds: number[];
        modifiers: ChannelSelectionModifiers;
      };
    }
  | { type: 'replaceSelection'; payload: number[] }
  | { type: 'clearSelection' }
  | { type: 'openModal'; payload: number }
  | { type: 'closeModal' }
  | { type: 'setModalScrubSeconds'; payload: number }
  | {
      type: 'toggleSceneChecklist';
      payload: {
        sceneId: number;
        channelId: number;
        desiredState?: boolean | null;
      };
    }
  | { type: 'resetAllSceneChecklists' }
  | { type: 'reconcileChannelIds'; payload: number[] };

export const initialAppState: AppState = {
  activeView: 'monitor',
  setupTab: 'general',
  selectedChannelIds: new Set<number>(),
  selectionAnchorChannelId: null,
  modalChannelId: null,
  modalScrubSeconds: 0,
  activeSceneId: null,
  sceneChecklistById: new Map<number, Set<number>>(),
  statusText: 'Connecting…',
};

function cloneChecklistMap(source: SceneChecklistById): SceneChecklistById {
  return new Map(
    [...source.entries()].map(([sceneId, checklist]) => [sceneId, new Set<number>(checklist)]),
  );
}

function applyViewSideEffects(state: AppState, nextView: ActiveView): AppState {
  const nextState: AppState = {
    ...state,
    activeView: nextView,
  };

  if (nextView !== 'monitor' && nextView !== 'show') {
    nextState.modalChannelId = null;
    nextState.modalScrubSeconds = 0;
  }

  return nextState;
}

export function appStateReducer(state: AppState, action: AppStateAction): AppState {
  switch (action.type) {
    case 'hydrateFromSettings': {
      return applyViewSideEffects(
        {
          ...state,
          activeSceneId: action.payload.activeSceneId,
        },
        action.payload.activeView,
      );
    }

    case 'setStatusText':
      return { ...state, statusText: action.payload };

    case 'setSetupTab':
      return { ...state, setupTab: action.payload };

    case 'setActiveView':
      return applyViewSideEffects(state, action.payload);

    case 'setActiveSceneId':
      return { ...state, activeSceneId: action.payload };

    case 'interactChannelCard': {
      const { channelId, orderedChannelIds, modifiers } = action.payload;
      const nextSelection = getChannelSelectionAfterInteraction({
        orderedChannelIds,
        selectedChannelIds: state.selectedChannelIds,
        anchorChannelId: state.selectionAnchorChannelId,
        channelId,
        additive: modifiers.additive,
        range: modifiers.range,
      });

      return {
        ...state,
        selectedChannelIds: new Set<number>(nextSelection.selectedChannelIds),
        selectionAnchorChannelId: nextSelection.anchorChannelId,
        modalChannelId: channelId,
        modalScrubSeconds: 0,
      };
    }

    case 'replaceSelection':
      return {
        ...state,
        selectedChannelIds: new Set<number>(action.payload),
        selectionAnchorChannelId: action.payload.at(-1) ?? null,
      };

    case 'clearSelection':
      return {
        ...state,
        selectedChannelIds: new Set<number>(),
        selectionAnchorChannelId: null,
        modalScrubSeconds: 0,
      };

    case 'openModal':
      return { ...state, modalChannelId: action.payload, modalScrubSeconds: 0 };

    case 'closeModal':
      return {
        ...state,
        modalChannelId: null,
        modalScrubSeconds: 0,
      };

    case 'setModalScrubSeconds':
      return { ...state, modalScrubSeconds: action.payload };

    case 'toggleSceneChecklist': {
      const { sceneId, channelId, desiredState } = action.payload;
      const nextChecklistMap = cloneChecklistMap(state.sceneChecklistById);
      const checklist = nextChecklistMap.get(sceneId) ?? new Set<number>();
      const shouldCheck = desiredState ?? !checklist.has(channelId);

      if (shouldCheck) {
        checklist.add(channelId);
      } else {
        checklist.delete(channelId);
      }

      nextChecklistMap.set(sceneId, checklist);
      return { ...state, sceneChecklistById: nextChecklistMap };
    }

    case 'resetAllSceneChecklists':
      return { ...state, sceneChecklistById: new Map<number, Set<number>>() };

    case 'reconcileChannelIds': {
      const validIds = new Set<number>(action.payload);
      const selectedChannelIds = new Set<number>(
        [...state.selectedChannelIds].filter((channelId) => validIds.has(channelId)),
      );
      const modalChannelId = state.modalChannelId !== null && validIds.has(state.modalChannelId)
        ? state.modalChannelId
        : null;
      const selectionAnchorChannelId = state.selectionAnchorChannelId !== null
        && validIds.has(state.selectionAnchorChannelId)
        ? state.selectionAnchorChannelId
        : [...selectedChannelIds].at(-1) ?? null;

      return {
        ...state,
        selectedChannelIds,
        selectionAnchorChannelId,
        modalChannelId,
        modalScrubSeconds: modalChannelId === null ? 0 : state.modalScrubSeconds,
      };
    }

    default:
      return state;
  }
}
