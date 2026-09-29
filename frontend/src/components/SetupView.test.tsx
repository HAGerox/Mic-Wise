import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { SetupView } from './SetupView';
import type { ChannelResponse, SceneResponse } from '../types/api';

function buildChannel(id: number): ChannelResponse {
  return {
    id,
    number: id,
    name: `Channel ${id}`,
    photo_path: null,
    input_index: id - 1,
    gain_db: 0,
    is_record_enabled: true,
    sort_index: id - 1,
    position_x: 0,
    position_y: 0,
  };
}

function renderSceneSetup(onSaveSceneAssignments = vi.fn().mockResolvedValue(undefined)) {
  const channels = [buildChannel(1), buildChannel(2), buildChannel(3)];
  const scene: SceneResponse = {
    id: 4,
    name: 'Scene 4',
    order_index: 3,
    sync_osc_address: '/micwise/scene/4',
    sync_osc_argument: null,
    sync_midi_pattern: null,
    channel_assignments: [],
  };

  render(
    <SetupView
      hidden={false}
      setupTab="scenes"
      settings={null}
      syncStatus={null}
      channels={channels}
      scenes={[scene]}
      audioDevices={[]}
      networkInterfaces={[]}
      activeSceneId={scene.id}
      onSetSetupTab={vi.fn()}
      onSaveSettings={vi.fn().mockResolvedValue(undefined)}
      onAddChannel={vi.fn().mockResolvedValue(undefined)}
      onSaveChannel={vi.fn().mockResolvedValue(undefined)}
      onRemoveChannel={vi.fn().mockResolvedValue(undefined)}
      onAddScene={vi.fn().mockResolvedValue(undefined)}
      onSetActiveScene={vi.fn().mockResolvedValue(undefined)}
      onDeleteScene={vi.fn().mockResolvedValue(undefined)}
      onSaveSceneName={vi.fn().mockResolvedValue(undefined)}
      onSaveSceneAssignments={onSaveSceneAssignments}
      onSaveSceneCueMapping={vi.fn().mockResolvedValue(undefined)}
      onResetChecklist={vi.fn()}
      onExportShowfile={vi.fn().mockResolvedValue(undefined)}
      onImportShowfile={vi.fn().mockResolvedValue(undefined)}
      onUploadPhoto={vi.fn().mockResolvedValue({ photo_path: '/api/assets/photos/a.png', file_name: 'a.png' })}
      onTestRChat={vi.fn().mockResolvedValue(undefined)}
    />,
  );

  return { onSaveSceneAssignments };
}

afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
  Reflect.deleteProperty(document, 'elementFromPoint');
});

describe('SetupView scene painting', () => {
  it('interpolates a fast pointer stroke across every channel and saves once at pointer-up', async () => {
    vi.stubGlobal('PointerEvent', MouseEvent);
    const user = userEvent.setup();
    const { onSaveSceneAssignments } = renderSceneSetup();

    await user.click(screen.getByRole('radio', { name: /About to enter/ }));
    const firstTile = screen.getByRole('button', { name: /Paint channel 1.*About to enter/ });
    const secondTile = screen.getByRole('button', { name: /Paint channel 2.*About to enter/ });
    const thirdTile = screen.getByRole('button', { name: /Paint channel 3.*About to enter/ });
    const grid = screen.getByLabelText('Channel scene status');
    Object.defineProperty(document, 'elementFromPoint', {
      configurable: true,
      value: vi.fn((x: number) => (x < 60 ? secondTile : thirdTile)),
    });

    fireEvent.pointerDown(firstTile, { pointerId: 7, button: 0, clientX: 0, clientY: 20 });
    fireEvent.pointerMove(grid, { pointerId: 7, clientX: 120, clientY: 20 });
    expect(onSaveSceneAssignments).not.toHaveBeenCalled();

    fireEvent.pointerUp(window, { pointerId: 7 });

    expect(onSaveSceneAssignments).toHaveBeenCalledTimes(1);
    expect(onSaveSceneAssignments).toHaveBeenCalledWith(4, [
      { channel_id: 1, state: 'ready' },
      { channel_id: 2, state: 'ready' },
      { channel_id: 3, state: 'ready' },
    ]);
  });
});
