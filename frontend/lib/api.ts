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

function isLegacyApiError(err: unknown): boolean {
  return err instanceof Error && (err.message === "Not Found" || err.message === "Method Not Allowed");
}

export function isNetworkError(err: unknown): boolean {
  return err instanceof TypeError && String(err.message).includes("fetch");
}

export async function fetchLatestJob(projectId: string): Promise<Job | null> {
  try {
    return await api<Job | null>(`/projects/${projectId}/jobs/latest`);
  } catch (e) {
    if (isLegacyApiError(e) || isNetworkError(e)) return null;
    throw e;
  }
}

export function projectToLive(p: Project): ProjectLive {
  return {
    id: p.id,
    name: p.name,
    status: p.status,
    summary: p.summary,
    created_at: p.created_at,
    updated_at: p.updated_at,
    state_json: p.state_json,
    file_count: p.files?.length ?? 0,
    risk_count: p.risks?.length ?? 0,
    output_count: p.outputs?.length ?? 0,
  };
}

export function projectToOverview(p: Project): ProjectOverview {
  const live = projectToLive(p);
  return {
    ...live,
    files: (p.files ?? []).map(({ id, file_name, document_category, parse_status }) => ({
      id,
      file_name,
      document_category,
      parse_status,
    })),
    risk_preview: (p.risks ?? [])
      .slice()
      .sort((a, b) => b.risk_score - a.risk_score)
      .slice(0, 6)
      .map(({ id, risk_level, problem }) => ({ id, risk_level, problem })),
  };
}

/** 优先 /live；旧版后端无此路由时回退到完整项目接口 */
export async function fetchProjectLive(projectId: string): Promise<ProjectLive | null> {
  try {
    return await api<ProjectLive>(`/projects/${projectId}/live`);
  } catch (e) {
    if (isNetworkError(e)) return null;
    if (!isLegacyApiError(e)) throw e;
    return projectToLive(await api<Project>(`/projects/${projectId}`));
  }
}

export async function fetchProjectOverview(projectId: string): Promise<ProjectOverview> {
  try {
    return await api<ProjectOverview>(`/projects/${projectId}/overview`);
  } catch (e) {
    if (!isLegacyApiError(e)) throw e;
    return projectToOverview(await api<Project>(`/projects/${projectId}`));
  }
}

export async function fetchProjectFiles(projectId: string): Promise<FileRecord[]> {
  try {
    return await api<FileRecord[]>(`/projects/${projectId}/files`);
  } catch (e) {
    if (isNetworkError(e)) return [];
    if (!isLegacyApiError(e)) throw e;
    const p = await api<Project>(`/projects/${projectId}`);
    return p.files ?? [];
  }
}

export function downloadUrl(projectId: string, outputId: string) {
  const key = API_KEY ? `?api_key=${encodeURIComponent(API_KEY)}` : "";
  return `${API_BASE}/projects/${projectId}/outputs/${outputId}/download${key}`;
}

/** 与后端 state_json 结构对齐的类型辅助 */
export type ProjectStateJson = {
  agent_plan?: {
    focus_areas?: string[];
    reasoning?: string;
    sub_agents?: { id: string; name: string; station: string; agent_say?: string }[];
    incremental?: boolean;
  };
  execution_graph?: {
    agent_message?: string;
    sub_agents?: { id: string; name: string; station: string }[];
    plan_steps?: string[];
  };
  runtime?: {
    scope?: string;
    execution_mode?: string;
    human_gate?: { pause?: boolean; reason?: string };
    critic?: { validated?: number; flagged?: number };
  };
  execution_mode?: string;
  mission?: {
    objective?: string;
    tasks?: { id: string; title: string; assignee_name: string }[];
    registered_agents?: { id: string; name: string; station: string; tools?: string[] }[];
  };
  deliverable?: {
    status?: "pending" | "accepted" | "rejected";
    comment?: string;
    accepted_at?: string;
    rejected_at?: string;
  };
  sub_agent_briefs?: Record<
    string,
    {
      summary?: string;
      findings?: string[];
      focus_risks?: string[];
      tools_used?: string[];
      title?: string;
    }
  >;
  synthesis_brief?: {
    summary?: string;
    priority_findings?: string[];
    coordination_notes?: string;
  };
  processed_file_ids?: string[];
  last_incremental?: { new_file_ids?: string[]; new_categories?: string[] };
};

export type ProjectLive = {
  id: string;
  name: string;
  status: string;
  summary?: string;
  created_at: string;
  updated_at: string;
  state_json?: ProjectStateJson;
  file_count: number;
  risk_count: number;
  output_count: number;
};

export type ProjectOverview = ProjectLive & {
  files: Pick<FileRecord, "id" | "file_name" | "document_category" | "parse_status">[];
  risk_preview: { id: string; risk_level: string; problem: string }[];
};

export type Project = {
  id: string;
  name: string;
  status: string;
  summary?: string;
  created_at: string;
  updated_at: string;
  state_json?: ProjectStateJson;
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
  execution_mode?: string;
  react_max_turns?: number;
  text_model?: string;
  text_base_url?: string;
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

export function acceptDeliverables(projectId: string) {
  return api<{ ok: boolean; status: string }>(`/projects/${projectId}/deliverables/accept`, {
    method: "POST",
  });
}

export function rejectDeliverables(projectId: string, comment?: string, reanalyze = false) {
  return api<{ ok: boolean; status: string; job_id?: string; message?: string }>(
    `/projects/${projectId}/deliverables/reject`,
    {
      method: "POST",
      body: JSON.stringify({ comment: comment || "", reanalyze }),
    }
  );
}
