import type { ActiveView, SceneChecklistById, SetupTab } from '../types/ui';

export interface AppState {
  activeView: ActiveView;
  setupTab: SetupTab;
  selectedChannelIds: Set<number>;
  modalChannelId: number | null;
  modalScrubSeconds: number;
  multiListen: boolean;
  layoutMode: boolean;
  activeSceneId: number | null;
  sceneChecklistById: SceneChecklistById;
  statusText: string;
}

export type AppStateAction =
  | {
      type: 'hydrateFromSettings';
      payload: {
        activeView: ActiveView;
        multiListen: boolean;
        activeSceneId: number | null;
      };
    }
  | { type: 'setStatusText'; payload: string }
  | { type: 'setSetupTab'; payload: SetupTab }
  | { type: 'setLayoutMode'; payload: boolean }
  | { type: 'setMultiListen'; payload: boolean }
  | { type: 'setActiveView'; payload: ActiveView }
  | { type: 'setActiveSceneId'; payload: number | null }
  | { type: 'interactChannelCard'; payload: { channelId: number } }
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
  setupTab: 'program',
  selectedChannelIds: new Set<number>(),
  modalChannelId: null,
  modalScrubSeconds: 0,
  multiListen: false,
  layoutMode: false,
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
    layoutMode: nextView === 'monitor' ? state.layoutMode : false,
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
          multiListen: action.payload.multiListen,
        },
        action.payload.activeView,
      );
    }

    case 'setStatusText':
      return { ...state, statusText: action.payload };

    case 'setSetupTab':
      return { ...state, setupTab: action.payload };

    case 'setLayoutMode':
      return { ...state, layoutMode: action.payload };

    case 'setMultiListen': {
      if (action.payload || state.selectedChannelIds.size <= 1) {
        return { ...state, multiListen: action.payload };
      }

      const [firstSelected] = state.selectedChannelIds;
      return {
        ...state,
        multiListen: action.payload,
        selectedChannelIds: new Set<number>(firstSelected ? [firstSelected] : []),
      };
    }

    case 'setActiveView':
      return applyViewSideEffects(state, action.payload);

    case 'setActiveSceneId':
      return { ...state, activeSceneId: action.payload };

    case 'interactChannelCard': {
      const nextSelection = new Set<number>(state.selectedChannelIds);
      const { channelId } = action.payload;

      if (state.multiListen) {
        if (nextSelection.has(channelId)) {
          nextSelection.delete(channelId);
        } else {
          nextSelection.add(channelId);
        }
      } else if (nextSelection.size === 1 && nextSelection.has(channelId)) {
        nextSelection.clear();
      } else {
        nextSelection.clear();
        nextSelection.add(channelId);
      }

      return {
        ...state,
        selectedChannelIds: nextSelection,
        modalChannelId: channelId,
        modalScrubSeconds: 0,
      };
    }

    case 'replaceSelection':
      return { ...state, selectedChannelIds: new Set<number>(action.payload) };

    case 'clearSelection':
      return { ...state, selectedChannelIds: new Set<number>(), modalScrubSeconds: 0 };

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

      return {
        ...state,
        selectedChannelIds,
        modalChannelId,
        modalScrubSeconds: modalChannelId === null ? 0 : state.modalScrubSeconds,
      };
    }

    default:
      return state;
  }
}
