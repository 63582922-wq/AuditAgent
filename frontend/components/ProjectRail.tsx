"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProjectLiveOptional } from "@/contexts/ProjectLiveContext";
import { useI18n } from "@/lib/i18n";
import { statusLabel } from "@/lib/i18n/workflow-steps";

export function ProjectRail({ projectId }: { projectId: string }) {
  const pathname = usePathname();
  const { t, messages } = useI18n();
  const base = `/projects/${projectId}`;
  const meetingMatch = pathname.match(/^\/projects\/[^/]+\/meetings\/([^/]+)/);
  const meetingId = meetingMatch?.[1];
  const workBase = meetingId ? `${base}/meetings/${meetingId}` : base;
  const { live, job, notFound } = useProjectLiveOptional() ?? { live: null, job: null, notFound: false };

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
