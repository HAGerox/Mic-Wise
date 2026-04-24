import { useEffect, useRef } from 'react';

import { MODAL_WAVEFORM_WINDOW_SECONDS } from '../hooks/useWaveform';
import type { ChannelWaveformResponse } from '../types/api';

function resizeCanvas(canvas: HTMLCanvasElement): {
  context: CanvasRenderingContext2D;
  width: number;
  height: number;
} {
  const ratio = window.devicePixelRatio || 1;
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  canvas.width = Math.floor(width * ratio);
  canvas.height = Math.floor(height * ratio);
  const context = canvas.getContext('2d');
  if (!context) {
    throw new Error('Could not acquire waveform canvas context');
  }
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
  return { context, width, height };
}

function drawGrid(context: CanvasRenderingContext2D, width: number, height: number): void {
  context.clearRect(0, 0, width, height);
  context.fillStyle = '#020617';
  context.fillRect(0, 0, width, height);

  context.strokeStyle = 'rgba(148, 163, 184, 0.15)';
  context.lineWidth = 1;
  for (let line = 1; line < 4; line += 1) {
    const y = (height / 4) * line;
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }
}

interface WaveformCanvasProps {
  waveform: ChannelWaveformResponse | null;
  displayPoints: number[];
  scrubSeconds: number;
  onScrub: (replaySeconds: number) => void;
}

export function WaveformCanvas({
  waveform,
  displayPoints,
  scrubSeconds,
  onScrub,
}: WaveformCanvasProps): JSX.Element {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) {
      return;
    }

    const { context, width, height } = resizeCanvas(canvas);
    drawGrid(context, width, height);

    if (!waveform) {
      return;
    }

    const values = displayPoints.length > 0 ? displayPoints : waveform.points;
    const availableSeconds = Math.min(waveform.seconds, MODAL_WAVEFORM_WINDOW_SECONDS);
    const occupiedWidth = width * (availableSeconds / MODAL_WAVEFORM_WINDOW_SECONDS);
    const startX = width - occupiedWidth;
    const baseline = height - 12;

    if (values.length > 0 && occupiedWidth > 0) {
      context.beginPath();
      context.moveTo(startX, baseline);
      for (let index = 0; index < values.length; index += 1) {
        const value = values[index];
        const x = startX + ((occupiedWidth * index) / Math.max(values.length - 1, 1));
        const y = baseline - Math.max(2, value * (height - 26));
        context.lineTo(x, y);
      }
      context.lineTo(startX + occupiedWidth, baseline);
      context.closePath();
      context.fillStyle = 'rgba(56, 189, 248, 0.16)';
      context.fill();

      context.beginPath();
      for (let index = 0; index < values.length; index += 1) {
        const value = values[index];
        const x = startX + ((occupiedWidth * index) / Math.max(values.length - 1, 1));
        const y = baseline - Math.max(2, value * (height - 26));
        if (index === 0) {
          context.moveTo(x, y);
        } else {
          context.lineTo(x, y);
        }
      }
      context.strokeStyle = 'rgba(56, 189, 248, 0.95)';
      context.lineWidth = 2;
      context.stroke();
    }

    if (scrubSeconds > 0) {
      const markerX = width * (1 - Math.min(scrubSeconds, MODAL_WAVEFORM_WINDOW_SECONDS) / MODAL_WAVEFORM_WINDOW_SECONDS);
      context.strokeStyle = '#f97316';
      context.lineWidth = 2;
      context.beginPath();
      context.moveTo(markerX, 0);
      context.lineTo(markerX, height);
      context.stroke();
    }
  }, [displayPoints, scrubSeconds, waveform]);

  return (
    <canvas
      id="waveform-canvas"
      ref={canvasRef}
      onClick={(event) => {
        if (!waveform) {
          return;
        }
        const rect = event.currentTarget.getBoundingClientRect();
        const position = Math.min(Math.max(event.clientX - rect.left, 0), rect.width);
        const ratio = position / rect.width;
        const requestedReplaySeconds = Math.max(0, MODAL_WAVEFORM_WINDOW_SECONDS * (1 - ratio));
        const replaySeconds = Math.min(requestedReplaySeconds, waveform.seconds);
        const snappedReplaySeconds = replaySeconds < 1.25 ? 0 : replaySeconds;
        onScrub(snappedReplaySeconds);
      }}
    />
  );
}
