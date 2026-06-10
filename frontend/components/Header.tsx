"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV = [
  { href: "/projects", label: "项目" },
  { href: "/settings/rules", label: "规则库" },
  { href: "/settings/memory", label: "长期记忆" },
];

export function Header() {
  const pathname = usePathname();

  function isActive(href: string) {
    if (href === "/projects") return pathname === "/projects" || pathname.startsWith("/projects/");
    return pathname.startsWith(href);
  }

  return (
    <header className="header">
      <Link href="/" className="logo">
        <span className="logo-mark">AA</span>
        <span>AuditAgent</span>
      </Link>
      <nav>
        {NAV.map((item) => (
          <Link
            key={item.href}
            href={item.href}
            className={`nav-link${isActive(item.href) ? " active" : ""}`}
          >
            {item.label}
          </Link>
        ))}
      </nav>
    </header>
  );
}
