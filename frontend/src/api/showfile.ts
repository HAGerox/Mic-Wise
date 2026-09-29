import type {
  ShowfileExportFormat,
  ShowfileImportResponse,
  ShowfilePayload,
} from '../types/api';

const EXPORT_FILENAMES: Record<ShowfileExportFormat, string> = {
  archive: 'show.micwise.zip',
  json: 'micwise-showfile.micwise.json',
};

export async function downloadShowfile(format: ShowfileExportFormat = 'archive'): Promise<void> {
  const response = await fetch(`/api/showfile/export?format=${format}`);
  if (!response.ok) {
    throw new Error(`Showfile export failed: ${response.status}`);
  }

  const blob = await response.blob();
  const disposition = response.headers.get('Content-Disposition') ?? '';
  const quotedName = /filename="([^"]+)"/.exec(disposition)?.[1];
  const downloadUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = downloadUrl;
  anchor.download = quotedName ?? EXPORT_FILENAMES[format];
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(downloadUrl);
}

export async function importShowfile(payload: ShowfilePayload): Promise<ShowfileImportResponse> {
  const response = await fetch('/api/showfile/import', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    throw new Error(`Showfile import failed: ${response.status}`);
  }

  return response.json() as Promise<ShowfileImportResponse>;
}

export async function importShowFile(file: File): Promise<ShowfileImportResponse> {
  const formData = new FormData();
  formData.append('file', file, file.name);

  const response = await fetch('/api/showfile/import', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message = (detail as { detail?: string } | null)?.detail;
    throw new Error(message ?? `Showfile import failed: ${response.status}`);
  }

  return response.json() as Promise<ShowfileImportResponse>;
}
