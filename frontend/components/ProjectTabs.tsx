"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const TABS = [
  { suffix: "", label: "概览" },
  { suffix: "/files", label: "文件资料" },
  { suffix: "/risks", label: "风险清单" },
  { suffix: "/review", label: "人工复核" },
  { suffix: "/outputs", label: "交付物" },
  { suffix: "/logs", label: "审计日志" },
];

export function ProjectTabs({ projectId }: { projectId: string }) {
  const pathname = usePathname();
  const base = `/projects/${projectId}`;

  return (
    <div className="tabs">
      {TABS.map((tab) => {
        const href = `${base}${tab.suffix}`;
        const active =
          tab.suffix === ""
            ? pathname === base
            : pathname === href || pathname.startsWith(`${href}/`);
        return (
          <Link key={tab.suffix} href={href} className={`tab${active ? " active" : ""}`}>
            {tab.label}
          </Link>
        );
      })}
    </div>
  );
}
