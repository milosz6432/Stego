import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, pollJob } from "../services/api";
import { useStore } from "../store";
import { FileBar } from "../components/FileBar";
import { Plot } from "../components/Plot";
import { Section, Field, Json, ErrorBox, Spinner, Badge } from "../components/ui";

export default function VideoPage() {
  const cur = useStore((s) => s.current());
  const { refreshFiles, setCurrent } = useStore();
  const navigate = useNavigate();
  const [info, setInfo] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setInfo(null);
    if (cur?.media_type === "video") api.videoInfo(cur.id).then(setInfo).catch((e) => setError(e.message));
  }, [cur?.id]);

  if (!cur) return <div className="text-gray-500 text-sm mt-10 text-center">Select a file on the Dashboard first.</div>;
  if (cur.media_type !== "video")
    return (
      <>
        <FileBar />
        <div className="text-gray-500 text-sm mt-10 text-center">Active file is {cur.media_type}. Select a video file.</div>
      </>
    );

  return (
    <div>
      <FileBar />
      <div className="grid lg:grid-cols-2 gap-4">
        <Section title="Container & streams">
          <ErrorBox error={error} />
          {!info ? <Spinner /> : info.ok === false ? <div className="text-bad">{info.error}</div> : <VideoInfo info={info} />}
        </Section>
        <Section title="Extract audio → Audio workspace">
          <AudioExtract fileId={cur.id} info={info} onDone={(id: string) => { refreshFiles().then(() => { setCurrent(id); navigate("/audio"); }); }} />
          <div className="mt-4">
            <ContactSheet fileId={cur.id} />
          </div>
        </Section>
      </div>
      <FramesSection fileId={cur.id} onSent={() => refreshFiles()} navigate={navigate} setCurrent={setCurrent} />
    </div>
  );
}

function VideoInfo({ info }: { info: any }) {
  const v = info.video_streams[0];
  return (
    <div className="text-sm space-y-3">
      <div className="flex flex-wrap gap-2">
        <Badge>{info.format.format_name}</Badge>
        {v && <Badge>{v.codec_name}</Badge>}
        {v && <Badge>{v.width}×{v.height}</Badge>}
        <Badge>{(+info.format.duration).toFixed(2)}s</Badge>
        <Badge>{info.format.nb_streams} streams</Badge>
      </div>
      {info.video_streams.map((s: any, i: number) => (
        <div key={i} className="text-xs border-t border-edge pt-2">
          <div className="label">video #{s.index}</div>
          {s.codec_name} · {s.width}×{s.height} · {s.avg_frame_rate} fps · pix {s.pix_fmt} · {s.nb_frames ?? "?"} frames
        </div>
      ))}
      {info.audio_streams.map((s: any, i: number) => (
        <div key={i} className="text-xs border-t border-edge pt-2">
          <div className="label">audio #{s.index}</div>
          {s.codec_name} · {s.sample_rate} Hz · {s.channels}ch · {s.channel_layout}
        </div>
      ))}
    </div>
  );
}

function AudioExtract({ fileId, info, onDone }: any) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const hasAudio = info?.audio_streams?.length > 0;
  async function go() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.extractVideoAudio(fileId, 0);
      onDone(r.file_id);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <button className="btn btn-accent" onClick={go} disabled={busy || !hasAudio}>
        {busy ? "Extracting…" : hasAudio ? "Extract audio track" : "No audio stream"}
      </button>
      <ErrorBox error={error} />
      <p className="text-xs text-gray-500 mt-2">
        Audio is extracted losslessly to WAV and opened in the Audio workspace for PCM-LSB / spectrogram analysis.
      </p>
    </div>
  );
}

function ContactSheet({ fileId }: { fileId: string }) {
  const [img, setImg] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  async function go() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.contactSheet(fileId, 5, 4);
      setImg(r.image);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div>
      <button className="btn" onClick={go} disabled={busy}>
        {busy ? "Building…" : "Contact sheet"}
      </button>
      <ErrorBox error={error} />
      {img && <img src={img} className="w-full mt-2 border border-edge rounded" />}
    </div>
  );
}

function FramesSection({ fileId, onSent, navigate, setCurrent }: any) {
  const [mode, setMode] = useState("every_n");
  const [n, setN] = useState(30);
  const [interval, setIntervalVal] = useState(1);
  const [threshold, setThreshold] = useState(0.3);
  const [frameset, setFrameset] = useState<string | null>(null);
  const [frames, setFrames] = useState<any[]>([]);
  const [progress, setProgress] = useState<any>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ name: string; src: string } | null>(null);
  const [diff, setDiff] = useState<any>(null);

  async function extract() {
    setBusy(true);
    setError(null);
    setFrames([]);
    setDiff(null);
    try {
      const { job_id } = await api.framesExtract({ file_id: fileId, mode, n, interval, threshold, max_frames: 200 });
      const res = await pollJob<any>(job_id, setProgress);
      setFrameset(res.frameset);
      setFrames(res.frames);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function showFrame(name: string) {
    const r = await api.frameImage(fileId, frameset!, name);
    setPreview({ name, src: r.image });
  }
  async function sendToImage(name: string) {
    const r = await api.sendFrameToImage({ file_id: fileId, frameset, name });
    await onSent();
    setCurrent(r.file_id);
    navigate("/image");
  }
  async function runDiff() {
    setDiff(await api.framesetDiff(fileId, frameset!));
  }

  return (
    <Section title="Frame extraction & analysis">
      <div className="flex flex-wrap gap-2 items-end mb-3">
        <Field label="mode">
          <select className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
            <option value="every_n">every N frames</option>
            <option value="interval">every T seconds</option>
            <option value="scene">scene changes</option>
          </select>
        </Field>
        {mode === "every_n" && (
          <Field label="N">
            <input className="input w-20" type="number" value={n} onChange={(e) => setN(+e.target.value)} />
          </Field>
        )}
        {mode === "interval" && (
          <Field label="seconds">
            <input className="input w-20" type="number" step="0.1" value={interval} onChange={(e) => setIntervalVal(+e.target.value)} />
          </Field>
        )}
        {mode === "scene" && (
          <Field label="threshold">
            <input className="input w-20" type="number" step="0.05" value={threshold} onChange={(e) => setThreshold(+e.target.value)} />
          </Field>
        )}
        <button className="btn btn-accent" onClick={extract} disabled={busy}>
          {busy ? "Extracting…" : "Extract frames"}
        </button>
        {busy && progress && (
          <span className="text-xs text-gray-400">
            <Spinner /> {Math.round(progress.progress * 100)}% {progress.message}
          </span>
        )}
        {frames.length > 0 && (
          <button className="btn" onClick={runDiff}>
            Frame diff series
          </button>
        )}
      </div>
      <ErrorBox error={error} />
      {diff && (
        <div className="mb-3">
          <Plot
            data={[{ x: diff.differences.map((d: any) => d.frame), y: diff.differences.map((d: any) => d.mean_diff), type: "scattergl", mode: "lines+markers", line: { color: "#fbbd23" } }]}
            height={200}
            layout={{ xaxis: { title: "frame" }, yaxis: { title: "mean Δ" } }}
          />
          {diff.anomalies.length > 0 && (
            <div className="text-xs text-warn">Anomalous frames: {diff.anomalies.map((a: any) => `#${a.frame} (z=${a.z_score})`).join(", ")}</div>
          )}
        </div>
      )}
      {frames.length > 0 && (
        <div className="grid grid-cols-6 sm:grid-cols-10 gap-1 mb-3 max-h-48 overflow-auto">
          {frames.map((f) => (
            <button key={f.name} className="border border-edge rounded px-1 py-2 text-[10px] hover:bg-base-700" onClick={() => showFrame(f.name)}>
              {f.index}
            </button>
          ))}
        </div>
      )}
      {preview && (
        <div className="flex gap-4">
          <img src={preview.src} className="max-w-md border border-edge rounded" />
          <div>
            <div className="text-xs text-gray-400 mb-2">{preview.name}</div>
            <button className="btn btn-accent" onClick={() => sendToImage(preview.name)}>
              Send to Image module →
            </button>
          </div>
        </div>
      )}
    </Section>
  );
}
