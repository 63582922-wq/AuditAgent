"use client";

import { ReactNode } from "react";
import { AppPreferencesProvider } from "@/lib/i18n";

export function Providers({ children }: { children: ReactNode }) {
  return <AppPreferencesProvider>{children}</AppPreferencesProvider>;
}
