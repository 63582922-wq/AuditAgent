"use client";

import { ButtonHTMLAttributes, ReactNode, useState } from "react";
import { useI18n } from "@/lib/i18n";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  loading?: boolean;
  loadingLabel?: string;
  variant?: "primary" | "outline" | "ghost";
  children: ReactNode;
};

export function ActionButton({
  loading,
  loadingLabel,
  variant = "primary",
  className = "",
  disabled,
  onClick,
  children,
  ...rest
}: Props) {
  const { t } = useI18n();
  const [pending, setPending] = useState(false);
  const busy = loading || pending;
  const cls = "btn-text";

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
      {busy ? loadingLabel ?? t("common.processing") : children}
    </button>
  );
}
