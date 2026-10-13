import { cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PatchMatrix } from './PatchMatrix';
import type { ChannelResponse } from '../types/api';

function makeChannel(id: number, inputIndex: number | null): ChannelResponse {
  return {
    id,
    number: id,
    name: `Channel ${id}`,
    input_index: inputIndex,
  } as ChannelResponse;
}

describe('PatchMatrix', () => {
  afterEach(() => {
    cleanup();
  });

  function renderMatrix(channels: ChannelResponse[], overrides: Partial<{ onRenameChannel: ReturnType<typeof vi.fn> }> = {}) {
    const onPatchChannels = vi.fn().mockResolvedValue(undefined);
    const onRenameChannel = overrides.onRenameChannel ?? vi.fn().mockResolvedValue(undefined);
    render(
      <PatchMatrix
        channels={channels}
        inputCount={4}
        inputSourceLabel="Synthetic test signal"
        onPatchChannels={onPatchChannels}
        onRenameChannel={onRenameChannel}
      />,
    );
    return { onPatchChannels, onRenameChannel };
  }

  it('marks patched inputs, labels the input source, and unpatches everything in one batch', () => {
    const { onPatchChannels } = renderMatrix([makeChannel(1, 2), makeChannel(2, null), makeChannel(3, 0)]);

    expect(screen.getByRole('button', { name: 'Channel 1 from input 3' })).toHaveAttribute('aria-pressed', 'true');
    expect(screen.getByText('Synthetic test signal')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Patch 1:1' })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', { name: 'Unpatch all' }));
    expect(onPatchChannels).toHaveBeenCalledWith([
      { channelId: 1, inputIndex: null },
      { channelId: 3, inputIndex: null },
    ]);
    // The optimistic patch shows immediately while the save is in flight.
    expect(screen.getByRole('button', { name: 'Channel 1 from input 3' })).toHaveAttribute('aria-pressed', 'false');
  });

  it('renames a channel from its row header', () => {
    const { onRenameChannel } = renderMatrix([makeChannel(1, null)]);
    const input = screen.getByRole('textbox', { name: 'Name for CH 1' });

    fireEvent.change(input, { target: { value: '  Lead vocal ' } });
    fireEvent.blur(input);
    expect(onRenameChannel).toHaveBeenCalledWith(1, 'Lead vocal');

    fireEvent.change(input, { target: { value: '' } });
    fireEvent.blur(input);
    expect(onRenameChannel).toHaveBeenCalledTimes(1);
  });

  it('toggles a cell from the keyboard', () => {
    const { onPatchChannels } = renderMatrix([makeChannel(1, 1)]);

    fireEvent.click(screen.getByRole('button', { name: 'Channel 1 from input 2' }), { detail: 0 });
    expect(onPatchChannels).toHaveBeenLastCalledWith([{ channelId: 1, inputIndex: null }]);
    fireEvent.click(screen.getByRole('button', { name: 'Channel 1 from input 1' }), { detail: 0 });
    expect(onPatchChannels).toHaveBeenLastCalledWith([{ channelId: 1, inputIndex: 0 }]);
  });
});
