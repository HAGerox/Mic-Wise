import { useEffect, useMemo, useRef } from 'react';

import Sortable from 'sortablejs';

import { ChannelCard } from './ChannelCard';
import { dbToLinearGain, meterRatioFromLinear, linearToDbfs, sortChannels } from '../lib/format';
import { getShowChannelVisualState } from '../lib/ui-logic';
import type { AudioAlertResponse, ChannelResponse, MeterChannelSnapshot, SceneResponse } from '../types/api';
import type { ActiveView, ChannelCardState, ChannelStatusTone, ShowChannelVisualState } from '../types/ui';

function getSceneAssignmentState(scene: SceneResponse | null, channelId: number): string {
  if (!scene) {
    return 'off';
  }

  return scene.channel_assignments.find((assignment) => assignment.channel_id === channelId)?.state ?? 'off';
}

function getVisualState(
  activeView: ActiveView,
  activeScene: SceneResponse | null,
  checklist: Set<number>,
  channelId: number,
): ShowChannelVisualState | null {
  if (activeView !== 'show') {
    return null;
  }

  return getShowChannelVisualState(getSceneAssignmentState(activeScene, channelId), checklist.has(channelId));
}

function getStatusTone(
  visualState: ShowChannelVisualState | null,
  isSelected: boolean,
  activeAlert: AudioAlertResponse | null,
): ChannelStatusTone {
  if (activeAlert?.severity === 'critical') {
    return 'critical';
  }
  if (activeAlert?.severity === 'warning') {
    return 'warning';
  }
  if (visualState === 'off') {
    return 'muted';
  }
  if (isSelected) {
    return 'armed';
  }
  return 'live';
}

interface ChannelGridProps {
  channels: ChannelResponse[];
  meterMap: Map<number, MeterChannelSnapshot>;
  meterHistoryMap: Map<number, number[]>;
  activeAlertsByChannelId: Map<number, AudioAlertResponse>;
  selectedChannelIds: Set<number>;
  activeView: ActiveView;
  layoutMode: boolean;
  activeScene: SceneResponse | null;
  checklist: Set<number>;
  masterGainDb: number;
  onInteractChannel: (channelId: number) => void;
  onToggleChecklist: (channelId: number) => void;
  onPersistOrder: (orderedIds: number[]) => Promise<void>;
  onCloseModal: () => void;
}

export function ChannelGrid({
  channels,
  meterMap,
  meterHistoryMap,
  activeAlertsByChannelId,
  selectedChannelIds,
  activeView,
  layoutMode,
  activeScene,
  checklist,
  masterGainDb,
  onInteractChannel,
  onToggleChecklist,
  onPersistOrder,
  onCloseModal,
}: ChannelGridProps): JSX.Element {
  const gridRef = useRef<HTMLDivElement | null>(null);
  const sortableRef = useRef<Sortable | null>(null);

  const orderedChannels = useMemo(() => sortChannels(channels), [channels]);
  const cardStates = useMemo<ChannelCardState[]>(() => {
    return orderedChannels.map((channel) => {
      const meter = channel.input_index === null || channel.input_index === undefined
        ? null
        : meterMap.get(channel.input_index + 1) ?? null;
      const meterHistory = channel.input_index === null || channel.input_index === undefined
        ? []
        : meterHistoryMap.get(channel.input_index + 1) ?? [];
      const combinedGainLinear = dbToLinearGain((channel.gain_db ?? 0) + masterGainDb);
      const rmsLinear = meter ? Math.max(0, meter.rms * combinedGainLinear) : 0;
      const peakLinear = meter ? Math.max(rmsLinear, meter.peak * combinedGainLinear) : 0;
      const historyRatios = meterHistory.map((value) => meterRatioFromLinear(value * combinedGainLinear));
      const visualState = getVisualState(activeView, activeScene, checklist, channel.id);
      const activeAlert = activeAlertsByChannelId.get(channel.id) ?? null;
      const isSelected = selectedChannelIds.has(channel.id);

      return {
        channel,
        metrics: {
          rmsLinear,
          peakLinear,
          rmsDbfs: linearToDbfs(rmsLinear),
          peakDbfs: linearToDbfs(peakLinear),
          rmsRatio: meterRatioFromLinear(rmsLinear),
          peakRatio: meterRatioFromLinear(peakLinear),
          historyRatios,
        },
        activeAlert,
        isSelected,
        isLayoutMode: layoutMode,
        isShowMode: activeView === 'show',
        visualState,
        statusTone: getStatusTone(visualState, isSelected, activeAlert),
      };
    });
  }, [
    activeAlertsByChannelId,
    activeScene,
    activeView,
    checklist,
    layoutMode,
    masterGainDb,
    meterHistoryMap,
    meterMap,
    orderedChannels,
    selectedChannelIds,
  ]);

  useEffect(() => {
    const gridElement = gridRef.current;
    if (!gridElement) {
      return undefined;
    }

    if (!sortableRef.current) {
      sortableRef.current = Sortable.create(gridElement, {
        animation: 120,
        easing: 'cubic-bezier(0.2, 0.9, 0.2, 1)',
        draggable: '.channel-card',
        dataIdAttr: 'data-channel-id',
        ghostClass: 'channel-card--ghost',
        chosenClass: 'channel-card--chosen',
        dragClass: 'channel-card--dragging',
        fallbackClass: 'channel-card--fallback',
        forceFallback: true,
        fallbackOnBody: false,
        fallbackTolerance: 4,
        swapThreshold: 0.72,
        invertedSwapThreshold: 0.78,
        touchStartThreshold: 4,
        disabled: !layoutMode || activeView !== 'monitor',
        onStart: () => {
          onCloseModal();
        },
        onEnd: async (event) => {
          const orderedIds = Array.from(event.to.children)
            .map((child) => Number((child as HTMLElement).dataset.channelId ?? Number.NaN))
            .filter(Number.isInteger);
          await onPersistOrder(orderedIds);
        },
      });
    }

    sortableRef.current.option('disabled', !layoutMode || activeView !== 'monitor');

    return () => {
      if (sortableRef.current) {
        sortableRef.current.option('disabled', true);
      }
    };
  }, [activeView, layoutMode, onCloseModal, onPersistOrder]);

  useEffect(() => () => {
    sortableRef.current?.destroy();
    sortableRef.current = null;
  }, []);

  return (
    <div id="channel-grid" className="channel-grid" ref={gridRef}>
      {cardStates.map((cardState) => (
        <ChannelCard
          key={cardState.channel.id}
          state={cardState}
          onInteract={onInteractChannel}
          onToggleChecklist={onToggleChecklist}
        />
      ))}
    </div>
  );
}
