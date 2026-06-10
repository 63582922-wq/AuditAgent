import { HudSkeleton, PageSkeleton } from "@/components/PageSkeleton";

export default function ProjectLoading() {
  return (
    <>
      <HudSkeleton />
      <PageSkeleton lines={4} />
    </>
  );
}
