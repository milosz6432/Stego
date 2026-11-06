export interface Detection {
  media_type: string;
  format: string;
  description: string;
  confidence: number;
  extension: string;
  applicable_modules: string[];
}

export interface FileInfo {
  id: string;
  name: string;
  size: number;
  sha256: string;
  media_type: string;
  format: string;
  mime: string;
  origin: string;
  parent_id: string | null;
  created_at: number;
  meta: Record<string, unknown>;
  detection: Detection;
}

export interface ToolInfo {
  name: string;
  available: boolean;
  path: string | null;
  description: string;
  install_hint: string;
}

export interface Job {
  id: string;
  kind: string;
  status: "queued" | "running" | "done" | "error" | "cancelled";
  progress: number;
  message: string;
  error: string | null;
  has_result: boolean;
}

export interface HexRow {
  offset: number;
  hex: string;
  ascii: string;
}

export interface Finding {
  title: string;
  method: string;
  score: number;
  reasons: string[];
  details: Record<string, any>;
  file_id: string | null;
}

export interface ScanResult {
  file_id: string;
  file_name: string;
  media_type: string;
  format: string;
  depth: string;
  finding_count: number;
  findings: Finding[];
  stored_payloads: string[];
}
