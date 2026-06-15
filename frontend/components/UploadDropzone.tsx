"use client";

import { useCallback, useRef, useState } from "react";
import { useI18n } from "@/lib/i18n";

type Props = {
  onSelect: (files: FileList) => void;
  disabled?: boolean;
  selectedCount?: number;
};

export function UploadDropzone({ onSelect, disabled, selectedCount = 0 }: Props) {
  const { t } = useI18n();
  const inputRef = useRef<HTMLInputElement>(null);
  const [drag, setDrag] = useState(false);

  const pick = useCallback(
    (list: FileList | null) => {
      if (!list?.length || disabled) return;
      onSelect(list);
    },
    [disabled, onSelect]
  );

  return (
    <div
      className={`upload-zone${drag ? " upload-zone--drag" : ""}${selectedCount > 0 ? " upload-zone--ready" : ""}`}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        pick(e.dataTransfer.files);
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
              d="M10 4v8M6 8l4 4 4-4"
              stroke="currentColor"
              strokeWidth="1.4"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
        </span>
        <p className="upload-zone__title">
          {selectedCount > 0
            ? t("components.uploadDropzone.selected", { count: selectedCount })
            : t("components.uploadDropzone.pick")}
        </p>
        <p className="upload-zone__hint">{t("components.uploadDropzone.hint")}</p>
      </div>
      <input
        ref={inputRef}
        type="file"
        multiple
        hidden
        disabled={disabled}
        onChange={(e) => pick(e.target.files)}
      />
    </div>
  );
}
