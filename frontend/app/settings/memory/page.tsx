"use client";

import { useEffect, useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { Memory, api } from "@/lib/api";

type SearchHit = { id: string; memory_type: string; content: string; tags: string[] };

export default function MemoryPage() {
  const [memories, setMemories] = useState<Memory[]>([]);
  const [content, setContent] = useState("");
  const [type, setType] = useState("user_preference");
  const [searchQ, setSearchQ] = useState("");
  const [searchHits, setSearchHits] = useState<SearchHit[]>([]);

  function load() {
    api<Memory[]>("/memories").then(setMemories).catch(console.error);
  }

  useEffect(() => {
    load();
  }, []);

  async function addMemory(e: React.FormEvent) {
    e.preventDefault();
    await api("/memories", {
      method: "POST",
      body: JSON.stringify({ memory_type: type, content, tags: [] }),
    });
    setContent("");
    load();
  }

  async function doSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchQ.trim()) return;
    setSearchHits(await api<SearchHit[]>(`/memories/search?q=${encodeURIComponent(searchQ.trim())}`));
  }

  return (
    <>
      <PageTop title="长期记忆" desc="向量 + 标签混合检索" />

      <Block title="检索">
        <form onSubmit={doSearch} style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <input className="input" style={{ flex: 1, minWidth: 200 }} placeholder="语义搜索…" value={searchQ} onChange={(e) => setSearchQ(e.target.value)} />
          <button className="btn-outline" type="submit">
            搜索
          </button>
          <button
            className="btn-text"
            type="button"
            onClick={async () => {
              await api("/memories/reindex", { method: "POST" });
              load();
            }}
          >
            重建索引
          </button>
        </form>
        {searchHits.length > 0 && (
          <ul style={{ margin: "1rem 0 0", padding: 0, listStyle: "none", fontSize: "0.8125rem" }}>
            {searchHits.map((h) => (
              <li key={h.id} style={{ padding: "0.5rem 0", borderBottom: "1px solid var(--line)" }}>
                <span className="badge neutral">{h.memory_type}</span> {h.content}
              </li>
            ))}
          </ul>
        )}
      </Block>

      <Block title="写入">
        <form onSubmit={addMemory} style={{ display: "grid", gap: "0.75rem", maxWidth: 480 }}>
          <select className="input" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="user_preference">用户偏好</option>
            <option value="risk_policy">风险口径</option>
            <option value="report_template">报告模板</option>
            <option value="case_example">历史案例</option>
            <option value="accounting_knowledge">专业知识</option>
          </select>
          <textarea className="textarea" value={content} onChange={(e) => setContent(e.target.value)} required />
          <button className="btn" style={{ justifySelf: "start" }}>
            添加
          </button>
        </form>
      </Block>

      <Block title={`全部 · ${memories.length}`}>
        {memories.map((m) => (
          <div key={m.id} style={{ padding: "0.65rem 0", borderBottom: "1px solid var(--line)", fontSize: "0.8125rem" }}>
            <span className="badge neutral">{m.memory_type}</span>
            <p style={{ margin: "0.35rem 0 0", color: "var(--text-2)" }}>{m.content}</p>
          </div>
        ))}
      </Block>
    </>
  );
}
