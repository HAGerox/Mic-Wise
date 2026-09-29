import type { PhotoAssetResponse } from '../types/api';

export async function uploadPhotoAsset(file: File): Promise<PhotoAssetResponse> {
  const formData = new FormData();
  formData.append('file', file, file.name);

  const response = await fetch('/api/assets/photos', {
    method: 'POST',
    body: formData,
  });

  if (!response.ok) {
    const detail = await response.json().catch(() => null);
    const message = (detail as { detail?: string } | null)?.detail;
    throw new Error(message ?? `Photo upload failed: ${response.status}`);
  }

  return response.json() as Promise<PhotoAssetResponse>;
}
