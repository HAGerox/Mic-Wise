import { getShowChannelVisualState } from '../lib/ui-logic';
import { sortChannels } from '../lib/format';
import type { ChannelResponse, SceneResponse } from '../types/api';

function getSceneSummary(scene: SceneResponse | null): string {
  const assignments = scene?.channel_assignments ?? [];
  const onstageCount = assignments.filter((assignment) => assignment.state === 'onstage').length;
  const readyCount = assignments.filter((assignment) => assignment.state === 'ready').length;
  return `${onstageCount} on stage • ${readyCount} about to enter`;
}

function getSceneAssignmentState(scene: SceneResponse | null, channelId: number): string {
  if (!scene) {
    return 'off';
  }

  return scene.channel_assignments.find((assignment) => assignment.channel_id === channelId)?.state ?? 'off';
}

interface ShowSidebarProps {
  channels: ChannelResponse[];
  activeScene: SceneResponse | null;
  nextScene: SceneResponse | null;
  checklist: Set<number>;
  hidden: boolean;
  onToggleChecklist: (channelId: number) => void;
}

export function ShowSidebar({
  channels,
  activeScene,
  nextScene,
  checklist,
  hidden,
  onToggleChecklist,
}: ShowSidebarProps): JSX.Element {
  return (
    <aside id="show-sidebar" className={`show-sidebar ${hidden ? 'is-hidden' : ''}`} aria-label="Show mode mic check">
      <div className="show-sidebar-header">
        <div>
          <h2>Mic check</h2>
          <p id="show-scene-summary" className="show-scene-summary">
            {activeScene ? getSceneSummary(activeScene) : 'No active scene selected yet.'}
          </p>
        </div>
        <p id="show-next-scene" className="show-next-scene">{nextScene ? `Next: ${nextScene.name}` : 'Next: —'}</p>
      </div>

      <div className="show-legend" aria-label="Show mode colour legend">
        <span className="show-legend-item is-checked">Green · checked</span>
        <span className="show-legend-item is-pending">Red · pending</span>
        <span className="show-legend-item is-off">Grey · not in scene</span>
      </div>

      <p className="show-shortcuts">Press <strong>Y</strong> to check, <strong>N</strong> to undo, or hold a channel card to toggle it.</p>

      <div id="show-list" className="show-list">
        {sortChannels(channels).map((channel) => {
          const sceneState = getSceneAssignmentState(activeScene, channel.id);
          const visualState = getShowChannelVisualState(sceneState, checklist.has(channel.id));
          return (
            <button
              key={channel.id}
              type="button"
              className={`show-list-item is-${visualState}`}
              disabled={sceneState === 'off'}
              onClick={() => onToggleChecklist(channel.id)}
            >
              <span className="show-list-channel">CH {channel.number}</span>
              <span className="show-list-name">{channel.name}</span>
              <span className="show-list-state">
                {sceneState === 'off' ? 'Not in scene' : visualState === 'checked' ? 'Checked' : 'Pending'}
              </span>
            </button>
          );
        })}
      </div>
    </aside>
  );
}
