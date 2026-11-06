import { useCallback, useRef, useState } from "react";
import { api } from "../services/api";
import { useStore } from "../store";
import { Spinner } from "./ui";

export function FileUpload({ compact = false }: { compact?: boolean }) {
  const addFile = useStore((s) => s.addFile);
  const [drag, setDrag] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleFiles = useCallback(
    async (files: FileList | null) => {
      if (!files || !files.length) return;
      setBusy(true);
      setError(null);
      try {
        for (const f of Array.from(files)) {
          const info = await api.upload(f);
          addFile(info);
        }
      } catch (e: any) {
        setError(e.message || "Upload failed");
      } finally {
        setBusy(false);
      }
    },
    [addFile],
  );

  return (
    <div
      onDragOver={(e) => {
        e.preventDefault();
        setDrag(true);
      }}
      onDragLeave={() => setDrag(false)}
      onDrop={(e) => {
        e.preventDefault();
        setDrag(false);
        handleFiles(e.dataTransfer.files);
      }}
      onClick={() => inputRef.current?.click()}
      className={`cursor-pointer rounded-lg border-2 border-dashed transition-colors text-center
        ${drag ? "border-accent bg-accent/5" : "border-edge hover:border-accent-dim"}
        ${compact ? "p-4" : "p-10"}`}
    >
      <input
        ref={inputRef}
        type="file"
        multiple
        className="hidden"
        onChange={(e) => handleFiles(e.target.files)}
      />
      {busy ? (
        <Spinner label="Uploading…" />
      ) : (
        <div>
          <div className={compact ? "text-sm" : "text-lg"}>
            {drag ? "Drop to upload" : "Drag & drop a file, or click to browse"}
          </div>
          {!compact && (
            <div className="text-xs text-gray-500 mt-2">
              Images · Audio (WAV/FLAC/MP3/OGG/AIFF) · Video (MP4/MKV/AVI/MOV) · archives · any blob
            </div>
          )}
        </div>
      )}
      {error && <div className="text-bad text-xs mt-2">{error}</div>}
    </div>
  );
}
