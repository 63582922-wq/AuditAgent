"use client";

import { useEffect, useState } from "react";
import { Block, PageTop } from "@/components/PageChrome";
import { Memory, api } from "@/lib/api";
import { useI18n } from "@/lib/i18n";

type SearchHit = { id: string; memory_type: string; content: string; tags: string[] };

export default function MemoryPage() {
  const { t } = useI18n();
  const [memories, setMemories] = useState<Memory[]>([]);
  const [content, setContent] = useState("");
  const [type, setType] = useState("user_preference");
  const [searchQ, setSearchQ] = useState("");
  const [searchHits, setSearchHits] = useState<SearchHit[]>([]);
  const [formError, setFormError] = useState("");

  function load() {
    api<Memory[]>("/memories").then(setMemories).catch(console.error);
  }

  useEffect(() => {
    load();
  }, []);

  async function addMemory(e: React.FormEvent) {
    e.preventDefault();
    setFormError("");
    if (!content.trim()) {
      setFormError(t("common.fillRequired"));
      return;
    }
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
      <PageTop title={t("settings.memoryTitle")} desc={t("settings.memoryDesc")} />

      <Block title={t("settings.memorySearch")}>
        <form onSubmit={doSearch} style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap" }}>
          <input
            className="input"
            style={{ flex: 1, minWidth: 200 }}
            placeholder={t("settings.searchPlaceholder")}
            value={searchQ}
            onChange={(e) => setSearchQ(e.target.value)}
          />
          <button className="btn-outline" type="submit">
            {t("settings.search")}
          </button>
          <button
            className="btn-text"
            type="button"
            onClick={async () => {
              await api("/memories/reindex", { method: "POST" });
              load();
            }}
          >
            {t("settings.reindex")}
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

      <Block title={t("settings.memoryWrite")}>
        <form noValidate onSubmit={addMemory} style={{ display: "grid", gap: "0.75rem", maxWidth: 480 }}>
          <select className="input" value={type} onChange={(e) => setType(e.target.value)}>
            <option value="user_preference">{t("settings.memoryTypePreference")}</option>
            <option value="compliance_policy">{t("settings.memoryTypePolicy")}</option>
            <option value="finding_template">{t("settings.memoryTypeFinding")}</option>
            <option value="observation_case">{t("settings.memoryTypeCase")}</option>
            <option value="report_template">{t("settings.memoryTypeReport")}</option>
            <option value="case_example">{t("settings.memoryTypeExample")}</option>
            <option value="accounting_knowledge">{t("settings.memoryTypeKnowledge")}</option>
          </select>
          <textarea
            className="textarea"
            placeholder={t("settings.contentPlaceholder")}
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
          <button type="submit" className="btn" style={{ justifySelf: "start" }}>
            {t("settings.add")}
          </button>
          {formError && <p className="form-hint">{formError}</p>}
        </form>
      </Block>

      <Block title={`${t("settings.memoryAll")} · ${memories.length}`}>
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
