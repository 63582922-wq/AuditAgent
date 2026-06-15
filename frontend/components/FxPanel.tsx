"use client";

import { ReactNode } from "react";

type Props = {
  children: ReactNode;
  className?: string;
  glow?: boolean;
};

export function FxPanel({ children, className = "", glow }: Props) {
  return (
    <section className={`fx-panel${glow ? " fx-panel--glow" : ""}${className ? ` ${className}` : ""}`}>
      <div className="fx-panel__inner">{children}</div>
    </section>
  );
}
