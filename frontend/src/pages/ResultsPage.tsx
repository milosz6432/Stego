import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../services/api";
import { useStore } from "../store";
import { HexViewer } from "../components/HexViewer";
import { Section, Json, ErrorBox, Spinner, Badge, humanSize } from "../components/ui";
import type { FileInfo } from "../types";

export default function ResultsPage() {
  const { files, refreshFiles, setCurrent } = useStore();
  const navigate = useNavigate();
  const [selected, setSelected] = useState<string | null>(null);

  useEffect(() => {
    refreshFiles();
  }, [refreshFiles]);

  const recovered = files.filter((f) => f.origin !== "upload");
  const uploads = files.filter((f) => f.origin === "upload");
  const sel = files.find((f) => f.id === selected) || recovered[0] || uploads[0];

  const moduleFor = (f: FileInfo) =>
    f.media_type === "image" ? "/image" : f.media_type === "audio" ? "/audio" : f.media_type === "video" ? "/video" : null;

  return (
    <div className="grid lg:grid-cols-[320px,1fr] gap-4">
      <div>
        <Section title={`Recovered payloads (${recovered.length})`}>
          {recovered.length === 0 && <div className="text-gray-500 text-sm">Nothing recovered yet. Run extractions or Smart Scan.</div>}
          <div className="space-y-1">
            {recovered.map((f) => (
              <FileRow key={f.id} f={f} active={sel?.id === f.id} onClick={() => setSelected(f.id)} />
            ))}
          </div>
        </Section>
        <Section title={`Uploads (${uploads.length})`} defaultOpen={false}>
          <div className="space-y-1">
            {uploads.map((f) => (
              <FileRow key={f.id} f={f} active={sel?.id === f.id} onClick={() => setSelected(f.id)} />
            ))}
          </div>
        </Section>
      </div>
      <div>
        {sel ? (
          <PayloadDetail
            key={sel.id}
            f={sel}
            onReanalyse={() => {
              const m = moduleFor(sel);
              if (m) {
                setCurrent(sel.id);
                navigate(m);
              }
            }}
            onChanged={refreshFiles}
          />
        ) : (
          <div className="text-gray-500 text-sm mt-10 text-center">Select a file.</div>
        )}
      </div>
    </div>
  );
}

function FileRow({ f, active, onClick }: { f: FileInfo; active: boolean; onClick: () => void }) {
  return (
    <button onClick={onClick} className={`w-full text-left px-2 py-1.5 rounded text-xs ${active ? "bg-base-600" : "hover:bg-base-700"}`}>
      <div className="flex items-center gap-2">
        <Badge tone={f.media_type === "image" ? "good" : f.media_type === "audio" ? "warn" : "default"}>{f.format}</Badge>
        <span className="truncate flex-1">{f.name}</span>
        <span className="text-gray-500">{humanSize(f.size)}</span>
      </div>
      {f.meta && f.meta.method ? <div className="text-gray-600 mt-0.5">via {String(f.meta.method)}</div> : null}
    </button>
  );
}

function PayloadDetail({ f, onReanalyse, onChanged }: { f: FileInfo; onReanalyse: () => void; onChanged: () => void }) {
  const [view, setView] = useState<"meta" | "hex" | "text" | "preview" | "extraction">("meta");
  const navigate = useNavigate();
  const setCurrent = useStore((s) => s.setCurrent);
  const reAnalysable = ["image", "audio", "video"].includes(f.media_type);

  return (
    <div>
      <Section
        title={f.name}
        right={
          <div className="flex gap-2">
            <a className="btn btn-xs" href={api.downloadUrl(f.id)} target="_blank" rel="noreferrer">
              Download
            </a>
            {reAnalysable && (
              <button className="btn btn-xs btn-accent" onClick={onReanalyse}>
                Re-analyse in {f.media_type} module →
              </button>
            )}
          </div>
        }
      >
        <div className="flex flex-wrap gap-2 text-xs mb-3">
          <Badge>{f.media_type}</Badge>
          <Badge>{f.format}</Badge>
          <span>{humanSize(f.size)}</span>
          <span className="mono text-gray-500" title={f.sha256}>
            sha256:{f.sha256.slice(0, 24)}…
          </span>
          {f.origin !== "upload" && <Badge tone="good">{f.origin}</Badge>}
        </div>
        <div className="flex gap-1 border-b border-edge mb-3">
          {(["meta", "hex", "text", "preview", "extraction"] as const).map((v) => (
            <div key={v} className={`tab ${view === v ? "tab-active" : ""}`} onClick={() => setView(v)}>
              {v}
            </div>
          ))}
        </div>
        {view === "meta" && <Json data={f} />}
        {view === "hex" && <HexViewer fileId={f.id} />}
        {view === "text" && <TextView fileId={f.id} />}
        {view === "preview" && <Preview f={f} />}
        {view === "extraction" && <ExtractionView f={f} onChanged={onChanged} navigate={navigate} setCurrent={setCurrent} />}
      </Section>
    </div>
  );
}

function TextView({ fileId }: { fileId: string }) {
  const [s, setS] = useState<any>(null);
  useEffect(() => {
    api.strings(fileId, 4).then(setS);
  }, [fileId]);
  if (!s) return <Spinner />;
  return (
    <div className="mono text-xs bg-base-700 rounded p-2 max-h-96 overflow-auto">
      {s.strings.length === 0 && <span className="text-gray-500">No printable strings ≥ 4 chars.</span>}
      {s.strings.map((st: any, i: number) => (
        <div key={i}>
          <span className="text-accent-dim">{st.offset.toString(16).padStart(6, "0")}</span>{" "}
          <span className="break-all">{st.text}</span>
        </div>
      ))}
    </div>
  );
}

function Preview({ f }: { f: FileInfo }) {
  if (f.media_type === "image") return <img src={api.rawUrl(f.id)} className="max-w-full border border-edge rounded" />;
  if (f.media_type === "audio") return <audio controls src={api.rawUrl(f.id)} className="w-full" />;
  if (f.media_type === "video") return <video controls src={api.rawUrl(f.id)} className="max-w-full border border-edge rounded" />;
  return <div className="text-gray-500 text-sm">No inline preview for {f.format}. Use hex / text / download.</div>;
}

function ExtractionView({ f, onChanged, navigate, setCurrent }: any) {
  const [analysis, setAnalysis] = useState<any>(null);
  const [archive, setArchive] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    setAnalysis(null);
    setArchive(null);
    api.analyse(f.id).then(setAnalysis).catch((e) => setError(e.message));
    api.archiveList(f.id).then(setArchive).catch(() => {});
  }, [f.id]);

  async function carveAll() {
    setBusy(true);
    try {
      const r = await api.carveAuto(f.id);
      await onChanged();
      alert(`Carved ${r.count} embedded file(s) → appear in the list`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function extractEntry(name: string) {
    const r = await api.archiveExtract({ file_id: f.id, entry: name });
    await onChanged();
    setCurrent(r.file_id);
    alert(`Extracted ${name} (${humanSize(r.size)}) → now active. Check Results list.`);
  }
  async function recursive() {
    setBusy(true);
    try {
      const r = await api.recursive(f.id);
      await onChanged();
      alert(`Recursive analysis created ${r.nodes.reduce((a: number, n: any) => a + n.children.length, 0)} child payload(s).`);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <ErrorBox error={error} />
      <div className="flex gap-2 mb-3">
        <button className="btn btn-accent" onClick={carveAll} disabled={busy}>
          Carve embedded files
        </button>
        <button className="btn" onClick={recursive} disabled={busy}>
          Recursive extract
        </button>
      </div>
      {archive?.is_zip && (
        <div className="mb-4">
          <div className="label mb-1">ZIP archive — {archive.count} entries</div>
          <table className="w-full text-xs">
            <tbody>
              {archive.entries.map((e: any, i: number) => (
                <tr key={i} className="border-t border-edge/40">
                  <td className="py-1">{e.name}</td>
                  <td className="text-right text-gray-500">{humanSize(e.size)}</td>
                  <td className="text-right">
                    {e.encrypted && <span className="text-warn mr-2">🔒</span>}
                    {!e.is_dir && (
                      <button className="btn btn-xs" onClick={() => extractEntry(e.name)}>
                        extract
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {analysis && (
        <div>
          <div className="label mb-1">Signatures ({analysis.signatures.length})</div>
          <div className="text-xs space-y-0.5 max-h-40 overflow-auto mb-3">
            {analysis.signatures.map((s: any, i: number) => (
              <div key={i}>
                <span className="text-accent-dim mono">{s.offset.toString(16).padStart(6, "0")}</span> {s.name} — {s.description}
              </div>
            ))}
          </div>
          {analysis.interesting?.flags?.length > 0 && (
            <div className="mb-2">
              {analysis.interesting.flags.map((fl: string, i: number) => (
                <div key={i} className="mono text-good bg-good/10 rounded px-2 py-1 mb-1">
                  {fl}
                </div>
              ))}
            </div>
          )}
          {analysis.carved?.length > 0 && (
            <div className="text-xs text-gray-400">
              Carvable: {analysis.carved.map((c: any) => `${c.name}@${c.offset}(${humanSize(c.size)})`).join(", ")}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
