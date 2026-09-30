import { PIIDetection, PIIRedactionRequest } from '../workspaces/pii/PIITypes';

const getPort = () => (window as any).__FADE_PORT__ ?? 8000;

export async function fetchPIIDetections(file: File): Promise<PIIDetection[]> {
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('use_ner', 'true');

    const res = await fetch(`http://127.0.0.1:${getPort()}/pii/detect`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      throw new Error(`Failed to fetch PII detections: ${res.statusText}`);
    }
    const data = await res.json();
    return data.detections || [];
  } catch (error: any) {
    console.error('[PII API] Fetch error:', error);
    if (error instanceof TypeError && error.message === 'Failed to fetch') {
      throw new Error("Connection dropped. The backend may have crashed (e.g. missing Tesseract OCR dependency). Check backend console.");
    }
    throw error;
  }
}

export async function submitPIIRedactions(
  file: File,
  request: PIIRedactionRequest,
): Promise<any> {
  try {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('redaction_request', JSON.stringify(request));

    const res = await fetch(`http://127.0.0.1:${getPort()}/pii/sanitize`, {
      method: 'POST',
      body: formData,
    });
    if (!res.ok) {
      throw new Error(`Failed to submit PII redactions: ${res.statusText}`);
    }

    // Get the sanitized blob
    const blob = await res.blob();

    // 1. Download it locally for the user
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `sanitized_${file.name}`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);

    // 2. Upload it to the FADE library
    const uploadForm = new FormData();
    uploadForm.append('file', new File([blob], `sanitized_${file.name}`, { type: blob.type }));

    const uploadRes = await fetch(`http://127.0.0.1:${getPort()}/library/upload`, {
      method: 'POST',
      body: uploadForm,
    });

    if (!uploadRes.ok) {
      throw new Error(`Failed to upload sanitized file to library: ${uploadRes.statusText}`);
    }

    const uploadData = await uploadRes.json();
    const sanitizedAssetId: string = uploadData.assetId;
    const originalAssetId: string  = request.asset_id;

    // 3. Register the security boundary:
    //    - marks original RESTRICTED (blocks it from AI/LLM)
    //    - marks sanitized SANITIZED (approved for AI/LLM)
    //    - swaps all timeline clips that referenced originalAssetId
    if (sanitizedAssetId && originalAssetId) {
      try {
        const regRes = await fetch(`http://127.0.0.1:${getPort()}/pii/register-sanitized`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ originalAssetId, sanitizedAssetId }),
        });
        if (regRes.ok) {
          const regData = await regRes.json();
          console.log(
            `[PII] Security boundary registered: original=${originalAssetId.slice(0, 8)} RESTRICTED, ` +
            `sanitized=${sanitizedAssetId.slice(0, 8)} SANITIZED, ` +
            `clips swapped=${regData.clipsSwapped}`,
          );
        } else {
          console.warn('[PII] register-sanitized failed:', regRes.status, regRes.statusText);
        }
      } catch (regErr) {
        // Non-fatal — the sanitized file is already in the library; log and continue
        console.warn('[PII] Could not call register-sanitized (non-fatal):', regErr);
      }
    }

    return uploadData;
  } catch (error) {
    console.error('[PII API] Submit error:', error);
    throw error;
  }
}

/**
 * Fetch the current PII security state for a library asset.
 * Returns "NONE" | "RESTRICTED" | "SANITIZED".
 */
export async function fetchAssetSecurityState(assetId: string): Promise<{
  assetId: string;
  securityState: 'NONE' | 'RESTRICTED' | 'SANITIZED';
  sanitizedAssetId: string | null;
  originalAssetId: string | null;
}> {
  const res = await fetch(`http://127.0.0.1:${getPort()}/pii/security-state/${assetId}`);
  if (!res.ok) {
    throw new Error(`Failed to fetch security state for ${assetId}: ${res.statusText}`);
  }
  return res.json();
}

/**
 * Directly register an existing (already-uploaded) sanitized asset without
 * going through the full sanitize flow. Useful for re-registration or testing.
 */
export async function registerSanitizedAsset(
  originalAssetId: string,
  sanitizedAssetId: string,
): Promise<any> {
  const res = await fetch(`http://127.0.0.1:${getPort()}/pii/register-sanitized`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ originalAssetId, sanitizedAssetId }),
  });
  if (!res.ok) {
    throw new Error(`register-sanitized failed: ${res.statusText}`);
  }
  return res.json();
}

