export type SceneSyncTransport = 'off' | 'osc' | 'midi' | 'both';
export type SceneAssignmentState = 'off' | 'ready' | 'onstage';

export interface HealthResponse {
  status: string;
  audio_engine_running: boolean;
}

export interface SettingsResponse {
  sample_rate: number;
  channel_count: number;
  buffer_duration_sec: number;
  block_size: number;
  audio_source_mode: string;
  master_gain_db: number;
  multi_listen_enabled: boolean;
  active_mode: string;
  scene_mode_enabled: boolean;
  active_scene_id: number | null;
  external_sync_enabled: boolean;
  external_sync_transport: SceneSyncTransport;
  external_sync_osc_host: string;
  external_sync_osc_port: number;
  external_sync_midi_input_name: string | null;
}

export interface SettingsUpdateRequest {
  master_gain_db?: number | null;
  multi_listen_enabled?: boolean | null;
  active_mode?: string | null;
  scene_mode_enabled?: boolean | null;
  active_scene_id?: number | null;
  external_sync_enabled?: boolean | null;
  external_sync_transport?: SceneSyncTransport | null;
  external_sync_osc_host?: string | null;
  external_sync_osc_port?: number | null;
  external_sync_midi_input_name?: string | null;
}

export interface ChannelResponse {
  id: number;
  number: number;
  name: string;
  photo_path: string | null;
  input_index: number | null;
  gain_db: number;
  is_record_enabled: boolean;
  sort_index: number;
  position_x: number;
  position_y: number;
}

export interface ChannelCreateRequest {
  name?: string | null;
  photo_path?: string | null;
  input_index?: number | null;
  gain_db?: number | null;
  is_record_enabled?: boolean | null;
}

export interface ChannelUpdateRequest {
  name?: string | null;
  photo_path?: string | null;
  input_index?: number | null;
  gain_db?: number | null;
  is_record_enabled?: boolean | null;
  sort_index?: number | null;
  position_x?: number | null;
  position_y?: number | null;
}

export interface SceneChannelAssignmentResponse {
  channel_id: number;
  state: SceneAssignmentState;
}

export interface SceneChannelAssignmentRequest {
  channel_id: number;
  state: SceneAssignmentState;
}

export interface SceneResponse {
  id: number;
  name: string;
  order_index: number;
  sync_osc_address: string | null;
  sync_osc_argument: string | null;
  sync_midi_pattern: string | null;
  channel_assignments: SceneChannelAssignmentResponse[];
}

export interface SceneCreateRequest {
  name?: string | null;
  sync_osc_address?: string | null;
  sync_osc_argument?: string | null;
  sync_midi_pattern?: string | null;
  channel_assignments?: SceneChannelAssignmentRequest[] | null;
}

export interface SceneUpdateRequest {
  name?: string | null;
  order_index?: number | null;
  sync_osc_address?: string | null;
  sync_osc_argument?: string | null;
  sync_midi_pattern?: string | null;
  channel_assignments?: SceneChannelAssignmentRequest[] | null;
}

export interface SceneSyncStatusResponse {
  enabled: boolean;
  transport: string;
  osc_listening: boolean;
  osc_endpoint: string | null;
  midi_listening: boolean;
  midi_input_name: string | null;
  last_event_summary: string | null;
  last_matched_scene_id: number | null;
  error: string | null;
}

export interface MeterChannelSnapshot {
  channel: number;
  rms: number;
  peak: number;
}

export interface MeterSnapshotResponse {
  write_head: number;
  window_frames: number;
  channels: MeterChannelSnapshot[];
}

export interface ChannelWaveformResponse {
  channel_id: number;
  input_index: number | null;
  seconds: number;
  points: number[];
}

export interface WebRtcOfferRequest {
  sdp: string;
  type: string;
  channel_ids: number[];
  replay_seconds: number;
}

export interface WebRtcAnswerResponse {
  sdp: string;
  type: string;
}
