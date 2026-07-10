# UI / Architecture Audit - 2026-06-28

## Scope

AuditAgent is currently a project -> meeting -> review workflow. The real business unit is one observation meeting/case: import local folder, ingest materials, run analysis, review findings, generate deliverables, accept or reject.

## Current Flow

1. `/projects`: project list, batch operations, create entry.
2. `/projects/[id]`: project hub and meeting list.
3. `/projects/[id]/meetings/[meetingId]`: meeting workspace.
4. Meeting pages:
   - `files`: upload or supplement materials, run/re-run analysis.
   - `risks`: view findings.
   - `review`: optional line-by-line human review.
   - `outputs`: formal deliverable acceptance.
   - `logs`: execution trace.
5. Legacy project-level pages (`/projects/[id]/files|risks|review|outputs|logs`) only redirect to the first meeting. They should stay only as compatibility routes.

## UI Components

### Keep

- `AppShell`: global layout.
- `ProjectRail`: left navigation and current meeting phase.
- `MainAgentDrawer`: retained as implementation file but now renders a persistent `main-agent-panel`.
- `MeetingWorkShell`, `MeetingRunStage`, `LiveWorkflowGraph`, `LiveExecutionTrace`, `SettlingStage`: current meeting runtime visualization.
- `MeetingsManager`, `ProjectHubPageClient`, `FolderPicker`, `UploadDropzone`, `ActionButton`, `PageChrome`, `PreferencesBar`.
- `AgentBriefsPanel`, `ActivityTimeline`, `AgentGraph`: used by outputs/logs/runtime visualization.

### Removed

These were legacy or orphaned visual components with no route-level usage:

- `AgentCore`
- `CyberWorkflow`
- `FxPanel`
- `MeetingRunStrip`
- `MissionControl`
- `PipelineHud`
- `ProjectWorkflowBar`
- `RiskChart`
- `TechBackdrop`

### Still To Clean

- Some CSS selectors with historical names remain because current runtime views still reuse them (`mission-strip`, `cyber-flow`, `pipeline-hud`, `telemetry-tile`). They should be renamed only in a focused visual refactor.
- `MainAgentDrawer.tsx` should be renamed to `MainAgentPanel.tsx` after the current behavior stabilizes.

## Navigation And Entry Points

### Problems Found

- The same user intent appeared in multiple places: left rail links, meeting overview quick links, file page footer links, and main Agent action cards.
- Legacy project-level routes still exist, which is acceptable only as redirects, not as visible product concepts.
- The left rail currently acts as both navigation and workflow state. The main Agent also proposes workflow actions. This can feel like two command centers.

### Recommended Direction

- Left rail should be location/navigation only: project, meeting, files, findings, outputs, logs.
- Main Agent should be command/workflow surface: "what next", "supplement materials", "rerun", "accept/reject", "explain current status".
- Meeting overview quick links were removed because they duplicated the left rail and created a second equal-weight entry surface.

## Main Agent

### Current State

- Main Agent is now a persistent right-side panel in `AppShell`.
- The implementation file is still named `MainAgentDrawer.tsx`, but the runtime component renders `#main-agent-panel`.
- Frontend calls backend `/api/agent/chat`; the frontend keyword router is only a fallback when the backend chat call fails.
- Backend chat reads project / meeting status, files, findings, outputs, recent logs and retrieved memories.
- High-impact actions are returned as approval-gated action proposals and executed through `/api/agent/actions/{proposal_id}/approve`.

### Required True-Agent Architecture

1. Conversation memory scoped by project and meeting.
2. Tool/action proposal model:
   - navigate
   - upload/supplement materials
   - run/re-run analysis
   - regenerate outputs
   - accept/reject deliverables
3. Human approval gate for destructive or high-impact actions.
4. Execution trace written into existing logs.
5. Agent can answer open questions from project/meeting context, rules, files, findings, outputs, and memory.
6. Rule/memory self-repair must be added as a governed workflow, not as blind automatic learning.

## Deliverables

### Formal Deliverables To Show In Acceptance UI

- `deliverable_package`: ZIP package, primary download.
- `finding_pdf`: Finding report PDF.
- `finding_excel`: Finding list Excel.
- `observation_summary`: observation summary PDF.
- `evidence_index`: evidence index Excel.
- `material_parse_index`: material parse index Excel; required for OCR / layout auditability.
- `missing_docs`: missing documents list.
- `correction_list`: correction tracker.

### Internal Or Duplicate Outputs To Hide From Main Acceptance UI

- `risk_pdf`, `risk_excel`: compatibility aliases of `finding_pdf`, `finding_excel`.
- `deliverable_readme`: should be inside ZIP.
- `annotated_excel`, `annotated_image`: internal evidence/debug artifacts, not formal deliverables.
- OCR Markdown and layout JSON are included in the ZIP under `06_资料解析/`, but are not separate `output_type` rows.

The output page now filters to formal deliverables by default and includes `material_parse_index`.

## Frontend / Backend Consistency

### Preferred API Surface

- Meeting-scoped endpoints should be the primary frontend surface:
  - `/projects/{project_id}/meetings/{meeting_id}/files`
  - `/projects/{project_id}/meetings/{meeting_id}/risks`
  - `/projects/{project_id}/meetings/{meeting_id}/outputs`
  - `/projects/{project_id}/meetings/{meeting_id}/deliverables/accept`
  - `/projects/{project_id}/meetings/{meeting_id}/deliverables/reject`

### Legacy API Surface

- Project-scoped deliverables and outputs can stay as compatibility wrappers that resolve the first/default meeting.
- Frontend should not introduce new project-level workflow links.

## Copy And Interaction Notes

- "项目" and "子会议" are technically accurate but product language should emphasize "观察案件" and "观察资料包" where the user thinks in cases/folders.
- "逐条复核（可选）" is useful, but if a Finding needs more materials, the action should route to supplement materials rather than only mark a local review status.
- "验收通过" and "退回" must remain structured actions with explicit state writes, not chat-only commands until Agent action approval exists.

## Product Direction

The clean target shape:

- Left side: navigation and current scope.
- Center: structured work area for current task.
- Right side: persistent Main Agent that explains status, proposes next actions, and later executes approved actions.

The system should not split the same primary task across several equal-weight entry points. For each intent:

- Import/supplement materials: Agent action + Files page.
- Review findings: Agent action + Review page.
- Accept/reject deliverables: Agent action + Outputs page.
- Inspect execution: Agent action + Logs page.

## Verification Evidence

- Browser verified `/projects` on 2026-06-28: page loaded without connection refused, project count showed `0`, and the persistent Main Agent panel was visible.
- Screenshots saved:
  - `docs/audit-screenshots/2026-06-28-projects-empty-viewport.png`
  - `docs/audit-screenshots/2026-06-28-projects-empty-desktop.png`
- Batch deletion root cause was backend foreign-key coverage: new project child tables were not included in the cascade delete path. The delete path now dynamically deletes project-scoped child rows before deleting meetings/projects.
