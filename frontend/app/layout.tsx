import Script from "next/script";
import { AppShell } from "@/components/AppShell";
import { Providers } from "@/components/Providers";
import "./globals.css";
import "./settling-theme.css";

export const metadata = {
  title: "AuditAgent · 会议合规远程观察",
  description: "罗氏会议合规远程观察 Agent · Finding 自动生成与交付验收",
  icons: { icon: "/favicon.svg" },
};

const THEME_LOCALE_INIT = `
(function () {
  var root = document.documentElement;
  var theme = localStorage.getItem("fxpg-theme");
  if (theme === "light" || theme === "dark") root.setAttribute("data-theme", theme);
  else root.setAttribute("data-theme", "dark");
  var locale = localStorage.getItem("fxpg-locale");
  root.lang = locale === "en" ? "en" : "zh-CN";

  root.removeAttribute("data-immersive-translate-page-theme");
  root.removeAttribute("data-immersive-translate-walked");
  if (root.hasAttribute("data-cursor-ref")) root.removeAttribute("data-cursor-ref");
  var els = document.querySelectorAll("[data-cursor-ref]");
  for (var i = 0; i < els.length; i++) els[i].removeAttribute("data-cursor-ref");
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link
          href="https://fonts.googleapis.com/css2?family=Syne:wght@500;600;700&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body suppressHydrationWarning>
        <Script id="theme-locale-init" strategy="beforeInteractive">
          {THEME_LOCALE_INIT}
        </Script>
        <Providers>
          <AppShell>{children}</AppShell>
        </Providers>
      </body>
    </html>
  );
}
