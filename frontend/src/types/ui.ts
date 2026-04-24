import type {
  ChannelResponse,
  SceneResponse,
  SceneSyncStatusResponse,
  SettingsResponse,
} from './api';

export type ActiveView = 'monitor' | 'show' | 'setup';
export type SetupTab = 'program' | 'scenes';
export type ShowChannelVisualState = 'off' | 'pending' | 'checked';
export type SceneChecklistById = Map<number, Set<number>>;
export type AudioInputSource = [inputIndex: number, gainDb: number];

export interface AppBootstrapData {
  settings: SettingsResponse;
  channels: ChannelResponse[];
  scenes: SceneResponse[];
  syncStatus: SceneSyncStatusResponse;
}

export interface ProgramChannelDraft {
  name: string;
  input_index: number | null;
  gain_db: number;
  is_record_enabled: boolean;
}

export interface ExternalSyncFormState {
  external_sync_enabled: boolean;
  external_sync_transport: SettingsResponse['external_sync_transport'];
  external_sync_osc_host: string;
  external_sync_osc_port: number;
  external_sync_midi_input_name: string;
}
