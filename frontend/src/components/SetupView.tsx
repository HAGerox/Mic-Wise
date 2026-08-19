import { useEffect, useMemo, useRef, useState } from 'react';

import { buildExternalSyncStatusText } from '../lib/ui-logic';
import { clampGainDb, sortChannels, sortScenes } from '../lib/format';
import type {
  AudioInputDeviceResponse,
  ChannelResponse,
  ChannelUpdateRequest,
  NetworkInterfaceResponse,
  SceneAssignmentState,
  SceneChannelAssignmentRequest,
  SceneResponse,
  SceneSyncStatusResponse,
  SceneUpdateRequest,
  SettingsResponse,
  SettingsUpdateRequest,
} from '../types/api';
import type { ProgramChannelDraft, SetupTab } from '../types/ui';

const PROGRAM_AUTOSAVE_DELAY_MS = 450;

const SCENE_ASSIGNMENT_STATES: Array<{ state: SceneAssignmentState; label: string; shortLabel: string }> = [
  { state: 'onstage', label: 'On stage', shortLabel: 'On' },
  { state: 'ready', label: 'About to enter', shortLabel: 'Ready' },
  { state: 'off', label: 'Not in scene', shortLabel: 'Off' },
];

function getSceneStateOption(state: SceneAssignmentState): { state: SceneAssignmentState; label: string; shortLabel: string } {
  return SCENE_ASSIGNMENT_STATES.find((option) => option.state === state) ?? SCENE_ASSIGNMENT_STATES[2];
}

function getSceneSummary(scene: SceneResponse | null): string {
  const assignments = scene?.channel_assignments ?? [];
  const onstageCount = assignments.filter((assignment) => assignment.state === 'onstage').length;
  const readyCount = assignments.filter((assignment) => assignment.state === 'ready').length;
  return `${onstageCount} on stage • ${readyCount} about to enter`;
}

function toProgramDraft(channel: ChannelResponse): ProgramChannelDraft {
  return {
    name: channel.name,
    photo_path: channel.photo_path ?? '',
    input_index: channel.input_index,
    gain_db: clampGainDb(channel.gain_db ?? 0),
    is_record_enabled: channel.is_record_enabled,
  };
}

function getSelectedDeviceDetails(
  audioDevices: AudioInputDeviceResponse[],
  selector: string | null | undefined,
): AudioInputDeviceResponse | null {
  return audioDevices.find((device) => device.selector === selector) ?? null;
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
        <div className="program-photo-field">
          <span
            className={`program-photo-preview ${draft.photo_path ? 'has-photo' : ''}`}
            style={draft.photo_path ? { backgroundImage: `url(${JSON.stringify(draft.photo_path)})` } : undefined}
            aria-hidden="true"
          ></span>
          <input
            type="text"
            data-field="photo_path"
            aria-label={`Photo URL for ${channel.name}`}
            placeholder="Image URL or /path"
            value={draft.photo_path}
            onChange={(event) => {
              setDraft({ ...draft, photo_path: event.target.value });
            }}
            onBlur={() => {
              const photoPath = draft.photo_path.trim();
              const nextDraft = { ...draft, photo_path: photoPath };
              setDraft(nextDraft);
              void onSave(channel.id, { ...nextDraft, photo_path: photoPath || null });
            }}
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
  audioDevices: AudioInputDeviceResponse[];
  networkInterfaces: NetworkInterfaceResponse[];
  activeSceneId: number | null;
  onSetSetupTab: (tab: SetupTab) => void;
  onSaveSettings: (payload: SettingsUpdateRequest) => Promise<void>;
  onAddChannel: () => Promise<void>;
  onSaveChannel: (channelId: number, payload: ChannelUpdateRequest) => Promise<void>;
  onRemoveChannel: (channelId: number) => Promise<void>;
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
  onResetChecklist: () => void;
  onExportShowfile: () => Promise<void>;
  onImportShowfile: (file: File) => Promise<void>;
  onTestRChat: () => Promise<void>;
}

export function SetupView({
  hidden,
  setupTab,
  settings,
  syncStatus,
  channels,
  scenes,
  audioDevices,
  networkInterfaces,
  activeSceneId,
  onSetSetupTab,
  onSaveSettings,
  onAddChannel,
  onSaveChannel,
  onRemoveChannel,
  onAddScene,
  onSetActiveScene,
  onDeleteScene,
  onSaveSceneName,
  onSaveSceneAssignments,
  onSaveSceneCueMapping,
  onResetChecklist,
  onExportShowfile,
  onImportShowfile,
  onTestRChat,
}: SetupViewProps): JSX.Element {
  const orderedChannels = useMemo(() => sortChannels(channels), [channels]);
  const orderedScenes = useMemo(() => sortScenes(scenes), [scenes]);
  const activeScene = useMemo(
    () => orderedScenes.find((scene) => scene.id === activeSceneId) ?? null,
    [activeSceneId, orderedScenes],
  );
  const selectedDevice = useMemo(
    () => getSelectedDeviceDetails(audioDevices, settings?.audio_input_device),
    [audioDevices, settings?.audio_input_device],
  );
  const [masterGainValue, setMasterGainValue] = useState('0');
  const [runtimeForm, setRuntimeForm] = useState({
    audio_source_mode: 'synthetic' as SettingsResponse['audio_source_mode'],
    audio_input_device: '',
    channel_count: 16,
    sample_rate: 48_000,
    block_size: 480,
    buffer_duration_sec: 300,
  });
  const [externalSyncForm, setExternalSyncForm] = useState({
    external_sync_enabled: false,
    external_sync_transport: 'off' as SettingsResponse['external_sync_transport'],
    external_sync_osc_host: '0.0.0.0',
    external_sync_osc_port: 53001,
    external_sync_midi_input_name: '',
  });
  const [alertsForm, setAlertsForm] = useState({
    rchat_enabled: false,
    rchat_flash_enabled: false,
    rchat_hold_seconds: 8,
    rchat_interface_ip: '',
    rchat_username: 'Mic-Wise',
  });
  const [sceneName, setSceneName] = useState('');
  const [sceneCueForm, setSceneCueForm] = useState({
    sync_osc_address: '',
    sync_osc_argument: '',
    sync_midi_pattern: '',
  });
  const [sceneAssignments, setSceneAssignments] = useState<Record<number, SceneAssignmentState>>({});
  const [sceneStateBrush, setSceneStateBrush] = useState<SceneAssignmentState>('onstage');
  const sceneAssignmentsRef = useRef<Record<number, SceneAssignmentState>>({});
  const importInputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => {
    setMasterGainValue(String(clampGainDb(Number(settings?.master_gain_db ?? 0))));
    setRuntimeForm({
      audio_source_mode: settings?.audio_source_mode ?? 'synthetic',
      audio_input_device: settings?.audio_input_device ?? '',
      channel_count: Math.max(1, Number(settings?.channel_count ?? 16)),
      sample_rate: Math.max(8_000, Number(settings?.sample_rate ?? 48_000)),
      block_size: Math.max(64, Number(settings?.block_size ?? 480)),
      buffer_duration_sec: Math.max(60, Number(settings?.buffer_duration_sec ?? 300)),
    });
    setExternalSyncForm({
      external_sync_enabled: Boolean(settings?.external_sync_enabled),
      external_sync_transport: settings?.external_sync_transport ?? 'off',
      external_sync_osc_host: settings?.external_sync_osc_host ?? '0.0.0.0',
      external_sync_osc_port: settings?.external_sync_osc_port ?? 53001,
      external_sync_midi_input_name: settings?.external_sync_midi_input_name ?? '',
    });
    setAlertsForm({
      rchat_enabled: Boolean(settings?.rchat_enabled),
      rchat_flash_enabled: Boolean(settings?.rchat_flash_enabled),
      rchat_hold_seconds: Math.max(1, Number(settings?.rchat_hold_seconds ?? 8)),
      rchat_interface_ip: settings?.rchat_interface_ip ?? '',
      rchat_username: settings?.rchat_username ?? 'Mic-Wise',
    });
  }, [settings]);

  useEffect(() => {
    setSceneName(activeScene?.name ?? '');
    setSceneCueForm({
      sync_osc_address: activeScene?.sync_osc_address ?? '',
      sync_osc_argument: activeScene?.sync_osc_argument ?? '',
      sync_midi_pattern: activeScene?.sync_midi_pattern ?? '',
    });
    const nextAssignments = Object.fromEntries(
      (activeScene?.channel_assignments ?? []).map((assignment) => [assignment.channel_id, assignment.state]),
    ) as Record<number, SceneAssignmentState>;
    sceneAssignmentsRef.current = nextAssignments;
    setSceneAssignments(nextAssignments);
  }, [activeScene]);

  const setupSections: Array<{ id: SetupTab; label: string }> = [
    { id: 'general', label: 'General' },
    { id: 'channels', label: 'Channels' },
    { id: 'scenes', label: 'Scenes' },
    { id: 'automation', label: 'Automation' },
  ];

  const sceneAssignmentCounts = SCENE_ASSIGNMENT_STATES.reduce<Record<SceneAssignmentState, number>>(
    (counts, option) => ({
      ...counts,
      [option.state]: orderedChannels.filter((channel) => (sceneAssignments[channel.id] ?? 'off') === option.state).length,
    }),
    { off: 0, ready: 0, onstage: 0 },
  );

  const applySceneState = (channelId: number, nextState: SceneAssignmentState): void => {
    const currentAssignments = sceneAssignmentsRef.current;

    if (!activeScene || (currentAssignments[channelId] ?? 'off') === nextState) {
      return;
    }

    const nextAssignments = {
      ...currentAssignments,
      [channelId]: nextState,
    };
    sceneAssignmentsRef.current = nextAssignments;
    setSceneAssignments(nextAssignments);
    const payload: SceneChannelAssignmentRequest[] = orderedChannels.map((orderedChannel) => ({
      channel_id: orderedChannel.id,
      state: nextAssignments[orderedChannel.id] ?? 'off',
    }));
    void onSaveSceneAssignments(activeScene.id, payload);
  };

  return (
    <section id="setup-view" className={`view-panel ${hidden ? 'is-hidden' : ''}`}>
      <section className="setup-shell">
        <nav className="setup-nav panel-card" aria-label="Setup navigation">
          {setupSections.map((section) => (
            <button
              key={section.id}
              type="button"
              className={`setup-nav-item ${setupTab === section.id ? 'is-active' : ''}`}
              onClick={() => onSetSetupTab(section.id)}
            >
              <strong>{section.label}</strong>
            </button>
          ))}
        </nav>

        <div className="setup-content">
          <section className={`setup-section ${setupTab === 'general' ? '' : 'is-hidden'}`}>
            <div className="setup-overview-grid">
              <section className="panel-card setup-summary-card">
          <div>
            <h3>Console defaults</h3>
          </div>

          <label className="field-group" htmlFor="master-gain-input">
            <span>Master trim</span>
            <div className="gain-input-field">
              <input
                id="master-gain-input"
                type="number"
                min={-24}
                max={24}
                step={1}
                value={masterGainValue}
                onChange={(event) => {
                  setMasterGainValue(String(clampGainDb(Number(event.target.value))));
                }}
                onBlur={() => {
                  const nextValue = String(clampGainDb(Number(masterGainValue)));
                  setMasterGainValue(nextValue);
                  void onSaveSettings({ master_gain_db: Number(nextValue) });
                }}
              />
              <span>dB</span>
            </div>
          </label>

              </section>

              <section className="panel-card setup-summary-card setup-showfile-card">
          <div>
            <h3>Showfile</h3>
            <p className="setup-helper-text">Export a portable backup before major edits. Import replaces the current channel, scene, and settings state from a Mic-Wise JSON showfile.</p>
          </div>

          <div className="panel-heading-actions">
            <button type="button" className="secondary" onClick={() => void onExportShowfile()}>Export showfile</button>
            <button type="button" onClick={() => importInputRef.current?.click()}>Import showfile</button>
            <input
              ref={importInputRef}
              className="is-hidden"
              type="file"
              accept=".json,.micwise.json"
              onChange={(event) => {
                const file = event.target.files?.[0] ?? null;
                if (!file) {
                  return;
                }
                void onImportShowfile(file);
                event.target.value = '';
              }}
            />
          </div>
              </section>

              <section className="panel-card setup-summary-card">
          <div>
            <h3>Audio engine</h3>
          </div>

          <div className="scene-sync-settings-grid">
            <label className="field-group" htmlFor="audio-source-mode">
              <span>Source</span>
              <select
                id="audio-source-mode"
                value={runtimeForm.audio_source_mode === 'sounddevice' ? 'hardware' : runtimeForm.audio_source_mode}
                onChange={(event) => {
                  const nextMode = event.target.value as 'synthetic' | 'hardware';
                  setRuntimeForm({
                    ...runtimeForm,
                    audio_source_mode: nextMode === 'hardware' ? 'sounddevice' : 'synthetic',
                  });
                  void onSaveSettings({ audio_source_mode: nextMode });
                }}
              >
                <option value="synthetic">Synthetic test source</option>
                <option value="hardware">Hardware input device</option>
              </select>
            </label>

            <label className="field-group" htmlFor="audio-input-device">
              <span>Input device</span>
              <select
                id="audio-input-device"
                disabled={runtimeForm.audio_source_mode !== 'sounddevice'}
                value={runtimeForm.audio_input_device}
                onChange={(event) => {
                  const nextDevice = event.target.value;
                  setRuntimeForm({ ...runtimeForm, audio_input_device: nextDevice });
                  void onSaveSettings({ audio_input_device: nextDevice || null });
                }}
              >
                <option value="">Auto / system default</option>
                {audioDevices.map((device) => (
                  <option key={device.selector} value={device.selector}>{device.display_name}</option>
                ))}
              </select>
            </label>

            <label className="field-group" htmlFor="audio-channel-count">
              <span>Input channels</span>
              <input
                id="audio-channel-count"
                type="number"
                min={1}
                max={64}
                step={1}
                value={runtimeForm.channel_count}
                onChange={(event) => {
                  setRuntimeForm({ ...runtimeForm, channel_count: Math.max(1, Number(event.target.value || 1)) });
                }}
                onBlur={() => {
                  void onSaveSettings({ channel_count: runtimeForm.channel_count });
                }}
              />
            </label>

            <label className="field-group" htmlFor="audio-sample-rate">
              <span>Sample rate</span>
              <input
                id="audio-sample-rate"
                type="number"
                min={8_000}
                max={192_000}
                step={1}
                value={runtimeForm.sample_rate}
                onChange={(event) => {
                  setRuntimeForm({ ...runtimeForm, sample_rate: Math.max(8_000, Number(event.target.value || 48_000)) });
                }}
                onBlur={() => {
                  void onSaveSettings({ sample_rate: runtimeForm.sample_rate });
                }}
              />
            </label>

            <label className="field-group" htmlFor="audio-block-size">
              <span>Block size</span>
              <input
                id="audio-block-size"
                type="number"
                min={64}
                max={4_096}
                step={1}
                value={runtimeForm.block_size}
                onChange={(event) => {
                  setRuntimeForm({ ...runtimeForm, block_size: Math.max(64, Number(event.target.value || 480)) });
                }}
                onBlur={() => {
                  void onSaveSettings({ block_size: runtimeForm.block_size });
                }}
              />
            </label>

            <label className="field-group" htmlFor="audio-buffer-duration">
              <span>History window</span>
              <input
                id="audio-buffer-duration"
                type="number"
                min={60}
                max={900}
                step={1}
                value={runtimeForm.buffer_duration_sec}
                onChange={(event) => {
                  setRuntimeForm({
                    ...runtimeForm,
                    buffer_duration_sec: Math.max(60, Number(event.target.value || 300)),
                  });
                }}
                onBlur={() => {
                  void onSaveSettings({ buffer_duration_sec: runtimeForm.buffer_duration_sec });
                }}
              />
            </label>
          </div>

          <p className="setup-helper-text">
            {selectedDevice
              ? `${selectedDevice.max_input_channels} inputs available on ${selectedDevice.hostapi_name} · default ${selectedDevice.default_sample_rate} Hz`
              : 'Use Auto to follow the system default interface, or lock Mic-Wise to a specific capture device.'}
          </p>
              </section>
            </div>
          </section>

          <section id="setup-program-panel" className={`setup-panel panel-card ${setupTab === 'channels' ? '' : 'is-hidden'}`}>
        <div className="panel-heading panel-heading--nested">
          <div>
            <h3>Channel patch sheet</h3>
          </div>
          <div className="panel-heading-actions">
            <button id="add-channel" type="button" onClick={() => void onAddChannel()}>Add RF path</button>
          </div>
        </div>

        <div className="table-shell">
          <table className="program-table">
            <thead>
              <tr>
                <th>Channel</th>
                <th>Name</th>
                <th>Photo</th>
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

          <section id="setup-scenes-panel" className={`setup-panel panel-card ${setupTab === 'scenes' ? '' : 'is-hidden'}`}>
        <div className="panel-heading panel-heading--nested">
          <div>
            <h3>Scene map</h3>
          </div>
          <div className="panel-heading-actions">
            <button type="button" className="secondary" onClick={onResetChecklist}>Reset scene checks</button>
            <button id="add-scene" type="button" onClick={() => void onAddScene()}>Add scene</button>
          </div>
        </div>

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
              <span>Add a scene to define live channels, standby channels, and cue sync.</span>
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

              <section className="scene-sync-card">
                <div>
                  <h3>Scene cue mapping</h3>
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

              <section className="scene-status-programmer" aria-labelledby="scene-status-programmer-title">
                <div className="scene-status-programmer-header">
                  <div>
                    <h3 id="scene-status-programmer-title">Paint channel states</h3>
                    <p>Choose a status, then click channel numbers to program this scene in one pass.</p>
                  </div>

                  <div className="scene-status-brushes" role="radiogroup" aria-label="Scene status brush">
                    {SCENE_ASSIGNMENT_STATES.map((option) => (
                      <button
                        key={option.state}
                        type="button"
                        className={`scene-status-brush is-${option.state} ${sceneStateBrush === option.state ? 'is-active' : ''}`}
                        role="radio"
                        aria-checked={sceneStateBrush === option.state}
                        onClick={() => setSceneStateBrush(option.state)}
                      >
                        <span className="scene-status-dot" aria-hidden="true" />
                        <strong>{option.label}</strong>
                        <span>{sceneAssignmentCounts[option.state]}</span>
                      </button>
                    ))}
                  </div>
                </div>

                <div id="scene-table-body" className="scene-status-grid" aria-label="Channel scene status">
                  {orderedChannels.map((channel) => {
                    const sceneState = sceneAssignments[channel.id] ?? 'off';
                    const sceneStateOption = getSceneStateOption(sceneState);
                    return (
                      <button
                        key={channel.id}
                        type="button"
                        data-channel-id={String(channel.id)}
                        className={`scene-status-tile is-${sceneState}`}
                        disabled={!activeScene}
                        aria-label={`Set channel ${channel.number}, ${channel.name}, to ${getSceneStateOption(sceneStateBrush).label}`}
                        title={`${channel.name}: ${sceneStateOption.label}`}
                        onClick={() => applySceneState(channel.id, sceneStateBrush)}
                      >
                        <span className="scene-status-channel-number">{channel.number}</span>
                        <span className="scene-status-channel-copy">
                          <strong>{channel.name}</strong>
                          <span>{sceneStateOption.label}</span>
                        </span>
                      </button>
                    );
                  })}
                </div>
              </section>
            </div>
          </section>
        </div>
          </section>

          <section className={`setup-section ${setupTab === 'automation' ? '' : 'is-hidden'}`}>
            <div className="setup-overview-grid">
              <section className="scene-sync-settings-panel panel-card">
          <div>
            <h3>External scene sync</h3>
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
                  void onSaveSettings({
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
                    external_sync_transport: event.target.value as SettingsResponse['external_sync_transport'],
                  };
                  setExternalSyncForm(nextForm);
                  void onSaveSettings({
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
                  void onSaveSettings({
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
                onChange={(event) => {
                  setExternalSyncForm({
                    ...externalSyncForm,
                    external_sync_osc_port: Number(event.target.value || 53001),
                  });
                }}
                onBlur={() => {
                  void onSaveSettings({
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
                  void onSaveSettings({
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

              <section className="scene-sync-settings-panel panel-card">
          <div>
            <h3>RChat</h3>
          </div>

          <div className="panel-heading-actions">
            <button type="button" className="secondary" onClick={() => void onTestRChat()}>Test RChat</button>
          </div>

          <div className="scene-sync-settings-grid">
            <label className="field-group field-group--toggle" htmlFor="rchat-enabled">
              <span>Send to RChat</span>
              <input
                id="rchat-enabled"
                type="checkbox"
                checked={alertsForm.rchat_enabled}
                onChange={(event) => {
                  const nextForm = { ...alertsForm, rchat_enabled: event.target.checked };
                  setAlertsForm(nextForm);
                  void onSaveSettings({
                    rchat_enabled: nextForm.rchat_enabled,
                    rchat_flash_enabled: nextForm.rchat_flash_enabled,
                    rchat_hold_seconds: nextForm.rchat_hold_seconds,
                    rchat_interface_ip: nextForm.rchat_interface_ip || null,
                    rchat_username: nextForm.rchat_username.trim() || 'Mic-Wise',
                  });
                }}
              />
            </label>

            <label className="field-group field-group--toggle" htmlFor="rchat-flash-enabled">
              <span>Flash message</span>
              <input
                id="rchat-flash-enabled"
                type="checkbox"
                checked={alertsForm.rchat_flash_enabled}
                disabled={!alertsForm.rchat_enabled}
                onChange={(event) => {
                  const nextForm = { ...alertsForm, rchat_flash_enabled: event.target.checked };
                  setAlertsForm(nextForm);
                  void onSaveSettings({
                    rchat_enabled: nextForm.rchat_enabled,
                    rchat_flash_enabled: nextForm.rchat_flash_enabled,
                    rchat_hold_seconds: nextForm.rchat_hold_seconds,
                    rchat_interface_ip: nextForm.rchat_interface_ip || null,
                    rchat_username: nextForm.rchat_username.trim() || 'Mic-Wise',
                  });
                }}
              />
            </label>

            <label className="field-group" htmlFor="rchat-hold-seconds">
              <span>RChat hold</span>
              <input
                id="rchat-hold-seconds"
                type="number"
                min={1}
                max={30}
                step={1}
                disabled={!alertsForm.rchat_enabled}
                value={alertsForm.rchat_hold_seconds}
                onChange={(event) => {
                  setAlertsForm({
                    ...alertsForm,
                    rchat_hold_seconds: Math.max(1, Number(event.target.value || 1)),
                  });
                }}
                onBlur={() => {
                  void onSaveSettings({
                    rchat_enabled: alertsForm.rchat_enabled,
                    rchat_flash_enabled: alertsForm.rchat_flash_enabled,
                    rchat_hold_seconds: alertsForm.rchat_hold_seconds,
                    rchat_interface_ip: alertsForm.rchat_interface_ip || null,
                    rchat_username: alertsForm.rchat_username.trim() || 'Mic-Wise',
                  });
                }}
              />
            </label>

            <label className="field-group" htmlFor="rchat-username">
              <span>RChat display name</span>
              <input
                id="rchat-username"
                type="text"
                maxLength={128}
                disabled={!alertsForm.rchat_enabled}
                value={alertsForm.rchat_username}
                onChange={(event) => {
                  setAlertsForm({ ...alertsForm, rchat_username: event.target.value });
                }}
                onBlur={() => {
                  const username = alertsForm.rchat_username.trim() || 'Mic-Wise';
                  setAlertsForm({ ...alertsForm, rchat_username: username });
                  void onSaveSettings({ rchat_username: username });
                }}
              />
            </label>

            <label className="field-group" htmlFor="rchat-interface-ip">
              <span>RChat interface</span>
              <select
                id="rchat-interface-ip"
                disabled={!alertsForm.rchat_enabled}
                value={alertsForm.rchat_interface_ip}
                onChange={(event) => {
                  const nextForm = { ...alertsForm, rchat_interface_ip: event.target.value };
                  setAlertsForm(nextForm);
                  void onSaveSettings({
                    rchat_enabled: nextForm.rchat_enabled,
                    rchat_flash_enabled: nextForm.rchat_flash_enabled,
                    rchat_hold_seconds: nextForm.rchat_hold_seconds,
                    rchat_interface_ip: nextForm.rchat_interface_ip || null,
                    rchat_username: nextForm.rchat_username.trim() || 'Mic-Wise',
                  });
                }}
              >
                <option value="">Auto / default route</option>
                {networkInterfaces.map((networkInterface) => (
                  <option key={`${networkInterface.name}-${networkInterface.ipv4_address}`} value={networkInterface.ipv4_address}>
                    {networkInterface.display_name}
                  </option>
                ))}
              </select>
            </label>
          </div>

              </section>
            </div>
          </section>
        </div>
      </section>
    </section>
  );
}
