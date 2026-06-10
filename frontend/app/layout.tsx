import Script from "next/script";
import { AppShell } from "@/components/AppShell";
import "./globals.css";

export const metadata = {
  title: "AuditAgent · 会计风险评估",
  description: "智能体会计风险评估与交付物生成",
  icons: { icon: "/favicon.svg" },
};

/** 浏览器翻译类扩展会在 <html> 上注入属性，导致 hydration 警告 */
const STRIP_EXTENSION_ATTRS = `
(function () {
  var root = document.documentElement;
  var blocked = ["data-immersive-translate-page-theme", "data-immersive-translate-walked"];
  function strip() {
    for (var i = 0; i < blocked.length; i++) root.removeAttribute(blocked[i]);
  }
  strip();
  var obs = new MutationObserver(strip);
  obs.observe(root, { attributes: true, attributeFilter: blocked });
  window.addEventListener("DOMContentLoaded", function () { obs.disconnect(); strip(); });
})();
`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <body suppressHydrationWarning>
        <Script id="strip-extension-attrs" strategy="beforeInteractive">
          {STRIP_EXTENSION_ATTRS}
        </Script>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
