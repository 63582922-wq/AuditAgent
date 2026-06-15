import { ReactNode } from "react";

/** 项目层 layout：子会议列表，不展示运行 HUD */
export default function ProjectLayout({ children }: { children: ReactNode }) {
  return <>{children}</>;
}
