import { useEffect, useMemo, useRef, useState } from 'react';

import { buildExternalSyncStatusText } from '../lib/ui-logic';
import { clampGainDb, sortChannels, sortScenes } from '../lib/format';
import type {
  ChannelResponse,
  ChannelUpdateRequest,
  SceneChannelAssignmentRequest,
  SceneResponse,
  SceneSyncStatusResponse,
  SceneUpdateRequest,
  SettingsResponse,
  SettingsUpdateRequest,
} from '../types/api';
import type { ExternalSyncFormState, ProgramChannelDraft, SetupTab } from '../types/ui';

const PROGRAM_AUTOSAVE_DELAY_MS = 450;

function getSceneSummary(scene: SceneResponse | null): string {
  const assignments = scene?.channel_assignments ?? [];
  const onstageCount = assignments.filter((assignment) => assignment.state === 'onstage').length;
  const readyCount = assignments.filter((assignment) => assignment.state === 'ready').length;
  return `${onstageCount} on stage • ${readyCount} about to enter`;
}

function toProgramDraft(channel: ChannelResponse): ProgramChannelDraft {
  return {
    name: channel.name,
    input_index: channel.input_index,
    gain_db: clampGainDb(channel.gain_db ?? 0),
    is_record_enabled: channel.is_record_enabled,
  };
}

interface ProgramRowProps {
  channel: ChannelResponse;
  availableInputCount: number;
  onSave: (channelId: number, payload: ChannelUpdateRequest) => Promise<void>;
  onRemove: (channelId: number) => Promise<void>;
}

function ProgramRow({ channel, availableInputCount, onSave, onRemove }: ProgramRowProps): JSX.Element {
  const [draft, setDraft] = useState<ProgramChannelDraft>(() => toProgramDraft(channel));
  const timerRef = useRef<number | null>(null);

  useEffect(() => {
    setDraft(toProgramDraft(channel));
  }, [channel]);

  useEffect(() => () => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
    }
  }, []);

  const scheduleSave = (nextDraft: ProgramChannelDraft, delay = PROGRAM_AUTOSAVE_DELAY_MS): void => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
    }
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null;
      void onSave(channel.id, nextDraft);
    }, delay);
  };

  const commitSave = (nextDraft = draft): void => {
    if (timerRef.current !== null) {
      window.clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    void onSave(channel.id, nextDraft);
  };

  return (
    <tr data-channel-id={String(channel.id)}>
      <td>CH {channel.number}</td>
      <td>
        <div className="program-name-field">
          <input
            type="text"
            data-field="name"
            value={draft.name}
            onChange={(event) => {
              const nextDraft = { ...draft, name: event.target.value };
              setDraft(nextDraft);
              scheduleSave(nextDraft);
            }}
            onBlur={() => commitSave()}
          />
        </div>
      </td>
      <td>
        <select
          data-field="input_index"
          value={draft.input_index ?? ''}
          onChange={(event) => {
            const nextDraft = {
              ...draft,
              input_index: event.target.value === '' ? null : Number(event.target.value),
            };
            setDraft(nextDraft);
            scheduleSave(nextDraft, 0);
          }}
        >
          <option value="">Unpatched</option>
          {Array.from({ length: availableInputCount }, (_, index) => index).map((index) => (
            <option key={index} value={index}>Input {index + 1}</option>
          ))}
        </select>
      </td>
      <td>
        <div className="gain-input-field">
          <input
            type="number"
            data-field="gain_db"
            min={-24}
            max={24}
            step={1}
            value={draft.gain_db}
            onChange={(event) => {
              const nextDraft = {
                ...draft,
                gain_db: clampGainDb(Number(event.target.value)),
              };
              setDraft(nextDraft);
              scheduleSave(nextDraft, 0);
            }}
            onBlur={() => {
              const nextDraft = {
                ...draft,
                gain_db: clampGainDb(Number(draft.gain_db)),
              };
              setDraft(nextDraft);
              commitSave(nextDraft);
            }}
          />
          <span>dB</span>
        </div>
      </td>
      <td className="checkbox-cell">
        <label className="record-toggle" aria-label="Rolling record enabled">
          <input
            type="checkbox"
            data-field="is_record_enabled"
            checked={draft.is_record_enabled}
            onChange={(event) => {
              const nextDraft = {
                ...draft,
                is_record_enabled: event.target.checked,
              };
              setDraft(nextDraft);
              scheduleSave(nextDraft, 0);
            }}
          />
          <span className="record-toggle-ui" aria-hidden="true"></span>
        </label>
      </td>
      <td>
        <button type="button" className="button-danger" onClick={() => void onRemove(channel.id)}>Remove</button>
      </td>
    </tr>
  );
}

interface SetupViewProps {
  hidden: boolean;
  setupTab: SetupTab;
  settings: SettingsResponse | null;
  syncStatus: SceneSyncStatusResponse | null;
  channels: ChannelResponse[];
  scenes: SceneResponse[];
  activeSceneId: number | null;
  onSetSetupTab: (tab: SetupTab) => void;
  onAddChannel: () => Promise<void>;
  onSaveChannel: (channelId: number, payload: ChannelUpdateRequest) => Promise<void>;
  onRemoveChannel: (channelId: number) => Promise<void>;
  onSaveMasterGain: (gainDb: number) => Promise<void>;
  onAddScene: () => Promise<void>;
  onSetActiveScene: (sceneId: number) => Promise<void>;
  onDeleteScene: (sceneId: number) => Promise<void>;
  onSaveSceneName: (sceneId: number, name: string) => Promise<void>;
  onSaveSceneAssignments: (
    sceneId: number,
    assignments: SceneChannelAssignmentRequest[],
  ) => Promise<void>;
  onSaveSceneCueMapping: (
    sceneId: number,
    payload: Pick<SceneUpdateRequest, 'sync_osc_address' | 'sync_osc_argument' | 'sync_midi_pattern'>,
  ) => Promise<void>;
  onSaveExternalSyncSettings: (
    payload: Pick<
      SettingsUpdateRequest,
      | 'external_sync_enabled'
      | 'external_sync_transport'
      | 'external_sync_osc_host'
      | 'external_sync_osc_port'
      | 'external_sync_midi_input_name'
    >,
  ) => Promise<void>;
}

export function SetupView({
  hidden,
  setupTab,
  settings,
  syncStatus,
  channels,
  scenes,
  activeSceneId,
  onSetSetupTab,
  onAddChannel,
  onSaveChannel,
  onRemoveChannel,
  onSaveMasterGain,
  onAddScene,
  onSetActiveScene,
  onDeleteScene,
  onSaveSceneName,
  onSaveSceneAssignments,
  onSaveSceneCueMapping,
  onSaveExternalSyncSettings,
}: SetupViewProps): JSX.Element {
  const orderedChannels = useMemo(() => sortChannels(channels), [channels]);
  const orderedScenes = useMemo(() => sortScenes(scenes), [scenes]);
  const activeScene = useMemo(
    () => orderedScenes.find((scene) => scene.id === activeSceneId) ?? null,
    [activeSceneId, orderedScenes],
  );

  const [masterGainValue, setMasterGainValue] = useState('0');
  const [externalSyncForm, setExternalSyncForm] = useState<ExternalSyncFormState>({
    external_sync_enabled: false,
    external_sync_transport: 'off',
    external_sync_osc_host: '0.0.0.0',
    external_sync_osc_port: 53001,
    external_sync_midi_input_name: '',
  });
  const [sceneName, setSceneName] = useState('');
  const [sceneCueForm, setSceneCueForm] = useState({
    sync_osc_address: '',
    sync_osc_argument: '',
    sync_midi_pattern: '',
  });
  const [sceneAssignments, setSceneAssignments] = useState<Record<number, string>>({});

  useEffect(() => {
    setMasterGainValue(String(clampGainDb(Number(settings?.master_gain_db ?? 0))));
    setExternalSyncForm({
      external_sync_enabled: Boolean(settings?.external_sync_enabled),
      external_sync_transport: settings?.external_sync_transport ?? 'off',
      external_sync_osc_host: settings?.external_sync_osc_host ?? '0.0.0.0',
      external_sync_osc_port: settings?.external_sync_osc_port ?? 53001,
      external_sync_midi_input_name: settings?.external_sync_midi_input_name ?? '',
    });
  }, [settings]);

  useEffect(() => {
    setSceneName(activeScene?.name ?? '');
    setSceneCueForm({
      sync_osc_address: activeScene?.sync_osc_address ?? '',
      sync_osc_argument: activeScene?.sync_osc_argument ?? '',
      sync_midi_pattern: activeScene?.sync_midi_pattern ?? '',
    });
    setSceneAssignments(
      Object.fromEntries((activeScene?.channel_assignments ?? []).map((assignment) => [assignment.channel_id, assignment.state])),
    );
  }, [activeScene]);

  return (
    <section id="setup-view" className={`view-panel ${hidden ? 'is-hidden' : ''}`}>
      <div className="panel-heading">
        <div>
          <h2>Show setup</h2>
          <p>Program show file metadata, build scenes, and configure optional external cue sync.</p>
        </div>
        <div className="panel-heading-actions">
          <div className="control-group segmented-control compact-segmented" role="tablist" aria-label="Setup sections">
            <button
              id="setup-tab-program"
              className={`segment-button ${setupTab === 'program' ? 'is-active' : ''}`}
              type="button"
              onClick={() => onSetSetupTab('program')}
            >
              Channels
            </button>
            <button
              id="setup-tab-scenes"
              className={`segment-button ${setupTab === 'scenes' ? 'is-active' : ''}`}
              type="button"
              onClick={() => onSetSetupTab('scenes')}
            >
              Scenes
            </button>
          </div>
        </div>
      </div>

      <section id="setup-program-panel" className={`setup-panel ${setupTab === 'program' ? '' : 'is-hidden'}`}>
        <div className="panel-heading panel-heading--nested">
          <div>
            <h3>Channel programming</h3>
            <p>Patch inputs, rename channels, and manage trim and rolling record from one place.</p>
          </div>
          <div className="panel-heading-actions">
            <label className="compact-setting" htmlFor="master-gain-input">
              <span>Master trim</span>
              <div className="compact-setting-input">
                <input
                  id="master-gain-input"
                  type="number"
                  min={-24}
                  max={24}
                  step={1}
                  value={masterGainValue}
                  onChange={(event) => {
                    const nextValue = String(clampGainDb(Number(event.target.value)));
                    setMasterGainValue(nextValue);
                    void onSaveMasterGain(Number(nextValue));
                  }}
                  onBlur={() => {
                    const nextValue = String(clampGainDb(Number(masterGainValue)));
                    setMasterGainValue(nextValue);
                    void onSaveMasterGain(Number(nextValue));
                  }}
                />
                <span>dB</span>
              </div>
            </label>
            <button id="add-channel" type="button" onClick={() => void onAddChannel()}>Add channel</button>
          </div>
        </div>

        <div className="table-shell">
          <table className="program-table">
            <thead>
              <tr>
                <th>Channel</th>
                <th>Name</th>
                <th>Input</th>
                <th>Trim</th>
                <th>Record</th>
                <th>Remove</th>
              </tr>
            </thead>
            <tbody id="program-table-body">
              {orderedChannels.map((channel) => (
                <ProgramRow
                  key={channel.id}
                  channel={channel}
                  availableInputCount={Math.max(settings?.channel_count ?? 0, 0)}
                  onSave={onSaveChannel}
                  onRemove={onRemoveChannel}
                />
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section id="setup-scenes-panel" className={`setup-panel ${setupTab === 'scenes' ? '' : 'is-hidden'}`}>
        <div className="panel-heading panel-heading--nested">
          <div>
            <h3>Scene programming</h3>
            <p>Choose who is on stage, who is about to enter, and optionally map scenes to external cues.</p>
          </div>
          <div className="panel-heading-actions">
            <button id="add-scene" type="button" onClick={() => void onAddScene()}>Add scene</button>
          </div>
        </div>

        <section className="scene-sync-settings-panel">
          <div>
            <h3>External scene sync</h3>
            <p>Optional QLab / desk integration. It stays off until you enable it and map cues to scenes.</p>
          </div>

          <div className="scene-sync-settings-grid">
            <label className="field-group field-group--toggle" htmlFor="external-sync-enabled">
              <span>Enabled</span>
              <input
                id="external-sync-enabled"
                type="checkbox"
                checked={externalSyncForm.external_sync_enabled}
                onChange={(event) => {
                  const nextForm = { ...externalSyncForm, external_sync_enabled: event.target.checked };
                  setExternalSyncForm(nextForm);
                  void onSaveExternalSyncSettings({
                    external_sync_enabled: nextForm.external_sync_enabled,
                    external_sync_transport: nextForm.external_sync_transport,
                    external_sync_osc_host: nextForm.external_sync_osc_host,
                    external_sync_osc_port: nextForm.external_sync_osc_port,
                    external_sync_midi_input_name: nextForm.external_sync_midi_input_name || null,
                  });
                }}
              />
            </label>
            <label className="field-group" htmlFor="external-sync-transport">
              <span>Transport</span>
              <select
                id="external-sync-transport"
                value={externalSyncForm.external_sync_transport}
                onChange={(event) => {
                  const nextForm = {
                    ...externalSyncForm,
                    external_sync_transport: event.target.value as ExternalSyncFormState['external_sync_transport'],
                  };
                  setExternalSyncForm(nextForm);
                  void onSaveExternalSyncSettings({
                    external_sync_enabled: nextForm.external_sync_enabled,
                    external_sync_transport: nextForm.external_sync_transport,
                    external_sync_osc_host: nextForm.external_sync_osc_host,
                    external_sync_osc_port: nextForm.external_sync_osc_port,
                    external_sync_midi_input_name: nextForm.external_sync_midi_input_name || null,
                  });
                }}
              >
                <option value="off">Disabled</option>
                <option value="osc">OSC</option>
                <option value="midi">MIDI</option>
                <option value="both">OSC + MIDI</option>
              </select>
            </label>
            <label className="field-group" htmlFor="external-sync-osc-host">
              <span>OSC host</span>
              <input
                id="external-sync-osc-host"
                type="text"
                value={externalSyncForm.external_sync_osc_host}
                placeholder="0.0.0.0"
                onChange={(event) => {
                  setExternalSyncForm({ ...externalSyncForm, external_sync_osc_host: event.target.value });
                }}
                onBlur={() => {
                  void onSaveExternalSyncSettings({
                    external_sync_enabled: externalSyncForm.external_sync_enabled,
                    external_sync_transport: externalSyncForm.external_sync_transport,
                    external_sync_osc_host: externalSyncForm.external_sync_osc_host.trim() || '0.0.0.0',
                    external_sync_osc_port: externalSyncForm.external_sync_osc_port,
                    external_sync_midi_input_name: externalSyncForm.external_sync_midi_input_name || null,
                  });
                }}
              />
            </label>
            <label className="field-group" htmlFor="external-sync-osc-port">
              <span>OSC port</span>
              <input
                id="external-sync-osc-port"
                type="number"
                min={0}
                max={65535}
                step={1}
                value={externalSyncForm.external_sync_osc_port}
                placeholder="53001"
                onChange={(event) => {
                  setExternalSyncForm({
                    ...externalSyncForm,
                    external_sync_osc_port: Number(event.target.value || 53001),
                  });
                }}
                onBlur={() => {
                  void onSaveExternalSyncSettings({
                    external_sync_enabled: externalSyncForm.external_sync_enabled,
                    external_sync_transport: externalSyncForm.external_sync_transport,
                    external_sync_osc_host: externalSyncForm.external_sync_osc_host.trim() || '0.0.0.0',
                    external_sync_osc_port: Number(externalSyncForm.external_sync_osc_port || 53001),
                    external_sync_midi_input_name: externalSyncForm.external_sync_midi_input_name || null,
                  });
                }}
              />
            </label>
            <label className="field-group" htmlFor="external-sync-midi-input-name">
              <span>MIDI input name</span>
              <input
                id="external-sync-midi-input-name"
                type="text"
                value={externalSyncForm.external_sync_midi_input_name}
                placeholder="IAC Driver Bus 1"
                onChange={(event) => {
                  setExternalSyncForm({ ...externalSyncForm, external_sync_midi_input_name: event.target.value });
                }}
                onBlur={() => {
                  void onSaveExternalSyncSettings({
                    external_sync_enabled: externalSyncForm.external_sync_enabled,
                    external_sync_transport: externalSyncForm.external_sync_transport,
                    external_sync_osc_host: externalSyncForm.external_sync_osc_host.trim() || '0.0.0.0',
                    external_sync_osc_port: externalSyncForm.external_sync_osc_port,
                    external_sync_midi_input_name: externalSyncForm.external_sync_midi_input_name.trim() || null,
                  });
                }}
              />
            </label>
          </div>

          <p id="external-sync-status" className="scene-sync-status">{buildExternalSyncStatusText(syncStatus)}</p>
        </section>

        <div className="scenes-layout">
          <aside className="scene-list-panel">
            <div id="scene-list" className="scene-list">
              {orderedScenes.map((scene) => (
                <button
                  key={scene.id}
                  type="button"
                  className={`scene-list-item ${scene.id === activeSceneId ? 'is-active' : ''}`}
                  onClick={() => void onSetActiveScene(scene.id)}
                >
                  <strong>{scene.name}</strong>
                  <span>{getSceneSummary(scene)}</span>
                </button>
              ))}
            </div>
          </aside>

          <section className="scene-editor-panel">
            <div id="scene-empty-state" className={`scene-empty-state ${activeScene ? 'is-hidden' : ''}`}>
              <strong>No scene selected</strong>
              <span>Add a scene to start programming who is on stage and who is about to enter.</span>
            </div>

            <div id="scene-detail" className={`scene-detail ${activeScene ? '' : 'is-hidden'}`}>
              <div className="scene-detail-header">
                <label className="scene-name-field" htmlFor="scene-name-input">
                  <span>Scene name</span>
                  <input
                    id="scene-name-input"
                    type="text"
                    value={sceneName}
                    onChange={(event) => setSceneName(event.target.value)}
                    onBlur={() => {
                      if (activeScene) {
                        void onSaveSceneName(activeScene.id, sceneName.trim() || activeScene.name);
                      }
                    }}
                  />
                </label>
                <div className="scene-detail-actions">
                  <button
                    id="delete-scene"
                    className="button-danger"
                    type="button"
                    disabled={!activeScene}
                    onClick={() => {
                      if (activeScene) {
                        void onDeleteScene(activeScene.id);
                      }
                    }}
                  >
                    Delete scene
                  </button>
                </div>
              </div>

              <p id="scene-detail-summary" className="scene-detail-summary">{getSceneSummary(activeScene)}</p>

              <section className="scene-sync-card">
                <div>
                  <h3>Scene cue mapping</h3>
                  <p>Optional exact-match cues for external sync.</p>
                </div>
                <div className="scene-sync-grid">
                  <label className="field-group" htmlFor="scene-sync-osc-address">
                    <span>OSC address</span>
                    <input
                      id="scene-sync-osc-address"
                      type="text"
                      value={sceneCueForm.sync_osc_address}
                      placeholder="/qlab/scene/2"
                      onChange={(event) => {
                        setSceneCueForm({ ...sceneCueForm, sync_osc_address: event.target.value });
                      }}
                      onBlur={() => {
                        if (activeScene) {
                          void onSaveSceneCueMapping(activeScene.id, {
                            sync_osc_address: sceneCueForm.sync_osc_address.trim() || null,
                            sync_osc_argument: sceneCueForm.sync_osc_argument.trim() || null,
                            sync_midi_pattern: sceneCueForm.sync_midi_pattern.trim() || null,
                          });
                        }
                      }}
                    />
                  </label>
                  <label className="field-group" htmlFor="scene-sync-osc-argument">
                    <span>OSC first argument</span>
                    <input
                      id="scene-sync-osc-argument"
                      type="text"
                      value={sceneCueForm.sync_osc_argument}
                      placeholder="GO"
                      onChange={(event) => {
                        setSceneCueForm({ ...sceneCueForm, sync_osc_argument: event.target.value });
                      }}
                      onBlur={() => {
                        if (activeScene) {
                          void onSaveSceneCueMapping(activeScene.id, {
                            sync_osc_address: sceneCueForm.sync_osc_address.trim() || null,
                            sync_osc_argument: sceneCueForm.sync_osc_argument.trim() || null,
                            sync_midi_pattern: sceneCueForm.sync_midi_pattern.trim() || null,
                          });
                        }
                      }}
                    />
                  </label>
                  <label className="field-group" htmlFor="scene-sync-midi-pattern">
                    <span>MIDI pattern</span>
                    <input
                      id="scene-sync-midi-pattern"
                      type="text"
                      value={sceneCueForm.sync_midi_pattern}
                      placeholder="program_change:12"
                      onChange={(event) => {
                        setSceneCueForm({ ...sceneCueForm, sync_midi_pattern: event.target.value });
                      }}
                      onBlur={() => {
                        if (activeScene) {
                          void onSaveSceneCueMapping(activeScene.id, {
                            sync_osc_address: sceneCueForm.sync_osc_address.trim() || null,
                            sync_osc_argument: sceneCueForm.sync_osc_argument.trim() || null,
                            sync_midi_pattern: sceneCueForm.sync_midi_pattern.trim() || null,
                          });
                        }
                      }}
                    />
                  </label>
                </div>
              </section>

              <div className="table-shell">
                <table className="program-table scene-table">
                  <thead>
                    <tr>
                      <th>Channel</th>
                      <th>Name</th>
                      <th>Scene status</th>
                    </tr>
                  </thead>
                  <tbody id="scene-table-body">
                    {orderedChannels.map((channel) => {
                      const sceneState = sceneAssignments[channel.id] ?? 'off';
                      return (
                        <tr key={channel.id} data-channel-id={String(channel.id)} className={`scene-row is-${sceneState}`}>
                          <td>CH {channel.number}</td>
                          <td>{channel.name}</td>
                          <td>
                            <select
                              className="scene-state-select"
                              data-field="scene_state"
                              value={sceneState}
                              onChange={(event) => {
                                if (!activeScene) {
                                  return;
                                }
                                const nextAssignments = {
                                  ...sceneAssignments,
                                  [channel.id]: event.target.value,
                                };
                                setSceneAssignments(nextAssignments);
                                const payload: SceneChannelAssignmentRequest[] = orderedChannels.map((orderedChannel) => ({
                                  channel_id: orderedChannel.id,
                                  state: (nextAssignments[orderedChannel.id] ?? 'off') as SceneChannelAssignmentRequest['state'],
                                }));
                                void onSaveSceneAssignments(activeScene.id, payload);
                              }}
                            >
                              <option value="off">Greyed out</option>
                              <option value="ready">About to enter</option>
                              <option value="onstage">On stage</option>
                            </select>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          </section>
        </div>
      </section>
    </section>
  );
}
