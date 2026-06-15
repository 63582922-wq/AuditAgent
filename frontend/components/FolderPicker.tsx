"use client";

import { useCallback, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";

type Props = {
  onSelect: (files: File[]) => void;
  disabled?: boolean;
  selectedFiles?: File[];
};

function folderLabel(files: File[]): string {
  if (!files.length) return "";
  const first = files[0] as File & { webkitRelativePath?: string };
  const rel = first.webkitRelativePath || first.name;
  const root = rel.split("/")[0] || rel;
  return root;
}

export function FolderPicker({ onSelect, disabled, selectedFiles = [] }: Props) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  const apply = useCallback(
    (list: FileList | File[] | null) => {
      if (disabled || !list?.length) return;
      const files = Array.from(list).filter((f) => !f.name.startsWith("."));
      if (!files.length) return;
      onSelect(files);
    },
    [disabled, onSelect]
  );

  const label = selectedFiles.length ? folderLabel(selectedFiles) : "";

  return (
    <div
      className={`upload-zone folder-picker${drag ? " upload-zone--drag" : ""}${selectedFiles.length ? " upload-zone--ready" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        if (disabled) return;
        apply(e.dataTransfer.files);
      }}
      onClick={() => !disabled && inputRef.current?.click()}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (disabled) return;
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
    >
      <div className="upload-zone__core">
        <span className="upload-zone__hex" aria-hidden>
          <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
            <path
              d="M4 7h4l1.5-2h6.5v9H4V7z"
              stroke="currentColor"
              strokeWidth="1.3"
              strokeLinejoin="round"
            />
            <path d="M4 7h12" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" />
          </svg>
        </span>
        <p className="upload-zone__title">
          {selectedFiles.length
            ? t("components.folderPicker.selected", { name: label, count: selectedFiles.length })
            : t("components.folderPicker.pick")}
        </p>
        <p className="upload-zone__hint">{t("components.folderPicker.hint")}</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        hidden
        disabled={disabled}
        {...({ webkitdirectory: "", directory: "" } as React.InputHTMLAttributes<HTMLInputElement>)}
        onChange={(e) => {
          apply(e.target.files);
          e.target.value = "";
        }}
      />
    </div>
  );
}
