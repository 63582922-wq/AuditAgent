"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { Project, api } from "@/lib/api";

export default function NewProjectPage() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    try {
      const p = await api<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({ name }),
      });
      router.push(`/projects/${p.id}`);
    } catch (err) {
      alert(String(err));
    } finally {
      setLoading(false);
    }
  }

  return (
    <>
      <PageTop title="新建项目" desc="创建后将进入项目概览，左侧栏显示流程进度。" />

      <Block title="项目名称">
        <form onSubmit={onSubmit} style={{ maxWidth: 420 }}>
          <input
            className="input"
            placeholder="某公司 2025 年度会计风险评估"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <div style={{ marginTop: "1rem" }}>
            <button className="btn" disabled={loading}>
              {loading ? "创建中" : "创建"}
            </button>
          </div>
        </form>
      </Block>
    </>
  );
}
