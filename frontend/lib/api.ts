const API_BASE = process.env.NEXT_PUBLIC_API_BASE || "http://localhost:8000/api";
const API_KEY = process.env.NEXT_PUBLIC_API_KEY || "";
const PRIMARY_DELIVERABLE_TYPES = new Set(["fixed_template_excel", "deliverable_package"]);

export async function api<T>(path: string, options?: RequestInit): Promise<T> {
  const headers: Record<string, string> = {
    ...(options?.body instanceof FormData ? {} : { "Content-Type": "application/json" }),
    ...(options?.headers as Record<string, string>),
  };
  if (API_KEY) headers["X-API-Key"] = API_KEY;

  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    cache: options?.cache ?? "default",
  });
  if (!res.ok) {
    let msg = res.statusText;
    let code: string | null = null;
    try {
      const body = await res.json();
      msg = body?.error?.message || body?.detail || msg;
      code = body?.error?.code || null;
    } catch {
      /* ignore */
    }
    if (res.status === 404 && path.includes("harness") && path.includes("upload")) {
      throw new Error("NOT_FOUND_UPLOAD_API");
    }
    const err = new Error(msg) as Error & { code?: string | null; status?: number };
    err.code = code;
    err.status = res.status;
    throw err;
  }
  return res.json();
}

function isLegacyApiError(err: unknown): boolean {
  return err instanceof Error && (err.message === "Not Found" || err.message === "Method Not Allowed");
}

export function isNetworkError(err: unknown): boolean {
  return err instanceof TypeError && String(err.message).includes("fetch");
}

export function isNotFoundError(err: unknown): boolean {
  return err instanceof Error && (err as Error & { status?: number }).status === 404;
}

export async function fetchLatestJob(projectId: string, meetingId?: string): Promise<Job | null> {
  const path = meetingId
    ? `/projects/${projectId}/meetings/${meetingId}/jobs/latest`
    : `/projects/${projectId}/jobs/latest`;
  try {
    return await api<Job | null>(path, { cache: "no-store" });
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
    output_count: (p.outputs ?? []).filter((output) => PRIMARY_DELIVERABLE_TYPES.has(output.output_type)).length,
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
export async function fetchProjectLive(projectId: string, meetingId?: string): Promise<ProjectLive | null> {
  const path = meetingId
    ? `/projects/${projectId}/meetings/${meetingId}/live`
    : `/projects/${projectId}/live`;
  try {
    return await api<ProjectLive>(path, { cache: "no-store" });
  } catch (e) {
    if (isNetworkError(e)) return null;
    if (!isLegacyApiError(e)) throw e;
    return projectToLive(await api<Project>(`/projects/${projectId}`));
  }
}

export async function fetchMeetingFiles(projectId: string, meetingId: string): Promise<FileRecord[]> {
  return api<FileRecord[]>(`/projects/${projectId}/meetings/${meetingId}/files`);
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
    critic?: {
      validated?: number;
      flagged?: number;
      readjudicate_rounds?: number;
      outputs_regenerated?: boolean;
      llm_enabled?: boolean;
    };
  };
  execution_mode?: string;
  agent_domain?: string;
  runtime_live?: {
    message?: string;
    step?: string;
    pct?: number;
    progress?: number;
    sub_agents?: { id: string; name: string; station: string; agent_say?: string }[];
  };
  rule_outcomes?: {
    rule_id?: string;
    rule_name?: string;
    status?: "passed" | "finding" | "needs_review" | "not_applicable" | string;
    reason?: string | null;
    evidence?: Record<string, unknown>;
  }[];
  evidence_gate?: {
    blocked?: boolean;
    reason?: string;
    required_fact_keys?: string[];
    blocked_fact_keys?: string[];
    conflict_fact_keys?: string[];
  };
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
    template_quality?: {
      status?: "pass" | "needs_review" | "fail";
      total_fields?: number;
      assessed_fields?: number;
      completion_rate?: number;
      review_required?: boolean;
      counts?: Record<string, number>;
      owner_counts?: Record<string, number>;
      issue_fields?: {
        column?: number;
        header?: string;
        value?: string;
        quality?: string;
        owner?: string;
        evidence_type?: string;
        handoff_required?: boolean;
        issue?: string;
        action?: string;
      }[];
      issue_field_count?: number;
      generated_at?: string;
    };
    evaluation?: {
      status?: "completed" | "skipped" | "failed";
      case_id?: string;
      case_name?: string;
      meeting_code?: string;
      passed?: boolean | null;
      critical_failures?: number;
      warning_failures?: number;
      total_checks?: number;
      passed_checks?: number;
      reason?: string;
      generated_at?: string;
      failed_checks?: {
        check_id?: string;
        severity?: string;
        expected?: unknown;
        actual?: unknown;
        message?: string;
        diagnosis?: {
          stage?: string;
          root_cause?: string;
          remediation?: string;
          target_category?: string;
          field?: string;
          source_path?: string;
          output_type?: string;
          file_name?: string;
          candidate_files?: {
            file_id?: string;
            file_name?: string;
            current_category?: string;
            reason?: string;
          }[];
          related_files?: {
            file_id?: string;
            file_name?: string;
            current_category?: string;
            related_category?: string;
          }[];
          loose_outputs?: {
            output_type?: string;
            file_name?: string;
          }[];
        };
      }[];
    };
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

export type Meeting = {
  id: string;
  project_id: string;
  meeting_code: string;
  meeting_title?: string;
  observation_type?: string;
  meeting_type?: string;
  meeting_date?: string;
  status: string;
  summary?: string;
  state_json?: ProjectStateJson;
  deliverable_json?: Record<string, unknown>;
  file_count?: number;
  risk_count?: number;
  output_count?: number;
  created_at: string;
  updated_at: string;
  last_run_at?: string;
};

export function fetchMeetings(projectId: string) {
  return api<Meeting[]>(`/projects/${projectId}/meetings`, { cache: "no-store" });
}

export function createMeeting(
  projectId: string,
  payload: {
    meeting_code: string;
    meeting_title?: string;
    observation_type?: string;
    meeting_type?: string;
    meeting_date?: string;
  }
) {
  return api<Meeting>(`/projects/${projectId}/meetings`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateMeeting(
  projectId: string,
  meetingId: string,
  payload: Partial<{
    meeting_code: string;
    meeting_title: string;
    observation_type: string;
    meeting_type: string;
    meeting_date: string;
    summary: string;
  }>
) {
  return api<Meeting>(`/projects/${projectId}/meetings/${meetingId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteMeeting(projectId: string, meetingId: string) {
  return api<{ ok: boolean }>(`/projects/${projectId}/meetings/${meetingId}`, { method: "DELETE" });
}

export function batchDeleteMeetings(projectId: string, meetingIds: string[]) {
  return api<{ ok: boolean; deleted: number }>(`/projects/${projectId}/meetings/batch-delete`, {
    method: "POST",
    body: JSON.stringify({ meeting_ids: meetingIds }),
  });
}

export function updateProject(projectId: string, payload: { name?: string; summary?: string }) {
  return api<Project>(`/projects/${projectId}`, { method: "PATCH", body: JSON.stringify(payload) });
}

export function batchDeleteProjects(projectIds: string[]) {
  return api<{ ok: boolean; deleted: number }>("/projects/batch-delete", {
    method: "POST",
    body: JSON.stringify({ project_ids: projectIds }),
  });
}

export type AgentChatMessage = {
  role: "agent" | "user";
  content: string;
};

export type AgentChatAction = {
  id: string;
  label: string;
  description: string;
  segment: string;
  proposal_id?: string | null;
  requires_meeting?: boolean;
  requires_approval?: boolean;
  tone?: "default" | "warning";
};

export type AgentCitation = {
  fact_key: string;
  value: unknown;
  status: "accepted" | "conflict" | "needs_review" | "missing" | string;
  confidence: number;
  source: {
    file_id?: string | null;
    page_number?: number | null;
    evidence?: string | null;
    source_kind?: string | null;
  };
};

export type AgentChatResponse = {
  reply: string;
  answer?: string;
  actions: AgentChatAction[];
  planned_actions?: AgentChatAction[];
  citations?: AgentCitation[];
  intent?: "consult" | "analysis_request" | "operation" | "learning_feedback" | string;
  mode: "llm" | "fallback" | string;
  context: Record<string, unknown>;
};

export function agentChat(payload: {
  message: string;
  project_id?: string | null;
  meeting_id?: string | null;
  history?: AgentChatMessage[];
}) {
  return api<AgentChatResponse>("/agent/chat", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type AgentActionApproveResponse = {
  ok: boolean;
  proposal_id: string;
  action_id: string;
  status: string;
  message?: string;
  job_id?: string;
};

export function approveAgentAction(proposalId: string, comment?: string) {
  const trimmedComment = comment?.trim();
  return api<AgentActionApproveResponse>(`/agent/actions/${proposalId}/approve`, {
    method: "POST",
    body: JSON.stringify(trimmedComment ? { comment: trimmedComment } : {}),
  });
}

export type AgentFeedbackResponse = {
  ok: boolean;
  proposal_id: string;
  status: string;
  message: string;
};

export function submitAgentFeedback(payload: {
  feedback: string;
  project_id: string;
  meeting_id?: string | null;
  original_conclusion?: string;
}) {
  return api<AgentFeedbackResponse>("/agent/feedback", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export type Job = {
  id: string;
  project_id: string;
  meeting_id?: string;
  status: string;
  current_step: string;
  progress_pct: number;
  error_message?: string;
};

export type RunEvent = {
  id: string;
  step: string;
  status: string;
  kind: string;
  category: string;
  severity: string;
  name: string;
  message: string;
  duration_ms?: number | null;
  created_at?: string | null;
  detail?: Record<string, unknown>;
};

export type RunEventsSnapshot = {
  available: boolean;
  version: string;
  project_id: string;
  meeting_id: string;
  summary: {
    event_count: number;
    tool_event_count: number;
    failed_event_count: number;
    running_event_count: number;
    open_running_event_count: number;
    skipped_event_count: number;
    duration_ms_total: number;
    status_counts: Record<string, number>;
    category_counts: Record<string, number>;
    first_event_at?: string | null;
    last_event_at?: string | null;
  };
  health: {
    level: string;
    signals: string[];
  };
  events: RunEvent[];
};

export function emptyRunEventsSnapshot(projectId: string, meetingId: string): RunEventsSnapshot {
  return {
    available: false,
    version: "",
    project_id: projectId,
    meeting_id: meetingId,
    summary: {
      event_count: 0,
      tool_event_count: 0,
      failed_event_count: 0,
      running_event_count: 0,
      open_running_event_count: 0,
      skipped_event_count: 0,
      duration_ms_total: 0,
      status_counts: {},
      category_counts: {},
    },
    health: {
      level: "blocked",
      signals: ["no_events"],
    },
    events: [],
  };
}

export function fetchMeetingRunEvents(projectId: string, meetingId: string) {
  return api<RunEventsSnapshot>(`/projects/${projectId}/meetings/${meetingId}/run-events`, {
      cache: "no-store",
    })
    .catch((e) => {
    if (isLegacyApiError(e) || isNetworkError(e)) return emptyRunEventsSnapshot(projectId, meetingId);
    throw e;
    });
}

export type EvidenceFact = {
  fact_key: string;
  value: unknown;
  status: "accepted" | "conflict" | "needs_review" | "missing" | string;
  confidence: number;
  sources: Record<string, unknown>;
  conflicts?: unknown[] | null;
};

export type MeetingEvidenceSnapshot = {
  run_id: string | null;
  claims: {
    id: string;
    fact_key: string;
    value: unknown;
    file_id?: string | null;
    page_number?: number | null;
    confidence: number;
    status: string;
    evidence?: string | null;
    source_kind: string;
  }[];
  facts: EvidenceFact[];
  gate: {
    blocked: boolean;
    reason: string;
    required_fact_keys?: string[];
    blocked_fact_keys?: string[];
    conflict_fact_keys?: string[];
  };
};

export function fetchMeetingEvidence(projectId: string, meetingId: string) {
  return api<MeetingEvidenceSnapshot>(`/projects/${projectId}/meetings/${meetingId}/evidence`, {
    cache: "no-store",
  });
}

export function cancelJob(projectId: string, jobId: string, meetingId?: string) {
  const path = meetingId
    ? `/projects/${projectId}/meetings/${meetingId}/jobs/${jobId}/cancel`
    : `/projects/${projectId}/jobs/${jobId}/cancel`;
  return api<Job>(path, { method: "POST" });
}

export type AgentStatus = {
  mode: string;
  ready: boolean;
  rules_ready?: boolean;
  full_agent_ready?: boolean;
  message: string;
  agent_domain?: string;
  domain_label?: string;
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

export function acceptMeetingDeliverables(projectId: string, meetingId: string) {
  return api<{ ok: boolean; status: string }>(
    `/projects/${projectId}/meetings/${meetingId}/deliverables/accept`,
    { method: "POST" }
  );
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

export function rejectMeetingDeliverables(
  projectId: string,
  meetingId: string,
  comment?: string,
  reanalyze = false
) {
  return api<{ ok: boolean; status: string; job_id?: string; message?: string }>(
    `/projects/${projectId}/meetings/${meetingId}/deliverables/reject`,
    {
      method: "POST",
      body: JSON.stringify({ comment: comment || "", reanalyze }),
    }
  );
}

export type HarnessResult = {
  project_id: string;
  meeting_id?: string;
  status: string;
  meeting_code?: string;
  finding_count?: number;
  meeting_case?: Record<string, unknown>;
  runtime?: Record<string, unknown>;
  job_id?: string;
  message?: string;
};

export type HarnessRunOptions = {
  skipOrchestrator?: boolean;
  orchestratorMaxTasks?: number;
  visionMaxFiles?: number;
  runMode?: string;
};

function harnessRunPayload(options?: boolean | HarnessRunOptions) {
  const normalized = typeof options === "boolean" ? { skipOrchestrator: options } : options || {};
  return {
    skip_orchestrator: Boolean(normalized.skipOrchestrator),
    orchestrator_max_tasks: normalized.orchestratorMaxTasks,
    vision_max_files: normalized.visionMaxFiles,
    run_mode: normalized.runMode,
  };
}

export function harnessImportCase(casePath: string, projectName?: string) {
  return api<HarnessResult>("/harness/import", {
    method: "POST",
    body: JSON.stringify({ case_path: casePath, project_name: projectName || undefined }),
  });
}

export function harnessRunCase(casePath: string, projectName?: string) {
  return api<HarnessResult>("/harness/run-case", {
    method: "POST",
    body: JSON.stringify({ case_path: casePath, project_name: projectName || undefined }),
  });
}

function inferMeetingCodeFromFiles(files: File[]): string {
  for (const f of files) {
    const m = f.name.match(/A1P\d+/i);
    if (m) return m[0].toUpperCase();
  }
  const rel = (files[0] as File & { webkitRelativePath?: string })?.webkitRelativePath || files[0]?.name || "";
  const m = rel.match(/A1P\d+/i);
  return m ? m[0].toUpperCase() : "UNKNOWN";
}

async function harnessRunCaseUploadFallback(
  files: File[],
  projectName?: string,
  options?: HarnessRunOptions
): Promise<HarnessResult> {
  const code = inferMeetingCodeFromFiles(files);
  const project = await api<Project>("/projects", {
    method: "POST",
    body: JSON.stringify({ name: projectName?.trim() || `观察项目 ${code}` }),
  });
  const form = new FormData();
  for (const file of files) {
    form.append("files", file, file.name);
  }
  await api<{ uploaded: string[] }>(`/projects/${project.id}/files`, { method: "POST", body: form });
  const meetings = await fetchMeetings(project.id);
  const meetingId = meetings[0]?.id;
  if (!meetingId) throw new Error("子会议创建失败");
  return harnessRunProject(project.id, meetingId, options);
}

export function harnessRunCaseUpload(files: File[], projectName?: string, options?: HarnessRunOptions) {
  const form = new FormData();
  if (projectName?.trim()) form.append("project_name", projectName.trim());
  form.append("skip_orchestrator", options?.skipOrchestrator ? "true" : "false");
  if (options?.orchestratorMaxTasks != null) form.append("orchestrator_max_tasks", String(options.orchestratorMaxTasks));
  if (options?.visionMaxFiles != null) form.append("vision_max_files", String(options.visionMaxFiles));
  if (options?.runMode) form.append("run_mode", options.runMode);
  for (const file of files) {
    const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
    form.append("files", file, rel);
  }
  return api<HarnessResult>("/harness/run-case-upload", {
    method: "POST",
    body: form,
  }).catch((err) => {
    if (err instanceof Error && err.message === "NOT_FOUND_UPLOAD_API") {
      return harnessRunCaseUploadFallback(files, projectName, options);
    }
    if (err instanceof Error && err.message === "Not Found") {
      return harnessRunCaseUploadFallback(files, projectName, options);
    }
    throw err;
  });
}

export function harnessImportCaseUpload(files: File[], projectName?: string) {
  const form = new FormData();
  if (projectName?.trim()) form.append("project_name", projectName.trim());
  for (const file of files) {
    const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
    form.append("files", file, rel);
  }
  return api<HarnessResult>("/harness/import-upload", {
    method: "POST",
    body: form,
  });
}

export function harnessImportToProject(
  projectId: string,
  files: File[],
  options?: { meetingTitle?: string; runAnalysis?: boolean }
) {
  const form = new FormData();
  if (options?.meetingTitle?.trim()) form.append("meeting_title", options.meetingTitle.trim());
  form.append("run_analysis", options?.runAnalysis !== false ? "true" : "false");
  for (const file of files) {
    const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
    form.append("files", file, rel);
  }
  return api<HarnessResult>(`/projects/${projectId}/harness/import-upload`, {
    method: "POST",
    body: form,
  });
}

export function harnessRunProject(projectId: string, meetingId: string, options?: boolean | HarnessRunOptions) {
  return api<HarnessResult>(`/projects/${projectId}/meetings/${meetingId}/harness/run`, {
    method: "POST",
    body: JSON.stringify(harnessRunPayload(options)),
  });
}

export function harnessSupplementMeetingUpload(
  projectId: string,
  meetingId: string,
  files: File[],
  options?: { runAnalysis?: boolean; skipOrchestrator?: boolean }
) {
  const form = new FormData();
  form.append("run_analysis", options?.runAnalysis === false ? "false" : "true");
  form.append("skip_orchestrator", options?.skipOrchestrator ? "true" : "false");
  for (const file of files) {
    const rel = (file as File & { webkitRelativePath?: string }).webkitRelativePath || file.name;
    form.append("files", file, rel);
  }
  return api<HarnessResult>(`/projects/${projectId}/meetings/${meetingId}/harness/supplement-upload`, {
    method: "POST",
    body: form,
  });
}

export function harnessRunProjectLegacy(projectId: string, skipOrchestrator = false, meetingId?: string) {
  return api<HarnessResult>(`/projects/${projectId}/harness/run`, {
    method: "POST",
    body: JSON.stringify({ skip_orchestrator: skipOrchestrator, meeting_id: meetingId }),
  });
}
