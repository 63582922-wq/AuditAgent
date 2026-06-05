const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    ...(options?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(options?.headers as Record<string, string>),
  };
  if (API_KEY) headers["X-API-Key"] = API_KEY;

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    cache: "no-store",
  });
  if (!res.ok) {
    let msg = res.statusText;
    try {
      const body = await res.json();
      msg = body?.error?.message || body?.detail || msg;
    } catch {
      /* ignore */
    }
    throw new Error(msg);
  }
  return res.json();
}

export function downloadUrl(projectId: string, outputId: string) {
  const key = API_KEY ? `?api_key=${encodeURIComponent(API_KEY)}` : "";
  return `${API_BASE}/projects/${projectId}/outputs/${outputId}/download${key}`;
}

export type Project = {
  id: string;
  name: string;
  status: string;
  summary?: string;
  created_at: string;
  updated_at: string;
  state_json?: Record<string, unknown>;
  files?: FileRecord[];
  risks?: Risk[];
  outputs?: OutputRecord[];
};

export type FileRecord = {
  id: string;
  file_name: string;
  file_type: string;
  document_category: string;
  parse_status: string;
  confidence?: number;
};

export type Risk = {
  id: string;
  risk_id: string;
  risk_category: string;
  risk_subcategory?: string;
  risk_level: string;
  risk_score: number;
  problem: string;
  suggestion: string;
  analysis?: string;
  manual_review_required: boolean;
  status: string;
  evidence_json: Record<string, unknown>;
  source_location_json?: Record<string, unknown>;
};

export type OutputRecord = {
  id: string;
  output_type: string;
  file_name: string;
};

export type Memory = {
  id: string;
  memory_type: string;
  content: string;
  tags: string[];
};

export type Job = {
  id: string;
  project_id: string;
  status: string;
  current_step: string;
  progress_pct: number;
  error_message?: string;
};

export type AgentStatus = {
  mode: string;
  ready: boolean;
  message: string;
  text_model?: string;
  vision_model?: string;
  vision_ready?: boolean;
};

export type Stats = {
  project_count: number;
  risk_count: number;
  rule_count: number;
  high_count: number;
  medium_count: number;
  low_count: number;
};

export type ProjectSummary = {
  total_risks: number;
  high: number;
  medium: number;
  low: number;
  missing_documents: unknown[];
  correction_suggestions: string[];
};

export type Rule = {
  id: string;
  rule_id: string;
  rule_name: string;
  risk_category: string;
  risk_level: string;
  applicable_document_type?: string;
  enabled: boolean;
};
