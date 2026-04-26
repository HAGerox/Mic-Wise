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
  checkedCount: number;
  totalCount: number;
  canGoToPreviousScene: boolean;
  canGoToNextScene: boolean;
  hidden: boolean;
  onNavigateScene: (offset: number) => void;
  onToggleChecklist: (channelId: number) => void;
  onResetChecklist: () => void;
}

export function ShowSidebar({
  channels,
  activeScene,
  nextScene,
  checklist,
  checkedCount,
  totalCount,
  canGoToPreviousScene,
  canGoToNextScene,
  hidden,
  onNavigateScene,
  onToggleChecklist,
  onResetChecklist,
}: ShowSidebarProps): JSX.Element {
  const sceneChannels = sortChannels(channels)
    .map((channel) => {
      const sceneState = getSceneAssignmentState(activeScene, channel.id);
      if (sceneState === 'off') {
        return null;
      }

      const visualState = getShowChannelVisualState(sceneState, checklist.has(channel.id));
      return {
        channel,
        sceneState,
        visualState,
      };
    })
    .filter((entry): entry is NonNullable<typeof entry> => Boolean(entry));

  return (
    <aside id="show-sidebar" className={`show-sidebar ${hidden ? 'is-hidden' : ''}`} aria-label="Show mode mic check">
      <section className="show-scene-card">
        <div className="show-scene-copy">
          <span className="show-sidebar-eyebrow">Show mode</span>
          <h2>{activeScene ? activeScene.name : 'No active scene'}</h2>
          <p id="show-scene-summary" className="show-scene-summary">
            {activeScene ? getSceneSummary(activeScene) : 'Choose or create a scene in setup to start a mic check.'}
          </p>
        </div>
        <div className="show-scene-progress">
          <span>Checklist</span>
          <strong>{checkedCount}/{totalCount}</strong>
          <small>{Math.max(totalCount - checkedCount, 0)} remaining</small>
        </div>
      </section>

      <section className="show-navigator" aria-label="Scene navigation">
        <button
          type="button"
          className="secondary icon-button"
          aria-label="Previous scene"
          disabled={!canGoToPreviousScene}
          onClick={() => onNavigateScene(-1)}
        >
          ‹
        </button>
        <div className="show-navigator-copy">
          <span className="show-sidebar-eyebrow">Next cue</span>
          <strong>{nextScene ? nextScene.name : 'End of show'}</strong>
          <span>{nextScene ? getSceneSummary(nextScene) : 'No further scenes queued.'}</span>
        </div>
        <button
          type="button"
          className="show-next-button"
          aria-label="Advance to next scene"
          disabled={!canGoToNextScene}
          onClick={() => onNavigateScene(1)}
        >
          Next scene
        </button>
      </section>

      <section className="show-sidebar-note">
        <div className="show-legend" aria-label="Show mode colour legend">
          <span className="show-legend-item is-checked">Checked</span>
          <span className="show-legend-item is-pending">Ready</span>
          <span className="show-legend-item is-off">Muted</span>
        </div>
        <p className="show-shortcuts">Press <strong>Y</strong> to mark checked, <strong>N</strong> to reopen, or hold a strip to toggle it.</p>
        <button type="button" className="secondary show-reset-button" onClick={onResetChecklist}>Reset all checks</button>
      </section>

      {sceneChannels.length === 0 ? (
        <div className="show-empty-state">
          <strong>No channels in this scene</strong>
          <span>Assign channels in setup and they will appear here as a clean mic-check list.</span>
        </div>
      ) : (
        <div id="show-list" className="show-list">
          {sceneChannels.map(({ channel, sceneState, visualState }) => (
            <button
              key={channel.id}
              type="button"
              className={`show-list-item is-${visualState}`}
              onClick={() => onToggleChecklist(channel.id)}
            >
              <span className="show-list-channel">CH {channel.number}</span>
              <span className="show-list-name">
                <strong>{channel.name}</strong>
                <small>{sceneState === 'onstage' ? 'Live in current scene' : 'About to enter'}</small>
              </span>
              <span className="show-list-state">{visualState === 'checked' ? 'Checked' : 'Ready'}</span>
            </button>
          ))}
        </div>
      )}
    </aside>
  );
}
