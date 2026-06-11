import { useEffect, useRef, useState } from 'react';

import { MODAL_WAVEFORM_WINDOW_SECONDS } from '../hooks/useWaveform';
import { buildWaveformRulerMarks } from '../lib/ui-logic';
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
  context.fillStyle = '#0a0b0d';
  context.fillRect(0, 0, width, height);

  context.strokeStyle = 'rgba(255, 255, 255, 0.08)';
  context.lineWidth = 1;
  for (let line = 1; line < 5; line += 1) {
    const y = (height / 5) * line;
    context.beginPath();
    context.moveTo(0, y);
    context.lineTo(width, y);
    context.stroke();
  }

  const rulerMarks = buildWaveformRulerMarks(MODAL_WAVEFORM_WINDOW_SECONDS, 60, 15, 30);
  for (const mark of rulerMarks) {
    const x = width * mark.position;
    context.beginPath();
    context.setLineDash(mark.kind === 'major' || mark.kind === 'live' ? [1, 0] : [3, 4]);
    context.strokeStyle = mark.kind === 'live' ? 'rgba(113, 112, 255, 0.44)' : 'rgba(255, 255, 255, 0.08)';
    context.moveTo(x, 0);
    context.lineTo(x, height);
    context.stroke();
  }
  context.setLineDash([]);

  context.beginPath();
  context.strokeStyle = 'rgba(255, 255, 255, 0.14)';
  context.moveTo(0, height - 1.5);
  context.lineTo(width, height - 1.5);
  context.stroke();
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
  const [resizeTick, setResizeTick] = useState(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || typeof ResizeObserver === 'undefined') {
      return undefined;
    }

    const resizeObserver = new ResizeObserver(() => {
      setResizeTick((tick) => tick + 1);
    });
    resizeObserver.observe(canvas);
    return () => {
      resizeObserver.disconnect();
    };
  }, []);

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
    const baseline = height - 14;

    if (values.length > 0 && occupiedWidth > 0) {
      const chartTop = 10;
      const chartHeight = baseline - chartTop;

      context.beginPath();
      context.moveTo(startX, baseline);
      for (let index = 0; index < values.length; index += 1) {
        const value = values[index];
        const x = startX + ((occupiedWidth * index) / Math.max(values.length - 1, 1));
        const y = baseline - Math.max(1, value * chartHeight);
        context.lineTo(x, y);
      }
      context.lineTo(startX + occupiedWidth, baseline);
      context.closePath();
      context.fillStyle = 'rgba(113, 112, 255, 0.12)';
      context.fill();

      context.beginPath();
      for (let index = 0; index < values.length; index += 1) {
        const value = values[index];
        const x = startX + ((occupiedWidth * index) / Math.max(values.length - 1, 1));
        const y = baseline - Math.max(1, value * chartHeight);
        if (index === 0) {
          context.moveTo(x, y);
        } else {
          context.lineTo(x, y);
        }
      }
      context.strokeStyle = 'rgba(247, 248, 248, 0.94)';
      context.lineWidth = 1.5;
      context.stroke();

      context.beginPath();
      for (let index = 0; index < values.length; index += 1) {
        const value = values[index];
        const x = startX + ((occupiedWidth * index) / Math.max(values.length - 1, 1));
        const y = baseline - Math.max(1, value * chartHeight);
        if (index === 0) {
          context.moveTo(x, y);
        } else {
          context.lineTo(x, y);
        }
      }
      context.strokeStyle = 'rgba(113, 112, 255, 0.55)';
      context.lineWidth = 3;
      context.globalCompositeOperation = 'screen';
      context.stroke();
      context.globalCompositeOperation = 'source-over';
    }

    if (scrubSeconds > 0) {
      const markerX = width * (1 - Math.min(scrubSeconds, MODAL_WAVEFORM_WINDOW_SECONDS) / MODAL_WAVEFORM_WINDOW_SECONDS);
      context.strokeStyle = '#f97316';
      context.lineWidth = 2;
      context.beginPath();
      context.moveTo(markerX, 0);
      context.lineTo(markerX, height);
      context.stroke();

      context.fillStyle = '#f97316';
      context.fillRect(markerX - 3, 8, 6, 6);
    }
  }, [displayPoints, resizeTick, scrubSeconds, waveform]);

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
