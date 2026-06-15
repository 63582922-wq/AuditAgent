"use client";

import { useEffect, useState } from "react";

/** 运行中 UI 心跳 tick，驱动 CSS 动画与图谱刷新 */
export function useLiveTick(active: boolean, intervalMs = 600): number {
  const [tick, setTick] = useState(0);

  useEffect(() => {
    if (!active) return;
    setTick((t) => t + 1);
    const id = setInterval(() => setTick((t) => t + 1), intervalMs);
    return () => clearInterval(id);
  }, [active, intervalMs]);

  return tick;
}
