import type { ShowfileImportResponse, ShowfilePayload } from '../types/api';

export async function downloadShowfile(): Promise<void> {
  const response = await fetch('/api/showfile/export');
  if (!response.ok) {
    throw new Error(`Showfile export failed: ${response.status}`);
  }

  const blob = await response.blob();
  const downloadUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = downloadUrl;
  anchor.download = 'micwise-showfile.micwise.json';
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
