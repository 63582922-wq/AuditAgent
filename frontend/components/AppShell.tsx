"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ReactNode } from "react";
import { ProjectRail } from "@/components/ProjectRail";

const MAIN_NAV = [
  { href: "/", label: "总览", exact: true },
  { href: "/projects", label: "项目", prefix: "/projects" },
  { href: "/settings/rules", label: "规则库", prefix: "/settings/rules" },
  { href: "/settings/memory", label: "记忆", prefix: "/settings/memory" },
];

function projectIdFrom(path: string): string | null {
  const m = path.match(/^\/projects\/([^/]+)/);
  if (!m || m[1] === "new") return null;
  return m[1];
}

export function AppShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const projectId = projectIdFrom(pathname);

  return (
    <div className="shell">
      <aside className="shell-side">
        <Link href="/" className="shell-brand">
          <span className="shell-brand__mark">FX</span>
          <span className="shell-brand__text">FXPG SYS</span>
        </Link>

        <nav className="shell-nav">
          {MAIN_NAV.map((item) => {
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

        {projectId && <ProjectRail projectId={projectId} />}
      </aside>

      <div className="shell-main">
        <div className="shell-content">{children}</div>
      </div>
    </div>
  );
}
