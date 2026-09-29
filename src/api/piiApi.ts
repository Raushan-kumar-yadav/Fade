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

export async function submitPIIRedactions(file: File, request: PIIRedactionRequest): Promise<any> {
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
    
    // 2. Upload it to the FADE library directly
    const uploadForm = new FormData();
    uploadForm.append('file', new File([blob], `sanitized_${file.name}`, { type: blob.type }));
    
    const uploadRes = await fetch(`http://127.0.0.1:${getPort()}/library/upload`, {
      method: 'POST',
      body: uploadForm,
    });
    
    if (!uploadRes.ok) {
      throw new Error(`Failed to upload sanitized file to library: ${uploadRes.statusText}`);
    }
    
    return await uploadRes.json();
  } catch (error) {
    console.error('[PII API] Submit error:', error);
    throw error;
  }
}
