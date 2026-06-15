import { ReactNode } from "react";
import { MeetingWorkShell } from "@/components/MeetingWorkShell";

export default function MeetingLayout({ children }: { children: ReactNode }) {
  return <MeetingWorkShell>{children}</MeetingWorkShell>;
}
