"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode, useMemo } from "react";
import { PreferencesBar } from "@/components/PreferencesBar";
import { ProjectLiveProvider } from "@/contexts/ProjectLiveContext";
import { MainAgentDrawer } from "@/components/MainAgentDrawer";
import { ProjectRail } from "@/components/ProjectRail";
import { useI18n } from "@/lib/i18n";

function projectIdFrom(path: string): string | null {
  const m = path.match(/^\/projects\/([^/]+)/);
  if (!m || m[1] === "new") return null;
  return m[1];
}

function meetingIdFrom(path: string): string | null {
  const m = path.match(/^\/projects\/[^/]+\/meetings\/([^/]+)/);
  return m ? m[1] : null;
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const projectId = projectIdFrom(pathname);
  const meetingId = meetingIdFrom(pathname);
  const { t } = useI18n();

  const mainNav = useMemo(
    () => [
      { href: "/", label: t("nav.overview"), exact: true },
      { href: "/projects", label: t("nav.projects"), prefix: "/projects" },
      { href: "/settings/rules", label: t("nav.rules"), prefix: "/settings/rules" },
      { href: "/settings/memory", label: t("nav.memory"), prefix: "/settings/memory" },
    ],
    [t]
  );

  const shell = (
    <div className="shell">
      <aside className="shell-side">
        <Link href="/" className="shell-brand">
          <span className="shell-brand__text">
            <span className="shell-brand__name">{t("product.name")}</span>
            <span className="shell-brand__sub">{t("product.subtitle")}</span>
          </span>
        </Link>

        <PreferencesBar placement="side" />

        <nav className="shell-nav">
          {mainNav.map((item) => {
            const active = item.exact
              ? pathname === item.href
              : item.prefix
                ? pathname === item.href || pathname.startsWith(item.prefix + "/") || pathname.startsWith(item.prefix)
                : pathname.startsWith(item.href);
            return (
              <Link key={item.href} href={item.href} className={`shell-nav__item${active ? " is-active" : ""}`}>
                {item.label}
              </Link>
            );
          })}
        </nav>

        {projectId && meetingId && <ProjectRail projectId={projectId} />}
      </aside>

      <div className="shell-main">
        <div className="shell-content">{children}</div>
      </div>
      <aside className="shell-agent" aria-label={t("mainAgent.title")}>
        <MainAgentDrawer projectId={projectId} meetingId={meetingId} pathname={pathname} />
      </aside>
    </div>
  );

  if (projectId && meetingId) {
    return (
      <ProjectLiveProvider
        projectId={projectId}
        meetingId={meetingId}
        includeLogs
        includeAgent
      >
        {shell}
      </ProjectLiveProvider>
    );
  }
  return shell;
}
