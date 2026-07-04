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
  const [msg, setMsg] = useState("");
  const [msgKind, setMsgKind] = useState<"danger" | "success">("success");
  const [busy, setBusy] = useState("");

  function load() {
    api<Memory[]>("/memories", { cache: "no-store" })
      .then(setMemories)
      .catch((e) => {
        setMsgKind("danger");
        setMsg(e instanceof Error ? e.message : String(e));
      });
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
    setBusy("add");
    setMsg("");
    try {
      await api("/memories", {
        method: "POST",
        body: JSON.stringify({ memory_type: type, content, tags: [] }),
      });
      setContent("");
      setMsgKind("success");
      setMsg(t("settings.added"));
      load();
    } catch (e) {
      setMsgKind("danger");
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  }

  async function doSearch(e: React.FormEvent) {
    e.preventDefault();
    if (!searchQ.trim()) return;
    setBusy("search");
    setMsg("");
    try {
      setSearchHits(await api<SearchHit[]>(`/memories/search?q=${encodeURIComponent(searchQ.trim())}`, { cache: "no-store" }));
    } catch (err) {
      setMsgKind("danger");
      setMsg(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy("");
    }
  }

  async function reindex() {
    setBusy("reindex");
    setMsg("");
    try {
      await api("/memories/reindex", { method: "POST" });
      setMsgKind("success");
      setMsg(t("settings.reindexed"));
      load();
    } catch (e) {
      setMsgKind("danger");
      setMsg(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
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
            disabled={!!busy}
          />
          <button className="btn-outline" type="submit" disabled={!!busy}>
            {busy === "search" ? t("common.processing") : t("settings.search")}
          </button>
          <button
            className="btn-text"
            type="button"
            onClick={reindex}
            disabled={!!busy}
          >
            {busy === "reindex" ? t("common.processing") : t("settings.reindex")}
          </button>
        </form>
        {msg && <p className={`alert ${msgKind}`}>{msg}</p>}
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
          <select className="input" value={type} onChange={(e) => setType(e.target.value)} disabled={!!busy}>
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
            disabled={!!busy}
          />
          <button type="submit" className="btn" style={{ justifySelf: "start" }} disabled={!!busy}>
            {busy === "add" ? t("common.processing") : t("settings.add")}
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
