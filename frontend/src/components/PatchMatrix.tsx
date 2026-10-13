import { useEffect, useMemo, useRef, useState } from 'react';
import type { PointerEvent as ReactPointerEvent } from 'react';

import {
  appendVisitedPatchCells,
  applyPatchStroke,
  getPatchStrokeCells,
  getPatchStrokeMode,
  getPointerStrokeSamplePoints,
} from '../lib/ui-logic';
import type { PatchMatrixCell, PatchStrokeMode } from '../lib/ui-logic';
import type { ChannelResponse } from '../types/api';

export interface ChannelPatchChange {
  channelId: number;
  inputIndex: number | null;
}

interface PatchStroke {
  pointerId: number;
  mode: PatchStrokeMode;
  anchor: PatchMatrixCell;
  current: PatchMatrixCell;
  /** Cells the pointer passed over, used when a stroke unpatches. */
  visited: PatchMatrixCell[];
  lastPoint: { x: number; y: number };
}

interface PatchMatrixProps {
  /** Display channels in row order. */
  channels: ChannelResponse[];
  inputCount: number;
  /** Names the audio source the input columns belong to. */
  inputSourceLabel: string;
  onPatchChannels: (changes: ChannelPatchChange[]) => Promise<void>;
  onRenameChannel: (channelId: number, name: string) => Promise<void>;
}

function cellFromPoint(clientX: number, clientY: number): PatchMatrixCell | null {
  const element = document.elementFromPoint(clientX, clientY);
  const cell = element instanceof Element ? element.closest<HTMLElement>('[data-patch-row]') : null;
  if (!cell) {
    return null;
  }
  return { row: Number(cell.dataset.patchRow), column: Number(cell.dataset.patchColumn) };
}

function isSameCell(left: PatchMatrixCell | null, right: PatchMatrixCell | null): boolean {
  return left?.row === right?.row && left?.column === right?.column;
}

interface MatrixChannelNameProps {
  channel: ChannelResponse;
  onRename: (channelId: number, name: string) => Promise<void>;
}

function MatrixChannelName({ channel, onRename }: MatrixChannelNameProps): JSX.Element {
  const [draft, setDraft] = useState(channel.name);

  useEffect(() => {
    setDraft(channel.name);
  }, [channel.name]);

  const commit = (): void => {
    const name = draft.trim();
    if (!name) {
      setDraft(channel.name);
      return;
    }
    if (name !== channel.name) {
      void onRename(channel.id, name).catch(() => setDraft(channel.name));
    }
  };

  return (
    <input
      type="text"
      className="patch-matrix-name-input"
      aria-label={`Name for CH ${channel.number}`}
      value={draft}
      onChange={(event) => setDraft(event.target.value)}
      onBlur={commit}
      onKeyDown={(event) => {
        if (event.key === 'Enter') {
          event.currentTarget.blur();
        } else if (event.key === 'Escape') {
          setDraft(channel.name);
          // Blur after the reset so the commit sees the original name.
          const input = event.currentTarget;
          window.setTimeout(() => input.blur(), 0);
        }
      }}
    />
  );
}

export function PatchMatrix({
  channels,
  inputCount,
  inputSourceLabel,
  onPatchChannels,
  onRenameChannel,
}: PatchMatrixProps): JSX.Element {
  const [stroke, setStroke] = useState<PatchStroke | null>(null);
  const [hoverCell, setHoverCell] = useState<PatchMatrixCell | null>(null);
  const [pendingPatch, setPendingPatch] = useState<Array<number | null> | null>(null);
  const requestTokenRef = useRef(0);

  const savedPatch = useMemo(
    () => channels.map((channel) => channel.input_index ?? null),
    [channels],
  );

  useEffect(() => {
    // A fresh channel list from the server supersedes any optimistic patch.
    requestTokenRef.current += 1;
    setPendingPatch(null);
  }, [savedPatch]);

  const basePatch = pendingPatch ?? savedPatch;
  const strokeCells = useMemo(() => {
    if (!stroke) {
      return [];
    }
    return stroke.mode === 'patch'
      ? getPatchStrokeCells(stroke.anchor, stroke.current, inputCount)
      : stroke.visited;
  }, [inputCount, stroke]);
  const displayPatch = useMemo(
    () => (stroke ? applyPatchStroke(basePatch, strokeCells, stroke.mode) : basePatch),
    [basePatch, stroke, strokeCells],
  );
  const strokeCellKeys = useMemo(
    () => new Set(strokeCells.map((cell) => `${cell.row}:${cell.column}`)),
    [strokeCells],
  );

  // Crosshair: the hovered cell plus every row and column the stroke touches.
  const { highlightRows, highlightColumns } = useMemo(() => {
    const rows = new Set<number>();
    const columns = new Set<number>();
    for (const cell of [...strokeCells, ...(hoverCell ? [hoverCell] : [])]) {
      rows.add(cell.row);
      columns.add(cell.column);
    }
    return { highlightRows: rows, highlightColumns: columns };
  }, [hoverCell, strokeCells]);

  const commitPatch = (nextPatch: Array<number | null>): void => {
    const changes: ChannelPatchChange[] = channels
      .map((channel, row) => ({ channelId: channel.id, inputIndex: nextPatch[row] ?? null, row }))
      .filter(({ row, inputIndex }) => inputIndex !== (basePatch[row] ?? null))
      .map(({ channelId, inputIndex }) => ({ channelId, inputIndex }));
    if (changes.length === 0) {
      return;
    }
    requestTokenRef.current += 1;
    const token = requestTokenRef.current;
    setPendingPatch(nextPatch);
    void onPatchChannels(changes).catch(() => {
      if (requestTokenRef.current === token) {
        setPendingPatch(null);
      }
    });
  };

  const finishStroke = (event: ReactPointerEvent<HTMLDivElement>, cancelled: boolean): void => {
    if (!stroke || stroke.pointerId !== event.pointerId) {
      return;
    }
    setStroke(null);
    if (!cancelled) {
      commitPatch(applyPatchStroke(basePatch, strokeCells, stroke.mode));
    }
  };

  const outOfRangeCount = basePatch.filter((inputIndex) => inputIndex !== null && inputIndex >= inputCount).length;

  return (
    <div className="patch-matrix">
      <div className="patch-matrix-toolbar">
        <button
          type="button"
          className="secondary"
          disabled={basePatch.every((inputIndex) => inputIndex === null)}
          onClick={() => commitPatch(channels.map(() => null))}
        >
          Unpatch all
        </button>
        {outOfRangeCount > 0 ? (
          <p className="setup-helper-text patch-matrix-warning">
            {outOfRangeCount === 1 ? '1 channel is' : `${outOfRangeCount} channels are`} patched beyond the {inputCount} configured inputs.
          </p>
        ) : null}
      </div>

      <div
        className={`table-shell patch-matrix-shell ${stroke ? `is-dragging is-${stroke.mode}` : ''}`}
        onPointerMove={(event) => {
          const cell = cellFromPoint(event.clientX, event.clientY);
          if (!stroke || stroke.pointerId !== event.pointerId) {
            if (!isSameCell(cell, hoverCell)) {
              setHoverCell(cell);
            }
            return;
          }
          const point = { x: event.clientX, y: event.clientY };
          // Sample along the pointer path so a fast unpatch sweep cannot skip cells.
          const passedCells = stroke.mode === 'unpatch'
            ? getPointerStrokeSamplePoints(stroke.lastPoint, point, 8)
              .map((sample) => cellFromPoint(sample.x, sample.y))
              .filter((sample): sample is PatchMatrixCell => sample !== null)
            : [];
          const visited = appendVisitedPatchCells(stroke.visited, passedCells);
          const current = cell ?? stroke.current;
          if (visited === stroke.visited && isSameCell(current, stroke.current)) {
            setStroke({ ...stroke, lastPoint: point });
            return;
          }
          setHoverCell(current);
          setStroke({ ...stroke, current, visited, lastPoint: point });
        }}
        onPointerLeave={() => {
          if (!stroke) {
            setHoverCell(null);
          }
        }}
        onPointerUp={(event) => finishStroke(event, false)}
        onPointerCancel={(event) => finishStroke(event, true)}
      >
        <table className="patch-matrix-table">
          <thead>
            <tr className="patch-matrix-group-row">
              <th scope="col" rowSpan={2} className="patch-matrix-corner">Channel</th>
              <th scope="colgroup" colSpan={Math.max(inputCount, 1)} className="patch-matrix-source">
                <span className="patch-matrix-source-label">Inputs</span>
                <span className="patch-matrix-source-name">{inputSourceLabel}</span>
              </th>
            </tr>
            <tr className="patch-matrix-number-row">
              {Array.from({ length: inputCount }, (_, column) => (
                <th
                  key={column}
                  scope="col"
                  className={`patch-matrix-input ${highlightColumns.has(column) ? 'is-highlighted' : ''}`}
                  title={`Input ${column + 1} · ${inputSourceLabel}`}
                >
                  {column + 1}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {channels.map((channel, row) => {
              const isRowHighlighted = highlightRows.has(row);
              return (
                <tr key={channel.id}>
                  <th scope="row" className={`patch-matrix-channel ${isRowHighlighted ? 'is-highlighted' : ''}`}>
                    <span className="patch-matrix-channel-number">CH {channel.number}</span>
                    <MatrixChannelName channel={channel} onRename={onRenameChannel} />
                  </th>
                  {Array.from({ length: inputCount }, (_, column) => {
                    const isPatched = displayPatch[row] === column;
                    const isStrokeCell = strokeCellKeys.has(`${row}:${column}`);
                    const isUnpatching = stroke?.mode === 'unpatch' && isStrokeCell && basePatch[row] === column;
                    return (
                      <td
                        key={column}
                        className={[
                          'patch-matrix-cell-wrap',
                          isRowHighlighted || highlightColumns.has(column) ? 'is-crosshair' : '',
                          isRowHighlighted && highlightColumns.has(column) ? 'is-crosshair-center' : '',
                        ].filter(Boolean).join(' ')}
                      >
                        <button
                          type="button"
                          className={[
                            'patch-matrix-cell',
                            isPatched ? 'is-patched' : '',
                            isStrokeCell && stroke?.mode === 'patch' ? 'is-stroke' : '',
                            isUnpatching ? 'is-unpatching' : '',
                          ].filter(Boolean).join(' ')}
                          data-patch-row={row}
                          data-patch-column={column}
                          aria-pressed={isPatched}
                          aria-label={`${channel.name} from input ${column + 1}`}
                          onPointerDown={(event) => {
                            if (event.button !== 0) {
                              return;
                            }
                            event.preventDefault();
                            event.currentTarget.closest<HTMLElement>('.patch-matrix-shell')?.setPointerCapture(event.pointerId);
                            const cell = { row, column };
                            setHoverCell(cell);
                            setStroke({
                              pointerId: event.pointerId,
                              mode: getPatchStrokeMode(basePatch, cell),
                              anchor: cell,
                              current: cell,
                              visited: [cell],
                              lastPoint: { x: event.clientX, y: event.clientY },
                            });
                          }}
                          onClick={(event) => {
                            // Pointer strokes commit on pointerup; this only handles keyboard activation.
                            if (event.detail === 0) {
                              const cell = { row, column };
                              commitPatch(applyPatchStroke(basePatch, [cell], getPatchStrokeMode(basePatch, cell)));
                            }
                          }}
                        >
                          <span aria-hidden="true"></span>
                        </button>
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
