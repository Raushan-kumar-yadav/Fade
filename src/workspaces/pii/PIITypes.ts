export type PIISource = 'automatic' | 'manual';

export interface PIIBoundingBox {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface PIIDetection {
  id: string;
  type: string;
  confidence?: number;
  source: PIISource;
  enabled: boolean;

  // Image/video
  bbox?: PIIBoundingBox;
  coordinateSpace?: string;
  sourceWidth?: number;
  sourceHeight?: number;

  // Text
  start?: number;
  end?: number;

  // Video
  frameStart?: number;
  frameEnd?: number;
  frames?: Record<string, PIIBoundingBox>;
}

export type PIIReviewStatus = 'REVIEWING' | 'CONFIRMED' | 'SANITIZING' | 'SANITIZED' | 'ERROR';

export interface PIIReviewState {
  assetId: string;
  detections: PIIDetection[];
  status: PIIReviewStatus;
  errors?: string[];
}

export interface PIIRedactionRequest {
  asset_id: string;
  asset_type: 'image' | 'video' | 'text';
  redactions: PIIDetection[];
}
