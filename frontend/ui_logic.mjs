export function normaliseActiveView(activeMode) {
  const mode = String(activeMode ?? "monitor").trim().toLowerCase();
  if (mode === "configure" || mode === "program" || mode === "setup") {
    return "setup";
  }
  if (mode === "scene" || mode === "show") {
    return "show";
  }
  return mode === "monitor" ? "monitor" : "monitor";
}

export function getShowChannelVisualState(sceneState, isChecked) {
  if (sceneState === "off") {
    return "off";
  }
  return isChecked ? "checked" : "pending";
}

export function getSceneChecklistStats(scene, checklist) {
  const activeAssignments = (scene?.channel_assignments ?? []).filter(
    (assignment) => assignment.state && assignment.state !== "off",
  );
  const checkedCount = activeAssignments.filter((assignment) => checklist?.has?.(assignment.channel_id)).length;
  return {
    total: activeAssignments.length,
    checked: checkedCount,
  };
}

function formatSyncTransportLabel(transport) {
  if (transport === "osc") {
    return "OSC";
  }
  if (transport === "midi") {
    return "MIDI";
  }
  if (transport === "both") {
    return "OSC + MIDI";
  }
  return String(transport ?? "off").toUpperCase();
}

export function buildExternalSyncStatusText(syncStatus) {
  if (!syncStatus) {
    return "Checking…";
  }
  if (syncStatus.error) {
    return `Sync error: ${syncStatus.error}`;
  }
  const transport = String(syncStatus.transport ?? "off").trim().toLowerCase();
  if (!syncStatus.enabled || transport === "off") {
    return "Disabled";
  }
  return `${formatSyncTransportLabel(transport)} ready${syncStatus.last_event_summary ? ` · ${syncStatus.last_event_summary}` : ""}`;
}

function sortScenesByOrder(scenes) {
  return [...scenes].sort((left, right) => {
    if (left.order_index === right.order_index) {
      return left.id - right.id;
    }
    return left.order_index - right.order_index;
  });
}

export function resolveActiveSceneId(activeSceneId, scenes) {
  const orderedScenes = sortScenesByOrder(Array.isArray(scenes) ? scenes : []);
  if (orderedScenes.length === 0) {
    return null;
  }

  const hasPreferredSceneId = activeSceneId !== null && activeSceneId !== undefined && activeSceneId !== "";
  const preferredSceneId = hasPreferredSceneId ? Number(activeSceneId) : null;
  if (Number.isInteger(preferredSceneId) && orderedScenes.some((scene) => scene.id === preferredSceneId)) {
    return preferredSceneId;
  }

  return orderedScenes[0].id;
}

export function calculateWaveformPointShift(elapsedMs, windowSeconds, pointCount) {
  if (!Number.isFinite(elapsedMs) || elapsedMs <= 0 || !Number.isFinite(windowSeconds) || windowSeconds <= 0) {
    return 0;
  }
  if (!Number.isFinite(pointCount) || pointCount <= 1) {
    return 0;
  }
  return (elapsedMs / 1000) * ((pointCount - 1) / windowSeconds);
}

function clampIndex(index, lastIndex) {
  if (index <= 0) {
    return 0;
  }
  if (index >= lastIndex) {
    return lastIndex;
  }
  return index;
}

export function shiftWaveformPoints(points, pointShift, tailValue = null) {
  if (!Array.isArray(points) || points.length === 0) {
    return [];
  }

  const lastIndex = points.length - 1;
  const resolvedTail = Number.isFinite(tailValue) ? tailValue : points[lastIndex];
  const safeShift = Number.isFinite(pointShift) && pointShift > 0 ? pointShift : 0;

  return points.map((_, index) => {
    const sourceIndex = index + safeShift;
    if (sourceIndex > lastIndex) {
      return resolvedTail;
    }

    const lowerIndex = clampIndex(Math.floor(sourceIndex), lastIndex);
    const upperIndex = clampIndex(Math.ceil(sourceIndex), lastIndex);
    if (lowerIndex === upperIndex) {
      return points[lowerIndex];
    }

    const fraction = sourceIndex - lowerIndex;
    return points[lowerIndex] + ((points[upperIndex] - points[lowerIndex]) * fraction);
  });
}

export function computeWaveformDisplayPoints(points, elapsedMs, windowSeconds, liveTailValue = null) {
  const safePoints = Array.isArray(points) ? points : [];
  if (safePoints.length === 0) {
    return [];
  }

  const pointShift = calculateWaveformPointShift(elapsedMs, windowSeconds, safePoints.length);
  return shiftWaveformPoints(safePoints, pointShift, liveTailValue);
}
