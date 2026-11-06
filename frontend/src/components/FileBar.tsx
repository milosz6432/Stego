import { useStore } from "../store";
import { humanSize, Badge } from "./ui";
import { FileUpload } from "./FileUpload";

const MEDIA_TONE: Record<string, "good" | "warn" | "bad" | "default"> = {
  image: "good",
  audio: "warn",
  video: "bad",
};

export function FileBar() {
  const { files, currentId, setCurrent, removeFile, current } = useStore();
  const cur = current();

  return (
    <div className="card p-3 mb-4">
      <div className="flex items-center justify-between mb-2">
        <span className="label">Active file</span>
        <span className="text-xs text-gray-500">{files.length} loaded</span>
      </div>
      <div className="flex gap-2 flex-wrap mb-2">
        {files.map((f) => (
          <button
            key={f.id}
            onClick={() => setCurrent(f.id)}
            className={`chip ${f.id === currentId ? "border-accent text-white" : ""}`}
            title={`${f.name} · ${f.format} · ${humanSize(f.size)}`}
          >
            <span className="max-w-[12rem] truncate">{f.name}</span>
            {f.origin !== "upload" && <span className="text-accent-dim">[{f.origin}]</span>}
            <span
              className="text-gray-500 hover:text-bad ml-1"
              onClick={(e) => {
                e.stopPropagation();
                removeFile(f.id);
              }}
            >
              ✕
            </span>
          </button>
        ))}
      </div>
      {cur && (
        <div className="flex items-center gap-2 flex-wrap text-xs border-t border-edge pt-2">
          <Badge tone={MEDIA_TONE[cur.media_type] || "default"}>{cur.media_type}</Badge>
          <Badge>{cur.format}</Badge>
          <span className="text-gray-400">{humanSize(cur.size)}</span>
          <span className="text-gray-500">{cur.detection.description}</span>
          <span className="mono text-gray-600 truncate max-w-[16rem]" title={cur.sha256}>
            sha256:{cur.sha256.slice(0, 16)}…
          </span>
          <a className="btn btn-xs ml-auto" href={`/api/files/${cur.id}/download`} target="_blank" rel="noreferrer">
            Download
          </a>
        </div>
      )}
      <div className="mt-2">
        <FileUpload compact />
      </div>
    </div>
  );
}
