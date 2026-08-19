import { useEffect, useMemo, useRef } from 'react';

import Sortable from 'sortablejs';

import { ChannelCard } from './ChannelCard';
import { dbToLinearGain, meterRatioFromLinear, linearToDbfs, sortChannels } from '../lib/format';
import { getShowChannelVisualState } from '../lib/ui-logic';
import type { AudioAlertResponse, ChannelResponse, MeterChannelSnapshot, SceneResponse } from '../types/api';
import type { ActiveView, ChannelCardState, ChannelSelectionModifiers, ChannelStatusTone, ShowChannelVisualState } from '../types/ui';

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
  activeScene: SceneResponse | null;
  checklist: Set<number>;
  masterGainDb: number;
  onInteractChannel: (channelId: number, modifiers: ChannelSelectionModifiers) => void;
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
  const onCloseModalRef = useRef(onCloseModal);
  const onPersistOrderRef = useRef(onPersistOrder);

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
        canReorder: activeView === 'monitor',
        visualState,
        statusTone: getStatusTone(visualState, isSelected, activeAlert),
      };
    });
  }, [
    activeAlertsByChannelId,
    activeScene,
    activeView,
    checklist,
    masterGainDb,
    meterHistoryMap,
    meterMap,
    orderedChannels,
    selectedChannelIds,
  ]);

  useEffect(() => {
    onCloseModalRef.current = onCloseModal;
    onPersistOrderRef.current = onPersistOrder;
  }, [onCloseModal, onPersistOrder]);

  useEffect(() => {
    const gridElement = gridRef.current;
    if (!gridElement) {
      return undefined;
    }

    if (!sortableRef.current) {
      sortableRef.current = Sortable.create(gridElement, {
        animation: 180,
        easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
        draggable: '.channel-card',
        handle: '.channel-reorder-handle',
        dataIdAttr: 'data-channel-id',
        ghostClass: 'channel-card--ghost',
        chosenClass: 'channel-card--chosen',
        dragClass: 'channel-card--dragging',
        fallbackClass: 'channel-card--fallback',
        forceFallback: true,
        fallbackOnBody: true,
        fallbackTolerance: 4,
        swapThreshold: 0.72,
        invertedSwapThreshold: 0.78,
        touchStartThreshold: 4,
        disabled: activeView !== 'monitor',
        onChoose: () => {
          gridElement.classList.add('is-reordering');
        },
        onUnchoose: () => {
          gridElement.classList.remove('is-reordering');
        },
        onStart: () => {
          onCloseModalRef.current();
        },
        onEnd: async () => {
          const orderedIds = sortableRef.current?.toArray().map(Number) ?? [];
          try {
            await onPersistOrderRef.current(orderedIds);
          } finally {
            gridElement.classList.remove('is-reordering');
          }
        },
      });
    }

    sortableRef.current.option('disabled', activeView !== 'monitor');

    return () => {
      if (sortableRef.current) {
        sortableRef.current.option('disabled', true);
      }
    };
  }, [activeView]);

  useEffect(() => () => {
    gridRef.current?.classList.remove('is-reordering');
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
