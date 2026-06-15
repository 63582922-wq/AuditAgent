"use client";

import { useRouter } from "next/navigation";
import Link from "next/link";
import { useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { Project, api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

export default function NewProjectPage() {
  const router = useRouter();
  const { t } = useI18n();
  const [name, setName] = useState("");
  const [phase, setPhase] = useState<"idle" | "creating" | "entering">("idle");
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError(t("newProject.nameRequired"));
      return;
    }
    if (phase !== "idle") return;

    setError("");
    setPhase("creating");
    try {
      const p = await api<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({ name: trimmed }),
      });
      setPhase("entering");
      router.push(`/projects/${p.id}`);
    } catch (err) {
      setPhase("idle");
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg.includes("Failed to fetch") ? t("newProject.offline") : msg);
    }
  }

  const busy = phase !== "idle";
  const submitLabel =
    phase === "creating"
      ? t("newProject.creating")
      : phase === "entering"
        ? t("newProject.enteringManual")
        : t("newProject.manualSubmit");

  return (
    <>
      <PageTop
        title={t("newProject.title")}
        desc={t("newProject.desc")}
        action={
          <Link href="/projects" className="btn btn-outline">
            {t("nav.backProjects")}
          </Link>
        }
      />

      <Block title={t("newProject.manualTitle")} hint={t("newProject.manualHint")}>
        <form onSubmit={onSubmit} style={{ maxWidth: 420 }} noValidate>
          <input
            className="input"
            placeholder={t("newProject.manualPlaceholder")}
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (error) setError("");
            }}
            disabled={busy}
            autoFocus
          />
          {error && (
            <p className="alert danger" style={{ marginTop: "0.75rem" }}>
              {error}
            </p>
          )}
          <div style={{ marginTop: "1rem" }}>
            <button type="submit" className={`btn${busy ? " is-busy" : ""}`} disabled={busy}>
              {submitLabel}
            </button>
          </div>
        </form>
      </Block>
    </>
  );
}
