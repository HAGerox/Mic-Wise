import { useEffect, useMemo, useRef } from 'react';

import Sortable from 'sortablejs';

import { ChannelCard } from './ChannelCard';
import { dbToLinearGain, sortChannels } from '../lib/format';
import { getShowChannelVisualState } from '../lib/ui-logic';
import type { ChannelResponse, MeterChannelSnapshot, SceneResponse } from '../types/api';
import type { ActiveView, ShowChannelVisualState } from '../types/ui';

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

interface ChannelGridProps {
  channels: ChannelResponse[];
  meterMap: Map<number, MeterChannelSnapshot>;
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
        disabled: !layoutMode || activeView !== 'monitor',
        onStart: () => {
          onCloseModal();
        },
        onEnd: async () => {
          const orderedIds = sortableRef.current?.toArray().map(Number) ?? [];
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
      {orderedChannels.map((channel) => {
        const meter = channel.input_index === null || channel.input_index === undefined
          ? null
          : meterMap.get(channel.input_index + 1) ?? null;
        const combinedGainLinear = dbToLinearGain((channel.gain_db ?? 0) + masterGainDb);
        const level = meter ? Math.min(meter.rms * combinedGainLinear * 100, 100) : 0;
        const visualState = getVisualState(activeView, activeScene, checklist, channel.id);

        return (
          <ChannelCard
            key={channel.id}
            channel={channel}
            level={level}
            isSelected={selectedChannelIds.has(channel.id)}
            isLayoutMode={layoutMode}
            isShowMode={activeView === 'show'}
            visualState={visualState}
            onInteract={onInteractChannel}
            onToggleChecklist={onToggleChecklist}
          />
        );
      })}
    </div>
  );
}
