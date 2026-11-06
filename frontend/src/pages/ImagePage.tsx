import { useEffect, useState } from "react";
import { api } from "../services/api";
import { useStore } from "../store";
import { FileBar } from "../components/FileBar";
import { Plot } from "../components/Plot";
import { Section, Field, Json, ErrorBox, Spinner, Badge, KeyVal } from "../components/ui";

const TABS = ["LSB", "Bitplanes", "Channels", "Format", "Tools"] as const;
type Tab = (typeof TABS)[number];

export default function ImagePage() {
  const cur = useStore((s) => s.current());
  const refreshFiles = useStore((s) => s.refreshFiles);
  const [tab, setTab] = useState<Tab>("LSB");

  if (!cur) return <Empty msg="Upload or select a file on the Dashboard first." />;
  if (cur.media_type !== "image")
    return (
      <>
        <FileBar />
        <Empty msg={`Active file is ${cur.media_type}, not an image. Select an image file.`} />
      </>
    );

  return (
    <div>
      <FileBar />
      <div className="flex gap-1 border-b border-edge mb-4">
        {TABS.map((t) => (
          <div key={t} className={`tab ${tab === t ? "tab-active" : ""}`} onClick={() => setTab(t)}>
            {t}
          </div>
        ))}
      </div>
      {tab === "LSB" && <LsbTab fileId={cur.id} onSaved={refreshFiles} />}
      {tab === "Bitplanes" && <BitplanesTab fileId={cur.id} />}
      {tab === "Channels" && <ChannelsTab fileId={cur.id} />}
      {tab === "Format" && <FormatTab fileId={cur.id} />}
      {tab === "Tools" && <ToolsTab fileId={cur.id} onSaved={refreshFiles} />}
    </div>
  );
}

function Empty({ msg }: { msg: string }) {
  return <div className="text-gray-500 text-sm mt-10 text-center">{msg}</div>;
}

// ---------------- LSB ----------------
const CHANNELS = ["R", "G", "B", "A"];
function LsbTab({ fileId, onSaved }: { fileId: string; onSaved: () => void }) {
  const [channels, setChannels] = useState<string[]>(["R", "G", "B"]);
  const [planes, setPlanes] = useState<number[]>([0]);
  const [traversal, setTraversal] = useState("row");
  const [channelMode, setChannelMode] = useState("interleave");
  const [bitOrder, setBitOrder] = useState("msb");
  const [planeOrder, setPlaneOrder] = useState("ascending");
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState<string | null>(null);

  const body = {
    file_id: fileId,
    channels,
    bit_planes: planes,
    traversal,
    channel_mode: channelMode,
    bit_order: bitOrder,
    plane_order: planeOrder,
    max_bytes: 1 << 20,
  };

  async function run() {
    setBusy(true);
    setError(null);
    setSaved(null);
    try {
      setResult(await api.imageLsb(body));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    try {
      const r = await api.imageLsbSave(body);
      setSaved(r.file_id);
      onSaved();
    } catch (e: any) {
      setError(e.message);
    }
  }

  return (
    <div className="grid lg:grid-cols-[320px,1fr] gap-4">
      <Section title="LSB parameters">
        <div className="space-y-3">
          <div>
            <div className="label mb-1">Channels</div>
            <div className="flex gap-2">
              {CHANNELS.map((c) => (
                <label key={c} className="chip cursor-pointer">
                  <input
                    type="checkbox"
                    checked={channels.includes(c)}
                    onChange={(e) =>
                      setChannels((cs) => (e.target.checked ? [...cs, c] : cs.filter((x) => x !== c)))
                    }
                  />
                  {c}
                </label>
              ))}
            </div>
          </div>
          <div>
            <div className="label mb-1">Bit planes (0 = LSB)</div>
            <div className="flex gap-1 flex-wrap">
              {[0, 1, 2, 3, 4, 5, 6, 7].map((b) => (
                <label key={b} className={`chip cursor-pointer ${planes.includes(b) ? "border-accent text-accent" : ""}`}>
                  <input
                    type="checkbox"
                    className="hidden"
                    checked={planes.includes(b)}
                    onChange={(e) => setPlanes((ps) => (e.target.checked ? [...ps, b].sort() : ps.filter((x) => x !== b)))}
                  />
                  {b}
                </label>
              ))}
            </div>
          </div>
          <Field label="Pixel traversal">
            <select className="input" value={traversal} onChange={(e) => setTraversal(e.target.value)}>
              <option value="row">Row-major</option>
              <option value="column">Column-major</option>
            </select>
          </Field>
          <Field label="Channel layout">
            <select className="input" value={channelMode} onChange={(e) => setChannelMode(e.target.value)}>
              <option value="interleave">Interleave (per pixel)</option>
              <option value="sequential">Sequential (channel by channel)</option>
            </select>
          </Field>
          <Field label="Bit order within byte">
            <select className="input" value={bitOrder} onChange={(e) => setBitOrder(e.target.value)}>
              <option value="msb">MSB first</option>
              <option value="lsb">LSB first</option>
            </select>
          </Field>
          <Field label="Plane order">
            <select className="input" value={planeOrder} onChange={(e) => setPlaneOrder(e.target.value)}>
              <option value="ascending">Ascending</option>
              <option value="descending">Descending</option>
            </select>
          </Field>
          <div className="flex gap-2">
            <button className="btn btn-accent flex-1" onClick={run} disabled={busy || !channels.length}>
              {busy ? "Extracting…" : "Extract"}
            </button>
            <button className="btn" onClick={save} disabled={!result}>
              Save payload
            </button>
          </div>
          {saved && <div className="text-good text-xs">Saved as recovered file → Results tab</div>}
        </div>
      </Section>
      <div>
        <ErrorBox error={error} />
        {result && <LsbResult result={result} />}
      </div>
    </div>
  );
}

function LsbResult({ result }: { result: any }) {
  const text = result.text || {};
  return (
    <>
      <Section title={`Extraction (${result.extracted_bytes} bytes of ${result.total_bits} bits)`}>
        {result.interesting?.flags?.length > 0 && (
          <div className="mb-3">
            <div className="label mb-1">Flag-like tokens</div>
            {result.interesting.flags.map((f: string, i: number) => (
              <div key={i} className="mono text-good bg-good/10 rounded px-2 py-1 mb-1">
                {f}
              </div>
            ))}
          </div>
        )}
        <div className="label mb-1">Text decodings</div>
        <div className="space-y-2">
          {["ascii", "utf-8", "utf-16-le", "latin-1"].map((enc) =>
            text[enc] ? (
              <div key={enc}>
                <div className="text-xs text-gray-500">
                  {enc} · {Math.round((text[enc].printable_ratio ?? 0) * 100)}% printable
                </div>
                <div className="mono text-xs bg-base-700 rounded p-2 max-h-28 overflow-auto whitespace-pre-wrap break-all">
                  {text[enc].text?.slice(0, 2000)}
                </div>
              </div>
            ) : null,
          )}
        </div>
      </Section>
      <Section title="Hex preview" defaultOpen={false}>
        <div className="mono text-xs bg-base-700 rounded p-2 overflow-auto max-h-80">
          {result.hex.map((r: any) => (
            <div key={r.offset} className="flex gap-4 whitespace-pre">
              <span className="text-accent-dim">{r.offset.toString(16).padStart(8, "0")}</span>
              <span>{r.hex.padEnd(47, " ")}</span>
              <span className="text-gray-400">{r.ascii}</span>
            </div>
          ))}
        </div>
      </Section>
    </>
  );
}

// ---------------- Bitplanes ----------------
function BitplanesTab({ fileId }: { fileId: string }) {
  const [overview, setOverview] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [img, setImg] = useState<{ src: string; meta: any } | null>(null);
  const [invert, setInvert] = useState(false);
  const [sel, setSel] = useState<{ channel: string; bit: number } | null>(null);

  useEffect(() => {
    setOverview(null);
    setImg(null);
    api.bitplaneOverview(fileId).then(setOverview).catch((e) => setError(e.message));
  }, [fileId]);

  async function show(channel: string, bit: number) {
    setSel({ channel, bit });
    const r = await api.bitplane(fileId, channel, bit, invert);
    setImg({ src: r.image, meta: r.meta });
  }
  useEffect(() => {
    if (sel) show(sel.channel, sel.bit);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [invert]);

  return (
    <div className="grid lg:grid-cols-[1fr,1fr] gap-4">
      <Section title="Bit-plane structure (higher score = more suspicious)">
        <ErrorBox error={error} />
        {!overview ? (
          <Spinner label="Scoring planes…" />
        ) : (
          <table className="w-full text-xs">
            <thead className="text-gray-500">
              <tr>
                <th className="text-left">Channel</th>
                <th className="text-left">Bit</th>
                <th className="text-left">Set %</th>
                <th className="text-left">Structure</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {overview.planes.map((p: any, i: number) => (
                <tr key={i} className="border-t border-edge/50 hover:bg-base-700">
                  <td>{p.channel}</td>
                  <td>{p.bit}</td>
                  <td>{(p.set_fraction * 100).toFixed(1)}%</td>
                  <td>
                    <span className={p.structure_score > 0.15 ? "text-warn" : "text-gray-500"}>
                      {p.structure_score.toFixed(3)}
                    </span>
                  </td>
                  <td>
                    <button className="btn btn-xs" onClick={() => show(p.channel, p.bit)}>
                      view
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Section>
      <Section
        title="Plane viewer"
        right={
          <label className="chip cursor-pointer">
            <input type="checkbox" checked={invert} onChange={(e) => setInvert(e.target.checked)} /> invert
          </label>
        }
      >
        {img ? (
          <div>
            <div className="text-xs text-gray-400 mb-2">
              {img.meta.channel} bit {img.meta.bit} · set {(img.meta.set_fraction * 100).toFixed(1)}% · structure{" "}
              {img.meta.structure_score}
            </div>
            <img src={img.src} className="max-w-full border border-edge rounded image-pixelated" style={{ imageRendering: "pixelated" }} />
          </div>
        ) : (
          <div className="text-gray-500 text-sm">Select a plane to view.</div>
        )}
      </Section>
    </div>
  );
}

// ---------------- Channels ----------------
function ChannelsTab({ fileId }: { fileId: string }) {
  const [hist, setHist] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [img, setImg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [invert, setInvert] = useState(false);
  const [gray, setGray] = useState(false);
  const [bright, setBright] = useState(0);
  const [contrast, setContrast] = useState(1);

  useEffect(() => {
    setImg(null);
    api.histograms(fileId).then(setHist).catch((e) => setError(e.message));
    api.imageStats(fileId).then(setStats).catch(() => {});
  }, [fileId]);

  async function applyTransform() {
    const r = await api.imageTransform({ file_id: fileId, invert, grayscale: gray, brightness: bright, contrast });
    setImg(r.image);
  }

  const histData =
    hist &&
    hist.channels.map((c: string) => ({
      x: Array.from({ length: 256 }, (_, i) => i),
      y: hist.histograms[c],
      type: "bar",
      name: c,
      marker: { color: { R: "#f87272", G: "#36d399", B: "#4f9dff", A: "#bbb", L: "#ccc" }[c] || "#888" },
    }));

  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <Section title="Channel histograms">
        <ErrorBox error={error} />
        {histData ? <Plot data={histData} layout={{ barmode: "overlay", height: 300 }} /> : <Spinner />}
      </Section>
      <Section title="Per-channel statistics (incl. LSB chi-square)">
        {stats ? (
          <table className="w-full text-xs">
            <thead className="text-gray-500">
              <tr>
                <th className="text-left">Ch</th>
                <th>Mean</th>
                <th>Std</th>
                <th>LSB set%</th>
                <th>χ² (LSB)</th>
              </tr>
            </thead>
            <tbody>
              {Object.entries(stats.stats).map(([c, s]: any) => (
                <tr key={c} className="border-t border-edge/50">
                  <td>{c}</td>
                  <td className="text-center">{s.mean}</td>
                  <td className="text-center">{s.std}</td>
                  <td className="text-center">{(s.lsb_set_fraction * 100).toFixed(1)}%</td>
                  <td className="text-center">{s.lsb_chi_square}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <Spinner />
        )}
      </Section>
      <Section title="Transforms (original file unchanged)">
        <div className="grid grid-cols-2 gap-3 mb-3">
          <label className="chip cursor-pointer">
            <input type="checkbox" checked={invert} onChange={(e) => setInvert(e.target.checked)} /> invert
          </label>
          <label className="chip cursor-pointer">
            <input type="checkbox" checked={gray} onChange={(e) => setGray(e.target.checked)} /> grayscale
          </label>
          <Field label={`brightness ${bright}`}>
            <input type="range" min={-128} max={128} value={bright} onChange={(e) => setBright(+e.target.value)} />
          </Field>
          <Field label={`contrast ${contrast.toFixed(1)}`}>
            <input type="range" min={0.2} max={4} step={0.1} value={contrast} onChange={(e) => setContrast(+e.target.value)} />
          </Field>
        </div>
        <button className="btn btn-accent" onClick={applyTransform}>
          Apply
        </button>
        {img && <img src={img} className="max-w-full mt-3 border border-edge rounded" />}
      </Section>
      <Section title="Channel difference">
        <ChannelDiff fileId={fileId} channels={hist?.channels || ["R", "G", "B"]} />
      </Section>
    </div>
  );
}

function ChannelDiff({ fileId, channels }: { fileId: string; channels: string[] }) {
  const [a, setA] = useState("R");
  const [b, setB] = useState("G");
  const [amp, setAmp] = useState(1);
  const [img, setImg] = useState<string | null>(null);
  async function run() {
    const r = await api.channelDiff(fileId, a, b, amp);
    setImg(r.image);
  }
  return (
    <div>
      <div className="flex gap-2 items-end mb-2">
        <Field label="A">
          <select className="input" value={a} onChange={(e) => setA(e.target.value)}>
            {channels.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </Field>
        <Field label="B">
          <select className="input" value={b} onChange={(e) => setB(e.target.value)}>
            {channels.map((c) => (
              <option key={c}>{c}</option>
            ))}
          </select>
        </Field>
        <Field label={`amplify ${amp}x`}>
          <input type="range" min={1} max={16} value={amp} onChange={(e) => setAmp(+e.target.value)} />
        </Field>
        <button className="btn btn-accent" onClick={run}>
          Diff
        </button>
      </div>
      {img && <img src={img} className="max-w-full border border-edge rounded" />}
    </div>
  );
}

// ---------------- Format ----------------
function FormatTab({ fileId }: { fileId: string }) {
  const [data, setData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setData(null);
    api.imageFormat(fileId).then(setData).catch((e) => setError(e.message));
  }, [fileId]);
  if (error) return <ErrorBox error={error} />;
  if (!data) return <Spinner label="Parsing format…" />;
  const a = data.analysis;
  return (
    <div>
      <Section title={`${data.format.toUpperCase()} structure`}>
        {a.anomalies?.length > 0 && (
          <div className="mb-3">
            <div className="label mb-1">Anomalies</div>
            {a.anomalies.map((an: any, i: number) => (
              <div key={i} className="text-warn text-xs mb-1">
                ⚠ <b>{an.type}</b> {an.chunk ? `[${an.chunk}]` : ""} @ {an.offset ?? "?"} — {an.detail}
              </div>
            ))}
          </div>
        )}
        {a.trailing_data && (
          <div className="mb-3 bg-warn/10 border border-warn/40 rounded p-2 text-xs">
            <b>Trailing data:</b> {a.trailing_data.size} bytes after end (printable{" "}
            {Math.round(a.trailing_data.printable_ratio * 100)}%).{" "}
            <span className="text-gray-400">See Results → Extraction to recover it.</span>
          </div>
        )}
        <Json data={a} />
      </Section>
    </div>
  );
}

// ---------------- Tools ----------------
function ToolsTab({ fileId, onSaved }: { fileId: string; onSaved: () => void }) {
  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <ZstegTool fileId={fileId} onSaved={onSaved} />
      <PassphraseTool fileId={fileId} onSaved={onSaved} />
      <SimpleTool fileId={fileId} label="exiftool (metadata)" run={(id) => api.exiftool(id)} />
      <SimpleTool fileId={fileId} label="binwalk (embedded files)" run={(id) => api.binwalk(id)} />
      <SimpleTool fileId={fileId} label="Tesseract OCR" run={(id) => api.ocr(id)} />
      <SimpleTool fileId={fileId} label="outguess (JPEG)" run={(id) => api.outguess(id)} />
    </div>
  );
}

function ZstegTool({ fileId, onSaved }: { fileId: string; onSaved: () => void }) {
  const [res, setRes] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function run() {
    setBusy(true);
    setError(null);
    try {
      setRes(await api.zsteg(fileId, true));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function extract(method: string) {
    try {
      const r = await api.zstegExtract(fileId, method);
      if (r.ok) onSaved();
      alert(r.ok ? `Extracted ${r.size} bytes → Results tab` : "zsteg extraction returned no data");
    } catch (e: any) {
      setError(e.message);
    }
  }
  return (
    <Section title="zsteg (PNG/BMP LSB)">
      <button className="btn btn-accent mb-2" onClick={run} disabled={busy}>
        {busy ? "Running…" : "Run zsteg -a"}
      </button>
      <ErrorBox error={error} />
      {res && (
        <div className="text-xs">
          <div className="text-gray-400 mb-1">{res.finding_count} findings · exit {res.command.returncode}</div>
          <div className="max-h-72 overflow-auto space-y-1">
            {res.findings.map((f: any, i: number) => (
              <div key={i} className="flex items-center gap-2 border-b border-edge/40 py-0.5">
                <span className="mono text-accent-dim flex-1 truncate" title={f.method}>
                  {f.method}
                </span>
                <span className="mono truncate flex-1" title={f.value}>
                  {f.value}
                </span>
                <button className="btn btn-xs" onClick={() => extract(f.method.split(" ")[0])}>
                  save
                </button>
              </div>
            ))}
          </div>
        </div>
      )}
    </Section>
  );
}

function PassphraseTool({ fileId, onSaved }: { fileId: string; onSaved: () => void }) {
  const [pass, setPass] = useState("");
  const [res, setRes] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  async function steghide() {
    setError(null);
    try {
      const r = await api.steghide(fileId, pass);
      setRes(r);
      if (r.file_id) onSaved();
    } catch (e: any) {
      setError(e.message);
    }
  }
  async function stegseek() {
    setError(null);
    try {
      const r = await api.stegseek(fileId);
      setRes(r);
      if (r.file_id) onSaved();
    } catch (e: any) {
      setError(e.message);
    }
  }
  return (
    <Section title="steghide / stegseek (JPEG/BMP/WAV)">
      <div className="flex gap-2 mb-2">
        <input className="input flex-1" placeholder="passphrase (blank = none)" value={pass} onChange={(e) => setPass(e.target.value)} />
        <button className="btn btn-accent" onClick={steghide}>
          steghide
        </button>
        <button className="btn" onClick={stegseek}>
          stegseek
        </button>
      </div>
      <ErrorBox error={error} />
      {res && (
        <div className="text-xs">
          <div className={res.ok ? "text-good" : "text-gray-400"}>
            {res.ok ? `Extracted ${res.extracted_bytes} bytes` : "No payload extracted"}
            {res.passphrase ? ` · passphrase: "${res.passphrase}"` : ""}
          </div>
          {res.command && <div className="mono text-gray-600 mt-1 break-all">{res.command.command}</div>}
          {res.command?.stderr && <div className="text-bad mt-1 whitespace-pre-wrap">{res.command.stderr.slice(0, 400)}</div>}
        </div>
      )}
    </Section>
  );
}

function SimpleTool({ fileId, label, run }: { fileId: string; label: string; run: (id: string) => Promise<any> }) {
  const [res, setRes] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    setError(null);
    try {
      setRes(await run(fileId));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Section title={label}>
      <button className="btn btn-accent mb-2" onClick={go} disabled={busy}>
        {busy ? "Running…" : "Run"}
      </button>
      <ErrorBox error={error} />
      {res && <Json data={res.metadata ?? res.text ?? res.signatures ?? res} />}
    </Section>
  );
}
