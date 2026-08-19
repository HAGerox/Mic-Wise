import type {
  AudioAlertResponse,
  ChannelResponse,
  SceneResponse,
  SceneSyncStatusResponse,
  SettingsResponse,
} from './api';

export type ActiveView = 'monitor' | 'show' | 'setup';
export type SetupTab = 'general' | 'channels' | 'scenes' | 'automation';
export type ShowChannelVisualState = 'off' | 'pending' | 'checked';
export type SceneChecklistById = Map<number, Set<number>>;
export type AudioInputSource = [inputIndex: number, gainDb: number];

export interface ChannelSelectionModifiers {
  additive: boolean;
  range: boolean;
}

export interface AppBootstrapData {
  settings: SettingsResponse;
  channels: ChannelResponse[];
  scenes: SceneResponse[];
  syncStatus: SceneSyncStatusResponse;
}

export interface ProgramChannelDraft {
  name: string;
  photo_path: string;
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

export interface ChannelVisualMetrics {
  rmsLinear: number;
  peakLinear: number;
  rmsDbfs: number;
  peakDbfs: number;
  rmsRatio: number;
  peakRatio: number;
  historyRatios: number[];
}

export type ChannelStatusTone = 'live' | 'armed' | 'muted' | 'warning' | 'critical';

export interface ChannelCardState {
  channel: ChannelResponse;
  metrics: ChannelVisualMetrics;
  activeAlert: AudioAlertResponse | null;
  isSelected: boolean;
  canReorder: boolean;
  visualState: ShowChannelVisualState | null;
  statusTone: ChannelStatusTone;
}
