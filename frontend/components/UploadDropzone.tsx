"use client";

import { useCallback, useRef, useState } from "react";

type Props = {
  onSelect: (files: FileList) => void;
  disabled?: boolean;
  selectedCount?: number;
};

export function UploadDropzone({ onSelect, disabled, selectedCount = 0 }: Props) {
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
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          inputRef.current?.click();
        }
      }}
    >
      <div className="upload-zone__grid" aria-hidden />
      <div className="upload-zone__core">
        <span className="upload-zone__hex">↑</span>
        <p className="upload-zone__title">
          {selectedCount > 0 ? `已选择 ${selectedCount} 个文件` : "拖入资料或点击选择"}
        </p>
        <p className="upload-zone__hint">xlsx · csv · docx · pdf · jpg · png · 可多选</p>
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
