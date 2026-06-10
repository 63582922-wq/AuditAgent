"use client";

import { useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { Project, api } from "@/lib/api";

export default function NewProjectPage() {
  const [name, setName] = useState("");
  const [phase, setPhase] = useState<"idle" | "creating" | "entering">("idle");
  const [error, setError] = useState("");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const trimmed = name.trim();
    if (!trimmed) {
      setError("请输入项目名称");
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
      // 硬跳转：dev 下 client router 编译 /files 路由常卡住，router.push 会无声失败
      window.location.assign(`/projects/${p.id}/files`);
    } catch (err) {
      setPhase("idle");
      const msg = err instanceof Error ? err.message : String(err);
      setError(msg.includes("Failed to fetch") ? "无法连接后端，请确认 8000 端口已启动" : msg);
    }
  }

  const busy = phase !== "idle";
  const btnLabel = phase === "creating" ? "创建中…" : phase === "entering" ? "正在进入…" : "创建项目";

  return (
    <>
      <PageTop title="新建项目" desc="输入名称后创建 · 自动进入资料上传页" />

      <Block title="项目名称">
        <form onSubmit={onSubmit} style={{ maxWidth: 420 }} noValidate>
          <input
            className="input"
            placeholder="某公司 2025 年度会计风险评估"
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              if (error) setError("");
            }}
            disabled={busy}
            autoFocus
            aria-invalid={!!error}
            aria-describedby={error ? "project-name-error" : undefined}
          />
          {error && (
            <p id="project-name-error" className="alert danger" style={{ marginTop: "0.75rem" }}>
              {error}
            </p>
          )}
          {phase === "entering" && !error && (
            <p className="alert success" style={{ marginTop: "0.75rem" }}>
              项目已创建 · 正在打开资料页（首次可能需等待编译）…
            </p>
          )}
          <div style={{ marginTop: "1rem" }}>
            <button type="submit" className={`btn${busy ? " is-busy" : ""}`} disabled={busy}>
              {btnLabel}
            </button>
          </div>
          {!name.trim() && phase === "idle" && (
            <p className="muted" style={{ marginTop: "0.75rem", fontSize: "0.8125rem" }}>
              请先输入项目名称
            </p>
          )}
        </form>
      </Block>
    </>
  );
}
