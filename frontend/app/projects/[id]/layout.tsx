import { ReactNode } from "react";
import { ProjectWorkflowBar } from "@/components/ProjectWorkflowBar";

export default function ProjectLayout({ children }: { children: ReactNode }) {
  return (
    <>
      <ProjectWorkflowBar />
      {children}
    </>
  );
}
