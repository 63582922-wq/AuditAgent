"use client";

import { ButtonHTMLAttributes, ReactNode, useState } from "react";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  loading?: boolean;
  loadingLabel?: string;
  variant?: "primary" | "outline" | "ghost";
  children: ReactNode;
};

export function ActionButton({
  loading,
  loadingLabel = "处理中…",
  variant = "primary",
  className = "",
  disabled,
  onClick,
  children,
  ...rest
}: Props) {
  const [pending, setPending] = useState(false);
  const busy = loading || pending;
  const cls =
    variant === "outline" ? "btn-outline" : variant === "ghost" ? "btn-ghost" : "btn";

  async function handleClick(e: React.MouseEvent<HTMLButtonElement>) {
    if (busy || !onClick) return;
    setPending(true);
    try {
      await onClick(e);
    } finally {
      setPending(false);
    }
  }

  return (
    <button
      type="button"
      {...rest}
      className={`${cls}${busy ? " is-busy" : ""} ${className}`.trim()}
      disabled={disabled || busy}
      onClick={handleClick}
    >
      {busy ? loadingLabel : children}
    </button>
  );
}
