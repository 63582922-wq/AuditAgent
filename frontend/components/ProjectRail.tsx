"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProjectLiveOptional } from "@/contexts/ProjectLiveContext";
import { useI18n } from "@/lib/i18n";
import { buildWorkflowSteps, statusLabel } from "@/lib/i18n/workflow-steps";
import { resolveMissionPhase } from "@/lib/mission";
import { isPipelineRunning, resolveLiveProgress } from "@/lib/workflow";

export function ProjectRail({ projectId }: { projectId: string }) {
  const pathname = usePathname();
  const { t, messages } = useI18n();
  const base = `/projects/${projectId}`;
  const meetingMatch = pathname.match(/^\/projects\/[^/]+\/meetings\/([^/]+)/);
  const meetingId = meetingMatch?.[1];
  const workBase = meetingId ? `${base}/meetings/${meetingId}` : base;
  const { live, job, notFound } = useProjectLiveOptional() ?? { live: null, job: null, notFound: false };

  const workflowSteps = buildWorkflowSteps(messages);
  const running = isPipelineRunning(live?.status ?? "", job?.status);
  const pct = live ? resolveLiveProgress(live, job, workflowSteps) : 0;
  const missionPhase = live ? resolveMissionPhase(live, job) : "init";
  const missionSteps = [
    { id: "init", num: "01", label: messages.mission.phases.init.short },
    { id: "ingest", num: "02", label: messages.mission.phases.ingest.short },
    { id: "processing", num: "03", label: messages.mission.phases.processing.short },
    { id: "deliver", num: "04", label: messages.mission.phases.deliver.short },
  ] as const;
  const phaseIdx =
    missionPhase === "init"
      ? 0
      : missionPhase === "ingest"
        ? 1
        : missionPhase === "processing"
          ? 2
          : 3;

  const meetingCode =
    (live?.state_json as { meeting_case?: { meeting_code?: string } } | undefined)?.meeting_case?.meeting_code ||
    live?.name ||
    meetingId;
  const statusText = live ? statusLabel(live.status, messages) : t("rail.pending");

  const pages = [
    { suffix: "", label: t("rail.overview") },
    { suffix: "/files", label: t("rail.files") },
    { suffix: "/risks", label: t("rail.findings") },
    { suffix: "/outputs", label: t("rail.outputs") },
    { suffix: "/logs", label: t("rail.logs") },
    { suffix: "/review", label: t("rail.review") },
  ];

  return (
    <div className="rail">
      {meetingId && notFound && (
        <section className="rail-context rail-context--danger" aria-label={t("rail.contextLabel")}>
          <span className="rail-context__label">{t("errors.notFound")}</span>
          <strong className="rail-context__code">{t("errors.meetingNotFound")}</strong>
          <p>{t("errors.projectNotFound")}</p>
          <Link href="/projects" className="rail-pages__link is-active">
            {t("nav.backProjects")}
          </Link>
        </section>
      )}
      {meetingId && notFound ? null : (
        <>
      {meetingId ? (
        <section className="rail-context" aria-label={t("rail.contextLabel")}>
          <span className="rail-context__label">{t("rail.meetingScope")}</span>
          <strong className="rail-context__code" title={meetingCode || undefined}>
            {meetingCode || t("rail.pending")}
          </strong>
          <p>
            {statusText} · {live?.file_count ?? 0} {t("meetingOverview.filesUnit")} ·{" "}
            {messages.domain.finding} {live?.risk_count ?? 0} · {t("meetingOverview.outputs")}{" "}
            {live?.output_count ?? 0}
          </p>
        </section>
      ) : (
        <section className="rail-context" aria-label={t("rail.contextLabel")}>
          <span className="rail-context__label">{t("rail.projectScope")}</span>
          <strong className="rail-context__code">{t("nav.meetingList")}</strong>
        </section>
      )}

      {meetingId && (
        <>
          <ol className="rail-steps" aria-label={t("rail.workflow")}>
            {missionSteps.map((step, i) => {
              const state =
                missionPhase === "failed"
                  ? i <= phaseIdx
                    ? i === phaseIdx
                      ? "is-live"
                      : "is-done"
                    : ""
                  : i < phaseIdx
                    ? "is-done"
                    : i === phaseIdx
                      ? "is-live"
                      : "";
              const suffix =
                step.id === "ingest" && (live?.file_count ?? 0) > 0
                  ? ` · ${live?.file_count} ${t("meetingOverview.filesUnit")}`
                  : step.id === "processing" && running
                    ? ` · ${pct}%`
                    : "";
              return (
                <li key={step.id} className={state || undefined}>
                  <div className="rail-steps__item">
                    <span>{step.num}</span>
                    <span className="rail-steps__text">
                      {step.label}
                      {suffix}
                    </span>
                  </div>
                </li>
              );
            })}
          </ol>
        </>
      )}

      {meetingId ? (
        <nav className="rail-pages" aria-label={t("rail.meetingNav")}>
          {pages.map((p) => {
            const href = `${workBase}${p.suffix}`;
            const active =
              p.suffix === ""
                ? pathname === workBase
                : pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link key={p.suffix} href={href} className={`rail-pages__link${active ? " is-active" : ""}`}>
                {p.label}
              </Link>
            );
          })}
        </nav>
      ) : (
        <div className="rail-project-actions">
          <Link href={base} className={`rail-pages__link${pathname === base ? " is-active" : ""}`}>
            {t("nav.meetingList")}
          </Link>
        </div>
      )}
        </>
      )}
    </div>
  );
}
