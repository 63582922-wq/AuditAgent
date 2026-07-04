import type { Messages } from "./zh";
import type { WorkflowStep, WorkflowStepId } from "@/lib/workflow";

const STEP_META: { id: WorkflowStepId; pct: number; icon: string }[] = [
  { id: "created", pct: 0, icon: "◆" },
  { id: "uploaded", pct: 2, icon: "↑" },
  { id: "planning", pct: 5, icon: "◎" },
  { id: "classifying", pct: 10, icon: "▤" },
  { id: "parsing", pct: 25, icon: "⎘" },
  { id: "extracting", pct: 40, icon: "⬡" },
  { id: "running_rules", pct: 55, icon: "⚙" },
  { id: "cross_checking", pct: 75, icon: "⇄" },
  { id: "adjudicating", pct: 85, icon: "◉" },
  { id: "generating_report", pct: 90, icon: "⬇" },
  { id: "completed", pct: 100, icon: "✓" },
];

export function buildWorkflowSteps(messages: Messages): WorkflowStep[] {
  return STEP_META.map(({ id, pct, icon }) => {
    const s = messages.workflow.steps[id];
    return {
      id,
      pct,
      icon,
      label: s.label,
      short: s.short,
      desc: s.desc,
      agentSay: s.agentSay,
      agentDone: s.agentDone,
      station: s.station,
    };
  });
}

export function statusLabel(status: string, messages: Messages): string {
  return (
    messages.workflow.status[status] ||
    messages.workflow.logStatus[status] ||
    status
  );
}
