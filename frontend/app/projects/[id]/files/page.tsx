import { LegacyMeetingRedirect } from "@/components/LegacyMeetingRedirect";

/** 旧路径重定向到首个子会议资料页 */
export default function LegacyFilesRedirect() {
  return <LegacyMeetingRedirect suffix="/files" />;
}
