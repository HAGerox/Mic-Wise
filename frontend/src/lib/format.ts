import type { ChannelResponse, SceneResponse } from '../types/api';

export const MIN_METER_DBFS = -60;

export function formatPlaybackOffset(seconds: number): string {
  const totalSeconds = Math.max(0, Math.round(seconds));
  const minutes = Math.floor(totalSeconds / 60);
  const remainingSeconds = totalSeconds % 60;
  return `${minutes}:${String(remainingSeconds).padStart(2, '0')}`;
}

export function clampGainDb(value: number, min = -24, max = 24): number {
  return Math.min(max, Math.max(min, Number.isFinite(value) ? value : 0));
}

export function dbToLinearGain(gainDb: number): number {
  return 10 ** (clampGainDb(gainDb) / 20);
}

export function linearToDbfs(
  value: number,
  floorDb = MIN_METER_DBFS,
  ceilingDb = 12,
): number {
  const safeValue = Math.max(0, Number.isFinite(value) ? value : 0);
  if (safeValue <= 0) {
    return floorDb;
  }

  return Math.min(ceilingDb, Math.max(floorDb, 20 * Math.log10(safeValue)));
}

export function dbfsToMeterRatio(dbfs: number, floorDb = MIN_METER_DBFS, ceilingDb = 0): number {
  const safeDbfs = Number.isFinite(dbfs) ? dbfs : floorDb;
  return Math.min(1, Math.max(0, (safeDbfs - floorDb) / (ceilingDb - floorDb)));
}

export function meterRatioFromLinear(value: number, floorDb = MIN_METER_DBFS): number {
  return dbfsToMeterRatio(linearToDbfs(value, floorDb), floorDb);
}

export function formatGainDb(gainDb: number): string {
  const value = clampGainDb(Number(gainDb));
  return `${value > 0 ? '+' : ''}${value} dB`;
}

export function formatDbfs(dbfs: number, floorDb = MIN_METER_DBFS): string {
  const safeDbfs = Number.isFinite(dbfs) ? dbfs : floorDb;
  if (safeDbfs <= floorDb) {
    return '-inf';
  }

  const normalisedValue = Math.abs(safeDbfs) < 0.05 ? 0 : safeDbfs;
  const precision = Math.abs(normalisedValue) < 10 ? 1 : 0;
  return `${normalisedValue > 0 ? '+' : ''}${normalisedValue.toFixed(precision)}`;
}

export function getInputLabel(channel: Pick<ChannelResponse, 'input_index'>): string {
  return channel.input_index === null || channel.input_index === undefined
    ? 'Unpatched'
    : `Input ${channel.input_index + 1}`;
}

export function isDefaultChannelName(channel: Pick<ChannelResponse, 'name' | 'number'>): boolean {
  return channel.name.trim().toLowerCase() === `channel ${channel.number}`.toLowerCase();
}

export function sortChannels(channels: ChannelResponse[]): ChannelResponse[] {
  return [...channels].sort((left, right) => {
    if (left.sort_index === right.sort_index) {
      return left.number - right.number;
    }
    return left.sort_index - right.sort_index;
  });
}

export function sortScenes(scenes: SceneResponse[]): SceneResponse[] {
  return [...scenes].sort((left, right) => {
    if (left.order_index === right.order_index) {
      return left.id - right.id;
    }
    return left.order_index - right.order_index;
  });
}
