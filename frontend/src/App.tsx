import { useCallback, useEffect, useMemo, useRef } from 'react';

import { useQuery, useQueryClient } from '@tanstack/react-query';

import { getLatestMeters } from './api/meters';
import { createChannel, deleteChannel, listChannels, updateChannel } from './api/channels';
import { createScene, deleteScene, listScenes, updateScene } from './api/scenes';
import { getHealth, getSettings, updateSettings } from './api/settings';
import { getSyncStatus } from './api/sync';
import { ChannelGrid } from './components/ChannelGrid';
import { ChannelModal } from './components/ChannelModal';
import { SetupView } from './components/SetupView';
import { ShowSidebar } from './components/ShowSidebar';
import { Toolbar } from './components/Toolbar';
import { useAudioTransport } from './hooks/useAudioTransport';
import { useMeters } from './hooks/useMeters';
import { useWaveform } from './hooks/useWaveform';
import { clampGainDb, sortChannels, sortScenes } from './lib/format';
import {
  getSceneChecklistStats,
  normaliseActiveView,
  resolveActiveSceneId,
} from './lib/ui-logic';
import { useAppState } from './state/AppStateContext';
import type {
  ChannelResponse,
  ChannelUpdateRequest,
  SceneChannelAssignmentRequest,
  SceneResponse,
  SceneUpdateRequest,
  SettingsResponse,
  SettingsUpdateRequest,
} from './types/api';
import type { ActiveView, AudioInputSource } from './types/ui';

const SYNC_STATUS_REFRESH_MS = 1500;

function getSceneAssignmentState(scene: SceneResponse | null, channelId: number): string {
  if (!scene) {
    return 'off';
  }

  return scene.channel_assignments.find((assignment) => assignment.channel_id === channelId)?.state ?? 'off';
}

function getSceneSummary(scene: SceneResponse | null): string {
  const assignments = scene?.channel_assignments ?? [];
  const onstageCount = assignments.filter((assignment) => assignment.state === 'onstage').length;
  const readyCount = assignments.filter((assignment) => assignment.state === 'ready').length;
  return `${onstageCount} on stage • ${readyCount} about to enter`;
}

function getCombinedGainDb(channel: ChannelResponse | null, settings: SettingsResponse | null): number {
  return clampGainDb((channel?.gain_db ?? 0) + (settings?.master_gain_db ?? 0));
}

function getTransportStatusText(
  modalChannelId: number | null,
  selectedChannelIds: Set<number>,
  modalScrubSeconds: number,
): string {
  if (!modalChannelId || !selectedChannelIds.has(modalChannelId)) {
    return 'Not currently listening';
  }

  if (modalScrubSeconds > 0) {
    const totalSeconds = Math.max(0, Math.round(modalScrubSeconds));
    const minutes = Math.floor(totalSeconds / 60);
    const remainingSeconds = totalSeconds % 60;
    return `Listening ${minutes}:${String(remainingSeconds).padStart(2, '0')} behind live`;
  }

  return 'Listening live';
}

function getFocusedShowChannelId(
  modalChannelId: number | null,
  selectedChannelIds: Set<number>,
  channels: ChannelResponse[],
): number | null {
  if (modalChannelId !== null) {
    return modalChannelId;
  }

  const orderedSelection = sortChannels(channels)
    .map((channel) => channel.id)
    .filter((channelId) => selectedChannelIds.has(channelId));

  return orderedSelection[0] ?? null;
}

function getNextSelectionAfterInteraction(
  selectedChannelIds: Set<number>,
  channelId: number,
  multiListen: boolean,
): number[] {
  const nextSelection = new Set<number>(selectedChannelIds);

  if (multiListen) {
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

  return [...nextSelection];
}

function AppContent(): JSX.Element {
  const { state, dispatch } = useAppState();
  const queryClient = useQueryClient();
  const audioElementRef = useRef<HTMLAudioElement | null>(null);
  const monitorViewRef = useRef<HTMLElement | null>(null);
  const monitorDockRef = useRef<HTMLElement | null>(null);

  const healthQuery = useQuery({
    queryKey: ['health'],
    queryFn: getHealth,
    refetchOnWindowFocus: false,
  });
  const settingsQuery = useQuery({
    queryKey: ['settings'],
    queryFn: getSettings,
    refetchOnWindowFocus: false,
  });
  const channelsQuery = useQuery({
    queryKey: ['channels'],
    queryFn: listChannels,
    refetchOnWindowFocus: false,
  });
  const scenesQuery = useQuery({
    queryKey: ['scenes'],
    queryFn: listScenes,
    refetchOnWindowFocus: false,
  });
  const latestMetersQuery = useQuery({
    queryKey: ['latestMeters'],
    queryFn: getLatestMeters,
    refetchOnWindowFocus: false,
  });
  const syncStatusQuery = useQuery({
    queryKey: ['syncStatus'],
    queryFn: getSyncStatus,
    refetchInterval: SYNC_STATUS_REFRESH_MS,
    refetchOnWindowFocus: false,
  });

  const channels = channelsQuery.data ?? [];
  const scenes = scenesQuery.data ?? [];
  const settings = settingsQuery.data ?? null;
  const syncStatus = syncStatusQuery.data ?? null;

  const orderedChannels = useMemo(() => sortChannels(channels), [channels]);
  const orderedScenes = useMemo(() => sortScenes(scenes), [scenes]);
  const activeScene = useMemo(
    () => orderedScenes.find((scene) => scene.id === state.activeSceneId) ?? null,
    [orderedScenes, state.activeSceneId],
  );
  const activeSceneIndex = useMemo(
    () => orderedScenes.findIndex((scene) => scene.id === state.activeSceneId),
    [orderedScenes, state.activeSceneId],
  );
  const nextScene = activeSceneIndex === -1 ? orderedScenes[0] ?? null : orderedScenes[activeSceneIndex + 1] ?? null;
  const sceneChecklist = useMemo(
    () => (activeScene ? state.sceneChecklistById.get(activeScene.id) ?? new Set<number>() : new Set<number>()),
    [activeScene, state.sceneChecklistById],
  );
  const sceneChecklistStats = useMemo(
    () => getSceneChecklistStats(activeScene, sceneChecklist),
    [activeScene, sceneChecklist],
  );
  const modalChannel = useMemo(
    () => channels.find((channel) => channel.id === state.modalChannelId) ?? null,
    [channels, state.modalChannelId],
  );
  const activeSceneName = activeScene ? activeScene.name : 'No scenes';
  const isMonitorLikeView = state.activeView === 'monitor' || state.activeView === 'show';

  const setStatusText = useCallback((statusText: string) => {
    dispatch({ type: 'setStatusText', payload: statusText });
  }, [dispatch]);

  const buildSelectionInputSources = useCallback((channelIds: number[]): AudioInputSource[] => {
    return channelIds
      .map((channelId) => channels.find((channel) => channel.id === channelId) ?? null)
      .filter((channel): channel is ChannelResponse => Boolean(channel))
      .filter((channel) => channel.input_index !== null && channel.input_index !== undefined)
      .map((channel) => [channel.input_index as number, getCombinedGainDb(channel, settings)]);
  }, [channels, settings]);

  const orderedSelection = useCallback((selection = state.selectedChannelIds): number[] => {
    return orderedChannels
      .map((channel) => channel.id)
      .filter((channelId) => selection.has(channelId));
  }, [orderedChannels, state.selectedChannelIds]);

  const { syncSelection } = useAudioTransport({
    audioElementRef,
    onStatusChange: setStatusText,
  });

  const meterMap = useMeters({
    initialSnapshot: latestMetersQuery.data,
    onOpen: () => {
      if (state.selectedChannelIds.size === 0 && healthQuery.data?.audio_engine_running) {
        setStatusText('Online');
      }
    },
    onError: () => {
      setStatusText('Meter socket error');
    },
  });

  const { waveform, displayPoints } = useWaveform(state.modalChannelId);

  useEffect(() => {
    if (!settings) {
      return;
    }

    dispatch({
      type: 'hydrateFromSettings',
      payload: {
        activeView: normaliseActiveView(settings.active_mode),
        multiListen: settings.multi_listen_enabled,
        activeSceneId: resolveActiveSceneId(settings.active_scene_id, scenes),
      },
    });
  }, [dispatch, scenes, settings]);

  useEffect(() => {
    dispatch({
      type: 'reconcileChannelIds',
      payload: channels.map((channel) => channel.id),
    });
  }, [channels, dispatch]);

  useEffect(() => {
    if (!syncStatus || syncStatus.last_matched_scene_id === null || syncStatus.last_matched_scene_id === state.activeSceneId) {
      return;
    }

    dispatch({ type: 'setActiveSceneId', payload: syncStatus.last_matched_scene_id });
    if (settings) {
      queryClient.setQueryData<SettingsResponse>(['settings'], {
        ...settings,
        active_scene_id: syncStatus.last_matched_scene_id,
      });
    }
  }, [dispatch, queryClient, settings, state.activeSceneId, syncStatus]);

  useEffect(() => {
    if (!healthQuery.data) {
      return;
    }

    if (state.selectedChannelIds.size > 0) {
      return;
    }

    setStatusText(healthQuery.data.audio_engine_running ? 'Online' : 'Starting');
  }, [healthQuery.data, setStatusText, state.selectedChannelIds.size]);

  useEffect(() => {
    document.body.classList.toggle('monitor-view-active', isMonitorLikeView);

    const monitorView = monitorViewRef.current;
    const monitorDock = monitorDockRef.current;
    if (!monitorView || !monitorDock || !isMonitorLikeView) {
      monitorView?.style.removeProperty('--monitor-dock-height');
      return () => {
        document.body.classList.remove('monitor-view-active');
      };
    }

    let frameId = 0;
    const updateDockHeight = (): void => {
      frameId = window.requestAnimationFrame(() => {
        const dockHeight = Math.ceil(monitorDock.getBoundingClientRect().height);
        if (dockHeight > 0) {
          monitorView.style.setProperty('--monitor-dock-height', `${dockHeight}px`);
        }
      });
    };

    updateDockHeight();
    const resizeObserver = new ResizeObserver(() => {
      updateDockHeight();
    });
    resizeObserver.observe(monitorDock);
    window.addEventListener('resize', updateDockHeight);

    return () => {
      window.cancelAnimationFrame(frameId);
      resizeObserver.disconnect();
      window.removeEventListener('resize', updateDockHeight);
      document.body.classList.remove('monitor-view-active');
    };
  }, [isMonitorLikeView, state.modalChannelId]);

  useEffect(() => {
    const handleGlobalKeydown = (event: KeyboardEvent): void => {
      const target = event.target;
      if (
        target instanceof HTMLElement
        && (
          target.isContentEditable
          || target.tagName === 'INPUT'
          || target.tagName === 'TEXTAREA'
          || target.tagName === 'SELECT'
        )
      ) {
        return;
      }

      if (state.activeView !== 'show') {
        return;
      }

      const focusedChannelId = getFocusedShowChannelId(state.modalChannelId, state.selectedChannelIds, channels);
      if (focusedChannelId === null || !activeScene) {
        return;
      }

      if (getSceneAssignmentState(activeScene, focusedChannelId) === 'off') {
        return;
      }

      if (event.key.toLowerCase() === 'y') {
        event.preventDefault();
        dispatch({
          type: 'toggleSceneChecklist',
          payload: {
            sceneId: activeScene.id,
            channelId: focusedChannelId,
            desiredState: true,
          },
        });
      }

      if (event.key.toLowerCase() === 'n') {
        event.preventDefault();
        dispatch({
          type: 'toggleSceneChecklist',
          payload: {
            sceneId: activeScene.id,
            channelId: focusedChannelId,
            desiredState: false,
          },
        });
      }
    };

    window.addEventListener('keydown', handleGlobalKeydown);
    return () => {
      window.removeEventListener('keydown', handleGlobalKeydown);
    };
  }, [activeScene, channels, dispatch, state.activeView, state.modalChannelId, state.selectedChannelIds]);

  const patchSettings = useCallback(async (changes: SettingsUpdateRequest): Promise<SettingsResponse> => {
    const updatedSettings = await updateSettings(changes);
    const currentScenes = queryClient.getQueryData<SceneResponse[]>(['scenes']) ?? scenes;
    queryClient.setQueryData(['settings'], updatedSettings);
    dispatch({
      type: 'hydrateFromSettings',
      payload: {
        activeView: normaliseActiveView(updatedSettings.active_mode),
        multiListen: updatedSettings.multi_listen_enabled,
        activeSceneId: resolveActiveSceneId(updatedSettings.active_scene_id, currentScenes),
      },
    });
    await queryClient.invalidateQueries({ queryKey: ['syncStatus'] });
    return updatedSettings;
  }, [dispatch, queryClient, scenes]);

  const syncListening = useCallback(async (channelIds: number[], replaySeconds = 0): Promise<void> => {
    await syncSelection({
      inputSources: buildSelectionInputSources(channelIds),
      replaySeconds,
    });
  }, [buildSelectionInputSources, syncSelection]);

  const handleSetActiveView = useCallback(async (view: ActiveView): Promise<void> => {
    dispatch({ type: 'setActiveView', payload: view });
    await patchSettings({
      active_mode: view === 'setup' ? 'setup' : view,
      scene_mode_enabled: view === 'show',
    });
  }, [dispatch, patchSettings]);

  const handleToggleListenMode = useCallback(async (): Promise<void> => {
    const nextMultiListen = !state.multiListen;
    const nextSelection = nextMultiListen ? orderedSelection() : orderedSelection().slice(0, 1);
    dispatch({ type: 'setMultiListen', payload: nextMultiListen });

    if (!nextMultiListen && state.selectedChannelIds.size > 1) {
      dispatch({ type: 'replaceSelection', payload: nextSelection });
      await syncListening(nextSelection, 0);
    }

    await patchSettings({ multi_listen_enabled: nextMultiListen });
  }, [dispatch, orderedSelection, patchSettings, state.multiListen, state.selectedChannelIds.size, syncListening]);

  const handleStopListening = useCallback(async (): Promise<void> => {
    dispatch({ type: 'clearSelection' });
    await syncListening([], 0);
  }, [dispatch, syncListening]);

  const handleToggleLayoutMode = useCallback((): void => {
    if (state.activeView !== 'monitor') {
      return;
    }

    dispatch({ type: 'setLayoutMode', payload: !state.layoutMode });
    if (!state.layoutMode) {
      dispatch({ type: 'closeModal' });
    }
  }, [dispatch, state.activeView, state.layoutMode]);

  const handlePersistOrder = useCallback(async (orderedIds: number[]): Promise<void> => {
    const channelById = new Map(channels.map((channel) => [channel.id, channel]));
    const changedChannels = orderedIds
      .map((channelId, sortIndex) => ({ channelId, sortIndex, channel: channelById.get(channelId) ?? null }))
      .filter(({ channel, sortIndex }) => channel && channel.sort_index !== sortIndex)
      .map(({ channelId, sortIndex }) => ({ id: channelId, sort_index: sortIndex }));

    queryClient.setQueryData<ChannelResponse[]>(
      ['channels'],
      orderedIds.map((channelId, sortIndex) => ({
        ...(channelById.get(channelId) as ChannelResponse),
        sort_index: sortIndex,
      })),
    );

    await Promise.all(
      changedChannels.map((channel) => updateChannel(channel.id, { sort_index: channel.sort_index })),
    );
  }, [channels, queryClient]);

  const handleChannelInteraction = useCallback(async (channelId: number): Promise<void> => {
    const nextSelection = getNextSelectionAfterInteraction(state.selectedChannelIds, channelId, state.multiListen);
    dispatch({ type: 'interactChannelCard', payload: { channelId } });
    await syncListening(nextSelection, 0);
  }, [dispatch, state.multiListen, state.selectedChannelIds, syncListening]);

  const handleScrubWaveform = useCallback(async (replaySeconds: number): Promise<void> => {
    if (state.modalChannelId === null) {
      return;
    }

    dispatch({ type: 'replaceSelection', payload: [state.modalChannelId] });
    dispatch({ type: 'setModalScrubSeconds', payload: replaySeconds });
    await syncListening([state.modalChannelId], replaySeconds);
  }, [dispatch, state.modalChannelId, syncListening]);

  const handleToggleChecklist = useCallback((channelId: number, desiredState?: boolean | null): void => {
    if (!activeScene) {
      return;
    }
    if (getSceneAssignmentState(activeScene, channelId) === 'off') {
      return;
    }

    dispatch({
      type: 'toggleSceneChecklist',
      payload: {
        sceneId: activeScene.id,
        channelId,
        desiredState,
      },
    });
  }, [activeScene, dispatch]);

  const handleNavigateScene = useCallback(async (offset: number): Promise<void> => {
    const nextIndex = activeSceneIndex === -1
      ? 0
      : Math.max(0, Math.min(activeSceneIndex + offset, orderedScenes.length - 1));
    const targetScene = orderedScenes[nextIndex] ?? null;
    if (!targetScene) {
      return;
    }

    dispatch({ type: 'setActiveSceneId', payload: targetScene.id });
    await patchSettings({ active_scene_id: targetScene.id });
  }, [activeSceneIndex, dispatch, orderedScenes, patchSettings]);

  const handleAddChannel = useCallback(async (): Promise<void> => {
    await createChannel({});
    await queryClient.invalidateQueries({ queryKey: ['channels'] });
  }, [queryClient]);

  const handleSaveChannel = useCallback(async (channelId: number, payload: ChannelUpdateRequest): Promise<void> => {
    const updatedChannel = await updateChannel(channelId, payload);
    queryClient.setQueryData<ChannelResponse[]>(
      ['channels'],
      (current = []) => current.map((channel) => (channel.id === channelId ? updatedChannel : channel)),
    );

    if (state.selectedChannelIds.has(channelId)) {
      await syncListening(orderedSelection(), state.modalScrubSeconds);
    }
  }, [orderedSelection, queryClient, state.modalScrubSeconds, state.selectedChannelIds, syncListening]);

  const handleRemoveChannel = useCallback(async (channelId: number): Promise<void> => {
    await deleteChannel(channelId);
    await queryClient.invalidateQueries({ queryKey: ['channels'] });
  }, [queryClient]);

  const handleSaveMasterGain = useCallback(async (gainDb: number): Promise<void> => {
    const nextGainDb = clampGainDb(gainDb);
    const updatedSettings = await patchSettings({ master_gain_db: nextGainDb });
    if (state.selectedChannelIds.size > 0) {
      await syncListening(orderedSelection(), state.modalScrubSeconds);
    }
    queryClient.setQueryData(['settings'], updatedSettings);
  }, [orderedSelection, patchSettings, queryClient, state.modalScrubSeconds, state.selectedChannelIds.size, syncListening]);

  const handleAddScene = useCallback(async (): Promise<void> => {
    const createdScene = await createScene({});
    dispatch({ type: 'setSetupTab', payload: 'scenes' });
    dispatch({ type: 'setActiveView', payload: 'setup' });
    dispatch({ type: 'setActiveSceneId', payload: createdScene.id });
    queryClient.setQueryData<SceneResponse[]>(['scenes'], (current = []) => sortScenes([...current, createdScene]));
    await patchSettings({
      active_scene_id: createdScene.id,
      active_mode: 'setup',
      scene_mode_enabled: false,
    });
    await queryClient.invalidateQueries({ queryKey: ['scenes'] });
  }, [dispatch, patchSettings, queryClient]);

  const handleSetActiveScene = useCallback(async (sceneId: number): Promise<void> => {
    dispatch({ type: 'setActiveSceneId', payload: sceneId });
    await patchSettings({ active_scene_id: sceneId });
  }, [dispatch, patchSettings]);

  const handleDeleteScene = useCallback(async (sceneId: number): Promise<void> => {
    await deleteScene(sceneId);
    const nextScenes = await queryClient.fetchQuery({ queryKey: ['scenes'], queryFn: listScenes });
    const nextActiveSceneId = resolveActiveSceneId(state.activeSceneId, nextScenes);
    dispatch({ type: 'setActiveSceneId', payload: nextActiveSceneId });
    await patchSettings({ active_scene_id: nextActiveSceneId });
  }, [dispatch, patchSettings, queryClient, state.activeSceneId]);

  const handleSaveSceneName = useCallback(async (sceneId: number, name: string): Promise<void> => {
    const updatedScene = await updateScene(sceneId, { name });
    queryClient.setQueryData<SceneResponse[]>(
      ['scenes'],
      (current = []) => current.map((scene) => (scene.id === sceneId ? updatedScene : scene)),
    );
  }, [queryClient]);

  const handleSaveSceneAssignments = useCallback(async (
    sceneId: number,
    assignments: SceneChannelAssignmentRequest[],
  ): Promise<void> => {
    const updatedScene = await updateScene(sceneId, { channel_assignments: assignments });
    queryClient.setQueryData<SceneResponse[]>(
      ['scenes'],
      (current = []) => current.map((scene) => (scene.id === sceneId ? updatedScene : scene)),
    );
  }, [queryClient]);

  const handleSaveSceneCueMapping = useCallback(async (
    sceneId: number,
    payload: Pick<SceneUpdateRequest, 'sync_osc_address' | 'sync_osc_argument' | 'sync_midi_pattern'>,
  ): Promise<void> => {
    const updatedScene = await updateScene(sceneId, payload);
    queryClient.setQueryData<SceneResponse[]>(
      ['scenes'],
      (current = []) => current.map((scene) => (scene.id === sceneId ? updatedScene : scene)),
    );
  }, [queryClient]);

  const handleSaveExternalSyncSettings = useCallback(async (
    payload: Pick<
      SettingsUpdateRequest,
      | 'external_sync_enabled'
      | 'external_sync_transport'
      | 'external_sync_osc_host'
      | 'external_sync_osc_port'
      | 'external_sync_midi_input_name'
    >,
  ): Promise<void> => {
    await patchSettings(payload);
    await queryClient.invalidateQueries({ queryKey: ['syncStatus'] });
  }, [patchSettings, queryClient]);

  const transportStatusText = getTransportStatusText(
    state.modalChannelId,
    state.selectedChannelIds,
    state.modalScrubSeconds,
  );

  return (
    <main className="app-shell">
      <Toolbar
        activeView={state.activeView}
        layoutMode={state.layoutMode}
        multiListen={state.multiListen}
        selectedCount={state.selectedChannelIds.size}
        statusText={state.statusText}
        activeSceneName={activeSceneName}
        showCheckedCount={sceneChecklistStats.checked}
        showTotalCount={sceneChecklistStats.total}
        canGoToPreviousScene={activeSceneIndex > 0}
        canGoToNextScene={activeSceneIndex !== -1 && activeSceneIndex < orderedScenes.length - 1}
        onSetActiveView={(view) => {
          void handleSetActiveView(view);
        }}
        onToggleListenMode={() => {
          void handleToggleListenMode();
        }}
        onToggleLayoutMode={handleToggleLayoutMode}
        onStopListening={() => {
          void handleStopListening();
        }}
        onNavigateScene={(offset) => {
          void handleNavigateScene(offset);
        }}
      />

      <section
        id="monitor-view"
        className={`view-panel monitor-panel ${state.activeView === 'setup' ? 'is-hidden' : ''} ${state.activeView === 'show' ? 'is-show-mode' : ''}`}
        ref={monitorViewRef}
      >
        <div className="monitor-workspace">
          <div className="channel-grid-shell">
            <ChannelGrid
              channels={channels}
              meterMap={meterMap}
              selectedChannelIds={state.selectedChannelIds}
              activeView={state.activeView}
              layoutMode={state.layoutMode}
              activeScene={activeScene}
              checklist={sceneChecklist}
              masterGainDb={settings?.master_gain_db ?? 0}
              onInteractChannel={(channelId) => {
                void handleChannelInteraction(channelId);
              }}
              onToggleChecklist={(channelId) => {
                handleToggleChecklist(channelId);
              }}
              onPersistOrder={handlePersistOrder}
              onCloseModal={() => dispatch({ type: 'closeModal' })}
            />
          </div>

          <ShowSidebar
            channels={channels}
            activeScene={activeScene}
            nextScene={nextScene}
            checklist={sceneChecklist}
            hidden={state.activeView !== 'show'}
            onToggleChecklist={(channelId) => {
              handleToggleChecklist(channelId);
            }}
          />
        </div>

        <section className="monitor-dock" aria-label="Channel inspector dock" ref={monitorDockRef}>
          <ChannelModal
            channel={modalChannel}
            visible={isMonitorLikeView && state.modalChannelId !== null}
            combinedGainDb={getCombinedGainDb(modalChannel, settings)}
            transportStatusText={transportStatusText}
            modalScrubSeconds={state.modalScrubSeconds}
            waveform={waveform}
            displayPoints={displayPoints}
            onClose={() => dispatch({ type: 'closeModal' })}
            onScrub={(replaySeconds) => {
              void handleScrubWaveform(replaySeconds);
            }}
          />
        </section>
      </section>

      <SetupView
        hidden={state.activeView !== 'setup'}
        setupTab={state.setupTab}
        settings={settings}
        syncStatus={syncStatus}
        channels={channels}
        scenes={scenes}
        activeSceneId={state.activeSceneId}
        onSetSetupTab={(tab) => dispatch({ type: 'setSetupTab', payload: tab })}
        onAddChannel={handleAddChannel}
        onSaveChannel={handleSaveChannel}
        onRemoveChannel={handleRemoveChannel}
        onSaveMasterGain={handleSaveMasterGain}
        onAddScene={handleAddScene}
        onSetActiveScene={handleSetActiveScene}
        onDeleteScene={handleDeleteScene}
        onSaveSceneName={handleSaveSceneName}
        onSaveSceneAssignments={handleSaveSceneAssignments}
        onSaveSceneCueMapping={handleSaveSceneCueMapping}
        onSaveExternalSyncSettings={handleSaveExternalSyncSettings}
      />

      <audio id="monitor-audio" className="sr-audio" autoPlay playsInline ref={audioElementRef}></audio>
    </main>
  );
}

export default function App(): JSX.Element {
  return <AppContent />;
}
