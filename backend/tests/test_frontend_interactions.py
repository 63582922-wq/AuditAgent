from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read_frontend(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_projects_page_guards_large_selection_and_editing():
    source = read_frontend("frontend/app/projects/page.tsx")

    assert "PROJECTS_PAGE_SIZE" in source
    assert "visibleProjects" in source
    assert "filteredProjects" in source
    assert 'api<Project[]>("/projects", { cache: "no-store" })' in source
    assert "setSelected((prev)" in source
    assert "validIds" in source
    assert "batchBusy" in source
    assert "deleteBusyId" in source
    assert "savingId" in source
    assert "pageMsgKind" in source
    assert 'alert ${pageMsgKind}' in source
    assert "nameRequired" in source
    assert "visibleProjectIds" in source
    assert "deleteProjectsWithFallback" in source
    assert "remainingIds" in source
    assert "projects.deleteNone" in source
    assert "projects.deletedPartial" in source


def test_new_project_i18n_keys_are_defined_for_import_flow():
    zh = read_frontend("frontend/lib/i18n/zh.ts")
    en = read_frontend("frontend/lib/i18n/en.ts")

    required_keys = [
        "caseImportTitle",
        "caseImportHint",
        "caseImportNamePlaceholder",
        "caseImportPickFolder",
        "caseImportSubmit",
        "caseImporting",
        "executionModeTitle",
        "rulesModeLabel",
        "rulesModeHint",
        "agentModeLabel",
        "agentModeHint",
        "agentStatusChecking",
        "agentStatusReady",
        "agentModeUnavailable",
        "enteringCase",
    ]

    for key in required_keys:
        assert f"{key}:" in zh
        assert f"{key}:" in en


def test_meetings_manager_guards_large_selection_and_editing():
    source = read_frontend("frontend/components/MeetingsManager.tsx")

    assert "MEETINGS_PAGE_SIZE" in source
    assert "visibleMeetings" in source
    assert "filteredMeetings" in source
    assert "setSelected((prev)" in source
    assert "validIds" in source
    assert "busy" in source
    assert "msgKind" in source
    assert 'alert ${msgKind}' in source
    assert "codeRequired" in source
    assert "visibleMeetingIds" in source
    assert "meetings.searchPlaceholder" in source


def test_review_and_outputs_actions_have_busy_and_message_states():
    outputs = read_frontend("frontend/app/projects/[id]/meetings/[meetingId]/outputs/page.tsx")
    review = read_frontend("frontend/app/projects/[id]/meetings/[meetingId]/review/page.tsx")
    risks = read_frontend("frontend/app/projects/[id]/meetings/[meetingId]/risks/page.tsx")

    assert "actionMsgKind" in outputs
    assert 'alert ${actionMsgKind}' in outputs
    assert "outputsPage.rejectedReanalyze" in outputs
    assert "disabled={busy}" in outputs
    assert "PRIMARY_OUTPUT_TYPES" in outputs
    assert "INTERNAL_OUTPUT_TYPES" in outputs
    assert "visibleOutputs" in outputs
    assert "primaryDeliverable" in outputs
    assert "archiveOutput" in outputs
    assert "templateQuality" in outputs
    assert "complianceEvaluation" in outputs
    assert "outputsPage.evaluationTitle" in outputs
    assert "outputs-evaluation__metrics" in outputs
    assert "check.diagnosis" in outputs
    assert "outputsPage.evaluationRootCause" in outputs
    assert "outputsPage.evaluationEvidenceFiles" in outputs
    assert "outputsPage.qualityTitle" in outputs
    assert "outputs-quality__metrics" in outputs
    assert "owner_counts" in outputs
    assert "issue.owner" in outputs
    assert "issue.evidence_type" in outputs
    assert "outputsPage.primaryTitle" in outputs
    assert "outputsPage.archiveTitle" in outputs
    assert "outputs-deliverable-grid" in outputs
    assert '"fixed_template_excel",' in outputs
    assert outputs.index('"fixed_template_excel",') < outputs.index('"deliverable_package",')
    assert outputs.index('"material_parse_index",') > outputs.index("const INTERNAL_OUTPUT_TYPES")

    # 复核是审核结论的一部分；旧路径只保留兼容跳转，不能再维护第二套操作页面。
    assert "router.replace" in review
    assert "/risks" in review
    assert "messageKind" in risks
    assert 'alert ${messageKind}' in risks
    assert 'setBusy("regenerate")' in risks
    assert "disabled={!!busy}" in risks


def test_meeting_navigation_avoids_dead_and_duplicate_entry_points():
    rail = read_frontend("frontend/components/ProjectRail.tsx")
    overview = read_frontend("frontend/app/projects/[id]/meetings/[meetingId]/page.tsx")
    shell = read_frontend("frontend/components/AppShell.tsx")

    assert 'suffix: "/audit"' not in rail
    assert "rail.audit" not in rail
    assert "{projectId && meetingId && <ProjectRail" in shell
    assert "quick-link-grid" not in overview
    assert "quick-link-tile" not in overview
    assert "meetingOverview.quickLinks" not in overview


def test_settings_pages_have_feedback_and_busy_states():
    rules = read_frontend("frontend/app/settings/rules/page.tsx")
    memory = read_frontend("frontend/app/settings/memory/page.tsx")

    assert 'api<Rule[]>("/rules", { cache: "no-store" })' in rules
    assert "toggleBusyId" in rules
    assert 'alert ${msgKind}' in rules
    assert "disabled={busy || !!toggleBusyId}" in rules

    assert 'api<Memory[]>("/memories", { cache: "no-store" })' in memory
    assert "function reindex()" in memory
    assert "settings.reindexed" in memory
    assert 'alert ${msgKind}' in memory


def test_project_hub_edit_name_has_visible_validation():
    source = read_frontend("frontend/components/ProjectHubPageClient.tsx")

    assert "formMsg" in source
    assert "projects.nameRequired" in source
    assert "projects.saved" in source
    assert "function cancelEdit()" in source
    assert 'alert ${formMsgKind}' in source


def test_frontend_api_keeps_live_workflow_helpers_exported():
    source = read_frontend("frontend/lib/api.ts")

    assert "export function cancelJob" in source
    assert "export type RunEventsSnapshot" in source
    assert "export function fetchMeetingRunEvents" in source
    assert "export function harnessSupplementMeetingUpload" in source
    assert "/run-events" in source
    assert "/harness/supplement-upload" in source
    assert "/cancel" in source


def test_app_shell_mounts_persistent_main_agent_panel():
    source = read_frontend("frontend/components/AppShell.tsx")

    assert 'import { MainAgentDrawer } from "@/components/MainAgentDrawer";' in source
    assert "<MainAgentDrawer" in source
    assert "projectId={projectId}" in source
    assert "meetingId={meetingId}" in source
    assert "pathname={pathname}" in source
    assert "shell-agent" in source


def test_main_agent_panel_uses_live_context_and_routes_actions():
    source = read_frontend("frontend/components/MainAgentDrawer.tsx")

    assert "useProjectLiveOptional" in source
    assert "agentChat, approveAgentAction" in source
    assert "AgentCitation" in source
    assert "await agentChat" in source
    assert "normalizeRemoteActions" in source
    assert "requires_approval" in source
    assert "requiresApproval" in source
    assert "proposal_id" in source
    assert "proposalId" in source
    assert "main-agent-action__approval" in source
    assert "main-agent-action__controls" in source
    assert "main-agent-action__button" in source
    assert "main-agent-action__link" in source
    assert "buildTransportFailureReply" in source
    assert "mainAgent.transportError" in source
    assert "includesAny" not in source
    assert "mainAgent.messages.status" not in source
    assert "mainAgent.messages." in source
    assert "main-agent-message__mode" in source
    assert "main-agent-citations" in source
    assert "data-agent-action-card" in source
    assert "data-agent-proposal-id" in source
    assert "chatBusy" in source
    assert 'segment: "files"' in source
    assert 'segment: "risks"' in source
    assert 'id: "review"' in source
    assert 'segment: "review"' not in source
    assert 'segment: "outputs"' in source
    assert "hrefForAction" in source
    assert "main-agent-panel" in source
    assert "setOpen" not in source
    assert "main-agent-fab" not in source
    assert "main-agent-backdrop" not in source


def test_live_context_exposes_not_found_instead_of_fake_zero_state():
    api = read_frontend("frontend/lib/api.ts")
    context = read_frontend("frontend/contexts/ProjectLiveContext.tsx")
    overview = read_frontend("frontend/components/SettlingStage.tsx")

    assert "err.status = res.status" in api
    assert "export function isNotFoundError" in api
    assert "isNotFoundError(liveResult.reason)" in context
    assert "setNotFound(true)" in context
    assert "setLive(null)" in context
    assert "setTraceLogs([])" in context
    assert "notFound" in overview
    assert "errors.meetingNotFound" in overview
    assert "LiveWorkflowGraph" in overview


def test_runtime_graph_uses_only_persisted_run_events_not_a_static_topology():
    graph = read_frontend("frontend/components/AgentGraph.tsx")
    css = read_frontend("frontend/app/globals.css")

    assert 'data-runtime-graph="true"' in graph
    assert "traceLogs = []" in graph
    assert "categoryFor(log)" in graph
    assert "Every dot is an actual event" in graph
    assert "全量事件映射" in graph
    assert "knowledge-graph__event" in graph
    assert "knowledge-graph__controls" in graph
    assert "runtime-graph__surface" in graph
    assert "runtime-graph__mesh" in graph
    assert "runtime-graph__track-label" in graph
    assert "runtime-graph__trace" in graph
    assert "traceLogTitle" in graph
    assert ".knowledge-graph" in css
    assert "overflow-x: auto" in css
    assert "knowledge-graph__event--evidence" in css


def test_main_agent_panel_executes_high_risk_actions_through_proposals():
    source = read_frontend("frontend/components/MainAgentDrawer.tsx")
    zh = read_frontend("frontend/lib/i18n/zh.ts")
    en = read_frontend("frontend/lib/i18n/en.ts")
    api = read_frontend("frontend/lib/api.ts")

    assert "mainAgent.actions.accept" in source
    assert "mainAgent.actions.reject" in source
    assert "mainAgent.actions.reanalyze" in source
    assert "window.confirm" in source
    assert "window.prompt" in source
    assert "mainAgent.approvalConfirm" in source
    assert "mainAgent.rejectReasonPrompt" in source
    assert "mainAgent.approvalDone" in source
    assert "mainAgent.approvalFailed" in source
    assert "await approveAgentAction" in source
    assert ".then(" not in source
    assert "approveAction(action)" in source
    assert "approvalConfirm" in zh
    assert "rejectReasonPrompt" in zh
    assert "approvalDone" in en
    assert "approvalFailed" in en
    assert "export type AgentActionApproveResponse" in api
    assert "export function approveAgentAction" in api
    assert "/agent/actions/${proposalId}/approve" in api
    assert "proposal_id?: string | null" in api


def test_project_rail_has_one_concise_navigation_set_without_duplicate_stage_steps():
    rail = read_frontend("frontend/components/ProjectRail.tsx")
    zh = read_frontend("frontend/lib/i18n/zh.ts")

    assert "rail-steps__item" not in rail
    assert 'href: "/files"' not in rail
    assert 'href: "/risks"' not in rail
    assert 'href: "/outputs"' not in rail
    assert "当前案件" in zh
    assert "页面入口" in zh
    assert 'overview: "案件概览"' in zh
    assert 'files: "资料与证据"' in zh
    assert 'findings: "审核结论"' in zh


def test_activity_timeline_surfaces_code_level_trace_metadata():
    timeline = read_frontend("frontend/components/ActivityTimeline.tsx")

    assert "detail.code_location" in timeline
    assert "loc.file" in timeline
    assert "loc.line" in timeline
    assert "loc.function" in timeline
    assert "${file}:${line}" in timeline
