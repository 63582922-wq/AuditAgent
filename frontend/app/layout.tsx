import { AppShell } from "@/components/AppShell";
import "./globals.css";

export const metadata = {
  title: "FXPG · 会计风险评估",
  description: "智能体会计风险评估与交付物生成",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
