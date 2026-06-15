"use client";

import { useAppPreferences } from "@/lib/i18n";

type Props = {
  /** 侧栏顶部（logo 下）或移动端顶栏 */
  placement?: "side" | "mobile";
};

export function PreferencesBar({ placement = "side" }: Props) {
  const { locale, theme, setLocale, setTheme, t } = useAppPreferences();

  const nextLocale = locale === "zh" ? "en" : "zh";
  const nextTheme = theme === "dark" ? "light" : "dark";

  return (
    <div className={`prefs-bar prefs-bar--${placement}`}>
      <button
        type="button"
        className="prefs-toggle"
        onClick={() => setLocale(nextLocale)}
        aria-label={t("prefs.toggleLocale")}
        title={t("prefs.toggleLocale")}
      >
        {locale === "zh" ? t("prefs.langZh") : t("prefs.langEn")}
      </button>
      <button
        type="button"
        className="prefs-toggle prefs-toggle--theme"
        onClick={() => setTheme(nextTheme)}
        aria-label={t("prefs.toggleTheme")}
        title={t("prefs.toggleTheme")}
      >
        {theme === "dark" ? t("prefs.themeDark") : t("prefs.themeLight")}
      </button>
    </div>
  );
}
