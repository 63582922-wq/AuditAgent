"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState, ReactNode } from "react";
import { en } from "./en";
import { zh, type Locale, type Messages } from "./zh";

const LOCALE_KEY = "fxpg-locale";
const THEME_KEY = "fxpg-theme";

export type Theme = "dark" | "light";

type Ctx = {
  locale: Locale;
  theme: Theme;
  messages: Messages;
  setLocale: (l: Locale) => void;
  setTheme: (t: Theme) => void;
  t: (key: string, vars?: Record<string, string | number>) => string;
};

const AppPreferencesContext = createContext<Ctx | null>(null);

const catalogs: Record<Locale, Messages> = { zh, en };

function resolve(obj: Record<string, unknown>, path: string): unknown {
  return path.split(".").reduce<unknown>((acc, part) => {
    if (acc && typeof acc === "object" && part in (acc as Record<string, unknown>)) {
      return (acc as Record<string, unknown>)[part];
    }
    return undefined;
  }, obj);
}

function interpolate(text: string, vars?: Record<string, string | number>): string {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (_, k) => String(vars[k] ?? `{${k}}`));
}

export function AppPreferencesProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>("zh");
  const [theme, setThemeState] = useState<Theme>("dark");

  useEffect(() => {
    const storedLocale = localStorage.getItem(LOCALE_KEY) as Locale | null;
    const storedTheme = localStorage.getItem(THEME_KEY) as Theme | null;
    if (storedLocale === "zh" || storedLocale === "en") setLocaleState(storedLocale);
    if (storedTheme === "light" || storedTheme === "dark") setThemeState(storedTheme);
  }, []);

  useEffect(() => {
    document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
    document.documentElement.setAttribute("data-theme", theme);
    localStorage.setItem(LOCALE_KEY, locale);
    localStorage.setItem(THEME_KEY, theme);
  }, [locale, theme]);

  const messages = catalogs[locale];

  const t = useCallback(
    (key: string, vars?: Record<string, string | number>) => {
      const val = resolve(messages as unknown as Record<string, unknown>, key);
      if (typeof val === "string") return interpolate(val, vars);
      return key;
    },
    [messages]
  );

  const setLocale = useCallback((l: Locale) => setLocaleState(l), []);
  const setTheme = useCallback((th: Theme) => setThemeState(th), []);

  const value = useMemo(
    () => ({ locale, theme, messages, setLocale, setTheme, t }),
    [locale, theme, messages, setLocale, setTheme, t]
  );

  return <AppPreferencesContext.Provider value={value}>{children}</AppPreferencesContext.Provider>;
}

export function useAppPreferences() {
  const ctx = useContext(AppPreferencesContext);
  if (!ctx) throw new Error("useAppPreferences must be used within AppPreferencesProvider");
  return ctx;
}

export function useI18n() {
  const { t, locale, messages } = useAppPreferences();
  return { t, locale, messages };
}

export type { Locale, Messages };
