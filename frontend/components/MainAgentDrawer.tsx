"use client";

import Link from "next/link";
import { FormEvent, useEffect, useMemo, useRef, useState } from "react";
import { useProjectLiveOptional } from "@/contexts/ProjectLiveContext";
import { agentChat, approveAgentAction } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { statusLabel } from "@/lib/i18n/workflow-steps";

type Translate = (key: string, vars?: Record<string, string | number>) => string;
type AgentActionSegment = "projects" | "files" | "risks" | "review" | "outputs" | "logs";

type AgentAction = {
  id: string;
  labelKey?: string;
  descKey?: string;
  label?: string;
  description?: string;
  segment: AgentActionSegment;
  proposalId?: string | null;
  requiresMeeting?: boolean;
  requiresApproval?: boolean;
  tone?: "default" | "warning";
};

type AgentMessage = {
  id: string;
  role: "agent" | "user";
  text: string;
  actions?: AgentAction[];
  mode?: "live" | "fallback" | "offline";
};

type ReplyContext = {
  projectId: string | null;
  meetingId: string | null;
  liveStatus: string;
  files: number | string;
  findings: number | string;
  outputs: number | string;
  jobStatus: string;
  progress: number | string;
  offline: boolean;
  notFound: boolean;
};

const ACTION_PROJECTS: AgentAction = {
  id: "projects",
  labelKey: "mainAgent.actions.projects",
  descKey: "mainAgent.actions.projectsDesc",
  segment: "projects",
};

const ACTION_FILES: AgentAction = {
  id: "files",
  labelKey: "mainAgent.actions.files",
  descKey: "mainAgent.actions.filesDesc",
  segment: "files",
  requiresMeeting: true,
};

const ACTION_FINDINGS: AgentAction = {
  id: "risks",
  labelKey: "mainAgent.actions.findings",
  descKey: "mainAgent.actions.findingsDesc",
  segment: "risks",
  requiresMeeting: true,
};

const ACTION_REVIEW: AgentAction = {
  id: "review",
  labelKey: "mainAgent.actions.review",
  descKey: "mainAgent.actions.reviewDesc",
  segment: "review",
  requiresMeeting: true,
};

const ACTION_OUTPUTS: AgentAction = {
  id: "outputs",
  labelKey: "mainAgent.actions.outputs",
  descKey: "mainAgent.actions.outputsDesc",
  segment: "outputs",
  requiresMeeting: true,
};

const ACTION_LOGS: AgentAction = {
  id: "logs",
  labelKey: "mainAgent.actions.logs",
  descKey: "mainAgent.actions.logsDesc",
  segment: "logs",
  requiresMeeting: true,
};

const ACTION_ACCEPT: AgentAction = {
  id: "accept",
  labelKey: "mainAgent.actions.accept",
  descKey: "mainAgent.actions.acceptDesc",
  segment: "outputs",
  requiresMeeting: true,
  requiresApproval: true,
  tone: "warning",
};

const ACTION_REJECT: AgentAction = {
  id: "reject",
  labelKey: "mainAgent.actions.reject",
  descKey: "mainAgent.actions.rejectDesc",
  segment: "outputs",
  requiresMeeting: true,
  requiresApproval: true,
  tone: "warning",
};

const ACTION_REANALYZE: AgentAction = {
  id: "reanalyze",
  labelKey: "mainAgent.actions.reanalyze",
  descKey: "mainAgent.actions.reanalyzeDesc",
  segment: "files",
  requiresMeeting: true,
  requiresApproval: true,
  tone: "warning",
};

function uid(prefix: string) {
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function normalizeSegment(segment: string): AgentActionSegment {
  if (segment === "files" || segment === "risks" || segment === "review" || segment === "outputs" || segment === "logs") {
    return segment;
  }
  return "projects";
}

function normalizeRemoteActions(
  actions: {
    id: string;
    label: string;
    description: string;
    segment: string;
    proposal_id?: string | null;
    requires_meeting?: boolean;
    requires_approval?: boolean;
    tone?: "default" | "warning";
  }[]
) {
  return actions.map((action) => ({
    id: action.id,
    label: action.label,
    description: action.description,
    segment: normalizeSegment(action.segment),
    proposalId: action.proposal_id,
    requiresMeeting: action.requires_meeting,
    requiresApproval: action.requires_approval,
    tone: action.tone,
  }));
}

function actionLabel(action: AgentAction, t: Translate) {
  return action.label ?? (action.labelKey ? t(action.labelKey) : action.id);
}

function actionDescription(action: AgentAction, t: Translate) {
  return action.description ?? (action.descKey ? t(action.descKey) : "");
}

export function hrefForAction(action: AgentAction, projectId: string | null, meetingId: string | null) {
  if (action.segment === "projects" || !projectId) return "/projects";
  if (!meetingId || action.requiresMeeting) {
    return meetingId
      ? `/projects/${projectId}/meetings/${meetingId}/${action.segment}`
      : `/projects/${projectId}`;
  }
  return `/projects/${projectId}`;
}

export function buildTransportFailureReply(ctx: ReplyContext, t: Translate) {
  if (ctx.notFound) {
    return {
      text: `${t("errors.notFound")}：${t("errors.meetingNotFound")}`,
      actions: [ACTION_PROJECTS],
      mode: "offline" as const,
    };
  }

  return {
    text: ctx.offline ? t("mainAgent.messages.offline") : t("mainAgent.transportError"),
    actions: ctx.meetingId ? [ACTION_LOGS, ACTION_FILES, ACTION_REVIEW] : [ACTION_PROJECTS],
    mode: "offline" as const,
  };
}

function buildWelcome(projectId: string | null, meetingId: string | null, t: Translate, notFound = false): AgentMessage {
  if (notFound) {
    return {
      id: "welcome",
      role: "agent",
      text: `${t("errors.notFound")}：${t("errors.meetingNotFound")}`,
      actions: [ACTION_PROJECTS],
    };
  }
  return {
    id: "welcome",
    role: "agent",
    text: meetingId
      ? t("mainAgent.messages.welcomeMeeting")
      : projectId
        ? t("mainAgent.messages.welcomeProject")
        : t("mainAgent.messages.welcomeGlobal"),
    actions: meetingId ? [ACTION_FILES, ACTION_REVIEW, ACTION_OUTPUTS] : [ACTION_PROJECTS],
    mode: "live",
  };
}

function messageModeLabel(mode: AgentMessage["mode"], t: Translate) {
  if (mode === "offline") return t("mainAgent.modeOffline");
  if (mode === "fallback") return t("mainAgent.modeFallback");
  if (mode === "live") return t("mainAgent.modeLive");
  return "";
}

export function MainAgentDrawer({
  projectId,
  meetingId,
  pathname,
}: {
  projectId: string | null;
  meetingId: string | null;
  pathname: string;
}) {
  const [draft, setDraft] = useState("");
  const [messages, setMessages] = useState<AgentMessage[]>([]);
  const [chatBusy, setChatBusy] = useState(false);
  const [approvingId, setApprovingId] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const liveCtx = useProjectLiveOptional();
  const { t, messages: catalog } = useI18n();

  useEffect(() => {
    setMessages([buildWelcome(projectId, meetingId, t, liveCtx?.notFound ?? false)]);
    setDraft("");
  }, [projectId, meetingId, liveCtx?.notFound, t]);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
  }, [messages]);

  const replyContext = useMemo<ReplyContext>(() => {
    const live = liveCtx?.live ?? null;
    const job = liveCtx?.job ?? null;
    const liveStatus = live?.status ? statusLabel(live.status, catalog) : t("mainAgent.statusUnknown");
    const jobStatus = job?.status ? statusLabel(job.status, catalog) : t("mainAgent.noJob");
    return {
      projectId,
      meetingId,
      liveStatus,
      files: live?.file_count ?? "-",
      findings: live?.risk_count ?? "-",
      outputs: live?.output_count ?? "-",
      jobStatus,
      progress: job?.progress_pct ?? live?.state_json?.runtime_live?.pct ?? 0,
      offline: liveCtx?.offline ?? false,
      notFound: liveCtx?.notFound ?? false,
    };
  }, [catalog, liveCtx?.job, liveCtx?.live, liveCtx?.offline, liveCtx?.notFound, meetingId, projectId, t]);

  const scopeLabel = meetingId
    ? t("mainAgent.meetingScope", { meetingId })
    : projectId
      ? t("mainAgent.projectScope", { projectId })
      : t("mainAgent.globalScope");

  const liveSummary = replyContext.notFound
    ? `${t("errors.notFound")} · ${t("errors.meetingNotFound")}`
    : t("mainAgent.liveSummary", {
        status: replyContext.liveStatus,
        files: replyContext.files,
        findings: replyContext.findings,
        outputs: replyContext.outputs,
      });

  const jobSummary = replyContext.notFound
    ? t("errors.projectNotFound")
    : t("mainAgent.jobSummary", {
        status: replyContext.jobStatus,
        progress: replyContext.progress,
      });

  const suggestions = useMemo(
    () => [
      { label: t("mainAgent.suggestions.status"), prompt: t("mainAgent.prompts.status") },
      { label: t("mainAgent.suggestions.materials"), prompt: t("mainAgent.prompts.materials") },
      { label: t("mainAgent.suggestions.deliver"), prompt: t("mainAgent.prompts.deliver") },
    ],
    [t]
  );

  async function sendMessage(text: string) {
    const value = text.trim();
    if (!value || chatBusy) return;
    const history = messages.map((message) => ({
      role: message.role,
      content: message.text,
    }));
    const userMessage: AgentMessage = { id: uid("user"), role: "user", text: value };
    setMessages((prev) => [...prev, userMessage]);
    setDraft("");
    setChatBusy(true);
    try {
      const remote = await agentChat({
        message: value,
        project_id: projectId,
        meeting_id: meetingId,
        history,
      });
      setMessages((prev) => [
        ...prev,
        {
          id: uid("agent"),
          role: "agent",
          text: remote.reply,
          actions: normalizeRemoteActions(remote.actions),
          mode: remote.mode === "llm" ? "live" : "fallback",
        },
      ]);
    } catch {
      const reply = buildTransportFailureReply(replyContext, t);
      setMessages((prev) => [
        ...prev,
        { id: uid("agent"), role: "agent", text: reply.text, actions: reply.actions, mode: reply.mode },
      ]);
    } finally {
      setChatBusy(false);
    }
  }

  async function approveAction(action: AgentAction) {
    if (!action.proposalId || approvingId) return;

    let comment: string | undefined;
    if (action.id === "reject") {
      const reason = window.prompt(t("mainAgent.rejectReasonPrompt"));
      if (!reason?.trim()) return;
      comment = reason.trim();
    } else if (!window.confirm(t("mainAgent.approvalConfirm"))) {
      return;
    }

    setApprovingId(action.proposalId);
    try {
      const result = await approveAgentAction(action.proposalId, comment);
      const resultText = result.message || t("mainAgent.approvalDone", { status: result.status });
      setMessages((prev) => [
        ...prev.map((message) => ({
          ...message,
          actions: message.actions?.map((item) =>
            item.proposalId === action.proposalId
              ? { ...item, requiresApproval: false, proposalId: null, description: resultText }
              : item
          ),
        })),
        { id: uid("agent"), role: "agent", text: resultText },
      ]);
    } catch {
      setMessages((prev) => [
        ...prev,
        { id: uid("agent"), role: "agent", text: t("mainAgent.approvalFailed") },
      ]);
    } finally {
      setApprovingId(null);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    sendMessage(draft);
  }

  return (
    <section
      id="main-agent-panel"
      className="main-agent-panel"
      aria-label={t("mainAgent.title")}
      data-pathname={pathname}
    >
      <header className="main-agent-panel__head">
        <div>
          <p className="main-agent-panel__eyebrow">{t("mainAgent.subtitle")}</p>
          <h2>
            <span className={`main-agent-panel__dot${liveCtx?.offline ? " is-offline" : ""}`} aria-hidden="true" />
            {t("mainAgent.title")}
          </h2>
        </div>
      </header>

      <div className="main-agent-context" aria-label={t("mainAgent.context")}>
        <div>
          <span className="main-agent-context__label">{t("mainAgent.context")}</span>
          <strong>{scopeLabel}</strong>
        </div>
        <p>{projectId || meetingId ? liveSummary : t("mainAgent.emptyScope")}</p>
        {projectId && meetingId && <p>{jobSummary}</p>}
      </div>

      <div ref={scrollRef} className="main-agent-messages" role="log" aria-live="polite">
        {messages.map((message) => (
          <article key={message.id} className={`main-agent-message main-agent-message--${message.role}`}>
            <p>
              {message.text}
              {message.role === "agent" && message.mode && (
                <span className="main-agent-message__mode">{messageModeLabel(message.mode, t)}</span>
              )}
            </p>
            {!!message.actions?.length && (
              <div className="main-agent-actions">
                {message.actions.map((action) => {
                  const href = hrefForAction(action, projectId, meetingId);
                  const className = `main-agent-action${action.tone === "warning" ? " main-agent-action--warning" : ""}`;
                  const title = actionLabel(action, t);
                  const description = actionDescription(action, t);
                  const needsApproval = action.requiresApproval && action.proposalId;
                  const content = (
                    <>
                      <strong>
                        {title}
                        {action.requiresApproval && (
                          <span className="main-agent-action__approval">{t("mainAgent.requiresApproval")}</span>
                        )}
                      </strong>
                      <span>{description}</span>
                    </>
                  );

                  if (needsApproval) {
                    return (
                      <div
                        key={`${message.id}-${action.id}-${action.proposalId}`}
                        className={className}
                        data-agent-action-card
                        data-agent-proposal-id={action.proposalId}
                      >
                        {content}
                        <div className="main-agent-action__controls">
                          <Link href={href} className="main-agent-action__link">
                            {t("mainAgent.openActionPage")}
                          </Link>
                          <button
                            type="button"
                            className="main-agent-action__button"
                            onClick={() => void approveAction(action)}
                            disabled={approvingId === action.proposalId}
                          >
                            {approvingId === action.proposalId ? t("mainAgent.approving") : t("mainAgent.approveAction")}
                          </button>
                        </div>
                      </div>
                    );
                  }

                  return (
                    <Link
                      key={`${message.id}-${action.id}`}
                      href={href}
                      className={className}
                      data-agent-action-card
                    >
                      {content}
                    </Link>
                  );
                })}
              </div>
            )}
          </article>
        ))}
      </div>

      <div className="main-agent-suggestions" aria-label={t("mainAgent.suggestionsLabel")}>
        {suggestions.map((item) => (
          <button key={item.label} type="button" onClick={() => void sendMessage(item.prompt)} disabled={chatBusy}>
            {item.label}
          </button>
        ))}
      </div>

      <form className="main-agent-composer" onSubmit={onSubmit}>
        <textarea
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          className="main-agent-input"
          rows={3}
          placeholder={t("mainAgent.inputPlaceholder")}
          disabled={chatBusy}
        />
        <button type="submit" className="main-agent-send" disabled={!draft.trim() || chatBusy}>
          {chatBusy ? t("common.processing") : t("mainAgent.send")}
        </button>
      </form>
    </section>
  );
}
