import { useEffect, useRef, useState } from "react";
import { api } from "../services/api";
import { useStore } from "../store";
import { FileBar } from "../components/FileBar";
import { Plot } from "../components/Plot";
import { Section, Field, Json, ErrorBox, Spinner, Badge, KeyVal } from "../components/ui";

const TABS = ["Waveform", "Spectrogram", "FFT", "PCM LSB", "Advanced", "Decoders"] as const;
type Tab = (typeof TABS)[number];

export default function AudioPage() {
  const cur = useStore((s) => s.current());
  const refreshFiles = useStore((s) => s.refreshFiles);
  const [tab, setTab] = useState<Tab>("Waveform");
  const [info, setInfo] = useState<any>(null);
  const [range, setRange] = useState<{ start?: number; end?: number }>({});

  useEffect(() => {
    setInfo(null);
    if (cur?.media_type === "audio") api.audioInfo(cur.id).then(setInfo).catch(() => {});
  }, [cur?.id]);

  if (!cur) return <div className="text-gray-500 text-sm mt-10 text-center">Select a file on the Dashboard first.</div>;
  if (cur.media_type !== "audio")
    return (
      <>
        <FileBar />
        <div className="text-gray-500 text-sm mt-10 text-center">
          Active file is {cur.media_type}. Select an audio file, or extract audio from a video on the Video tab.
        </div>
      </>
    );

  return (
    <div>
      <FileBar />
      <Player fileId={cur.id} />
      {info && (
        <div className="card p-3 mb-4 flex flex-wrap gap-2 items-center text-xs">
          <Badge>{info.format}</Badge>
          <Badge tone={info.is_lossless_pcm ? "good" : "warn"}>
            {info.is_lossless_pcm ? "lossless PCM" : "lossy/decoded"}
          </Badge>
          <span>{info.sample_rate} Hz</span>
          <span>{info.channels} ch</span>
          <span>{info.duration?.toFixed(2)} s</span>
          {info.sample_width_bits && <span>{info.sample_width_bits}-bit</span>}
          {info.transformations?.length > 0 && (
            <span className="text-warn" title={info.transformations.join("\n")}>
              ⚠ decoded ({info.transformations.length} transform)
            </span>
          )}
          <span className="ml-auto text-gray-500">
            range: {range.start?.toFixed(2) ?? "0"}s – {range.end?.toFixed(2) ?? info.duration?.toFixed(2) ?? "end"}s
          </span>
        </div>
      )}
      <div className="flex gap-1 border-b border-edge mb-4">
        {TABS.map((t) => (
          <div key={t} className={`tab ${tab === t ? "tab-active" : ""}`} onClick={() => setTab(t)}>
            {t}
          </div>
        ))}
      </div>
      {tab === "Waveform" && <WaveformTab fileId={cur.id} range={range} setRange={setRange} info={info} onSaved={refreshFiles} />}
      {tab === "Spectrogram" && <SpectrogramTab fileId={cur.id} range={range} info={info} />}
      {tab === "FFT" && <FftTab fileId={cur.id} range={range} info={info} />}
      {tab === "PCM LSB" && <PcmTab fileId={cur.id} info={info} onSaved={refreshFiles} />}
      {tab === "Advanced" && <AdvancedTab fileId={cur.id} range={range} info={info} />}
      {tab === "Decoders" && <DecodersTab fileId={cur.id} range={range} />}
    </div>
  );
}

function Player({ fileId }: { fileId: string }) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [speed, setSpeed] = useState(1);
  return (
    <div className="card p-3 mb-4 flex items-center gap-4">
      <audio ref={audioRef} controls src={api.rawUrl(fileId)} className="flex-1" />
      <Field label={`speed ${speed}x`}>
        <input
          type="range"
          min={0.25}
          max={2}
          step={0.25}
          value={speed}
          onChange={(e) => {
            setSpeed(+e.target.value);
            if (audioRef.current) audioRef.current.playbackRate = +e.target.value;
          }}
        />
      </Field>
    </div>
  );
}

function RangeControls({ range, setRange, duration }: any) {
  return (
    <div className="flex gap-2 items-end mb-3">
      <Field label="start (s)">
        <input
          className="input w-24"
          type="number"
          step="0.01"
          value={range.start ?? ""}
          onChange={(e) => setRange((r: any) => ({ ...r, start: e.target.value === "" ? undefined : +e.target.value }))}
        />
      </Field>
      <Field label="end (s)">
        <input
          className="input w-24"
          type="number"
          step="0.01"
          value={range.end ?? ""}
          onChange={(e) => setRange((r: any) => ({ ...r, end: e.target.value === "" ? undefined : +e.target.value }))}
        />
      </Field>
      <button className="btn btn-xs" onClick={() => setRange({})}>
        clear
      </button>
    </div>
  );
}

function WaveformTab({ fileId, range, setRange, info, onSaved }: any) {
  const [data, setData] = useState<any>(null);
  const [stats, setStats] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setData(null);
    api.waveform(fileId, 2000).then(setData).catch((e) => setError(e.message));
    api.audioStats(fileId).then(setStats).catch(() => {});
  }, [fileId]);

  async function exportSeg() {
    const r = await api.exportSegment(fileId, range.start, range.end);
    onSaved();
    alert(`Exported segment → Results tab (${r.name})`);
  }

  const traces =
    data &&
    data.peaks.map((peaks: number[][], ch: number) => {
      const x: number[] = [];
      const y: number[] = [];
      const dur = (data.range.end_time - data.range.start_time) || data.duration;
      peaks.forEach((mm, i) => {
        const t = data.range.start_time + (i / peaks.length) * dur;
        x.push(t, t);
        y.push(mm[0], mm[1]);
      });
      return { x, y, type: "scattergl", mode: "lines", name: `ch${ch}`, line: { width: 0.6 } };
    });

  return (
    <div className="grid lg:grid-cols-[1fr,320px] gap-4">
      <Section title="Waveform (drag-select a range on the plot)">
        <ErrorBox error={error} />
        {traces ? (
          <Plot
            data={traces}
            height={320}
            layout={{ xaxis: { title: "time (s)" }, yaxis: { title: "amplitude", range: [-1, 1] } }}
            onRelayout={(e) => {
              if (e["xaxis.range[0]"] != null)
                setRange({ start: +e["xaxis.range[0]"], end: +e["xaxis.range[1]"] });
            }}
          />
        ) : (
          <Spinner label="Rendering waveform…" />
        )}
        <RangeControls range={range} setRange={setRange} duration={info?.duration} />
        <button className="btn btn-accent" onClick={exportSeg}>
          Export selected segment → Results
        </button>
      </Section>
      <Section title="Amplitude statistics">
        {stats ? (
          <div>
            {stats.per_channel.map((s: any) => (
              <div key={s.channel} className="mb-2 text-xs">
                <div className="label">channel {s.channel}</div>
                <KeyVal
                  data={{
                    RMS: `${s.rms} (${s.rms_db} dB)`,
                    Peak: `${s.peak} (${s.peak_db} dB)`,
                    "Crest factor": s.crest_factor,
                    "Zero crossings": s.zero_crossings,
                    "DC offset": s.dc_offset,
                  }}
                />
              </div>
            ))}
            <div className="label mt-2">Silence regions: {stats.silence_regions.length}</div>
          </div>
        ) : (
          <Spinner />
        )}
      </Section>
    </div>
  );
}

const WINDOWS = ["hann", "hamming", "blackman", "bartlett", "boxcar", "blackmanharris", "flattop"];
const CMAPS = ["magma", "viridis", "inferno", "plasma", "turbo", "gray", "jet"];

function SpectrogramTab({ fileId, range, info }: any) {
  const [p, setP] = useState({ n_fft: 1024, window: "hann", scale: "linear", colormap: "magma", top_db: 80, f_min: 0, f_max: 0, overlap: 0.75, channel: 0 });
  const [img, setImg] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const r = await api.spectrogram({
        file_id: fileId,
        channel: p.channel,
        n_fft: p.n_fft,
        window: p.window,
        overlap: p.overlap,
        scale: p.scale,
        colormap: p.colormap,
        top_db: p.top_db,
        f_min: p.f_min,
        f_max: p.f_max || null,
        start: range.start,
        end: range.end,
      });
      setImg(r);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    run(); /* eslint-disable-next-line */
  }, [fileId]);

  return (
    <div className="grid lg:grid-cols-[300px,1fr] gap-4">
      <Section title="Spectrogram controls">
        <div className="space-y-2">
          <Field label="FFT size">
            <select className="input" value={p.n_fft} onChange={(e) => setP({ ...p, n_fft: +e.target.value })}>
              {[256, 512, 1024, 2048, 4096, 8192].map((n) => (
                <option key={n}>{n}</option>
              ))}
            </select>
          </Field>
          <Field label={`overlap ${Math.round(p.overlap * 100)}%`}>
            <input type="range" min={0} max={0.95} step={0.05} value={p.overlap} onChange={(e) => setP({ ...p, overlap: +e.target.value })} />
          </Field>
          <Field label="window">
            <select className="input" value={p.window} onChange={(e) => setP({ ...p, window: e.target.value })}>
              {WINDOWS.map((w) => (
                <option key={w}>{w}</option>
              ))}
            </select>
          </Field>
          <Field label="frequency scale">
            <select className="input" value={p.scale} onChange={(e) => setP({ ...p, scale: e.target.value })}>
              <option value="linear">linear</option>
              <option value="log">logarithmic</option>
              <option value="mel">mel</option>
            </select>
          </Field>
          <Field label="colormap">
            <select className="input" value={p.colormap} onChange={(e) => setP({ ...p, colormap: e.target.value })}>
              {CMAPS.map((c) => (
                <option key={c}>{c}</option>
              ))}
            </select>
          </Field>
          <Field label={`dynamic range ${p.top_db} dB`}>
            <input type="range" min={20} max={120} value={p.top_db} onChange={(e) => setP({ ...p, top_db: +e.target.value })} />
          </Field>
          <div className="grid grid-cols-2 gap-2">
            <Field label="f min (Hz)">
              <input className="input" type="number" value={p.f_min} onChange={(e) => setP({ ...p, f_min: +e.target.value })} />
            </Field>
            <Field label="f max (0=nyq)">
              <input className="input" type="number" value={p.f_max} onChange={(e) => setP({ ...p, f_max: +e.target.value })} />
            </Field>
          </div>
          {info?.channels > 1 && (
            <Field label="channel">
              <select className="input" value={p.channel} onChange={(e) => setP({ ...p, channel: +e.target.value })}>
                {Array.from({ length: info.channels }, (_, i) => (
                  <option key={i} value={i}>
                    {i}
                  </option>
                ))}
              </select>
            </Field>
          )}
          <button className="btn btn-accent w-full" onClick={run} disabled={busy}>
            {busy ? "Rendering…" : "Render"}
          </button>
        </div>
      </Section>
      <Section title="Spectrogram">
        <ErrorBox error={error} />
        {img ? (
          <div>
            <img src={img.image} className="w-full border border-edge rounded" />
            <div className="text-xs text-gray-500 mt-1">
              {img.meta.freq_bins} freq bins · {img.meta.time_frames} frames · {img.meta.time_start?.toFixed(2)}–
              {img.meta.time_end?.toFixed(2)}s · {img.meta.f_min}–{img.meta.f_max} Hz
            </div>
            <a className="btn btn-xs mt-2 inline-block" href={img.image} download="spectrogram.png">
              Export PNG
            </a>
          </div>
        ) : busy ? (
          <Spinner label="Rendering spectrogram…" />
        ) : null}
      </Section>
    </div>
  );
}

function FftTab({ fileId, range, info }: any) {
  const [data, setData] = useState<any>(null);
  const [channel, setChannel] = useState(0);
  const [error, setError] = useState<string | null>(null);
  async function run() {
    setError(null);
    try {
      setData(await api.fft(fileId, channel, range.start, range.end));
    } catch (e: any) {
      setError(e.message);
    }
  }
  useEffect(() => {
    run(); /* eslint-disable-next-line */
  }, [fileId, channel]);
  return (
    <div className="grid lg:grid-cols-[1fr,280px] gap-4">
      <Section title="Frequency spectrum">
        <ErrorBox error={error} />
        {data ? (
          <Plot
            data={[{ x: data.freqs, y: data.magnitude_db, type: "scattergl", mode: "lines", line: { color: "#4f9dff", width: 1 } }]}
            height={340}
            layout={{ xaxis: { title: "Hz" }, yaxis: { title: "dB" } }}
          />
        ) : (
          <Spinner />
        )}
        <button className="btn btn-xs mt-2" onClick={run}>
          Recompute for selected range
        </button>
      </Section>
      <Section title="Peak frequencies">
        {info?.channels > 1 && (
          <Field label="channel">
            <select className="input mb-2" value={channel} onChange={(e) => setChannel(+e.target.value)}>
              {Array.from({ length: info.channels }, (_, i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </Field>
        )}
        {data && (
          <table className="w-full text-xs">
            <thead className="text-gray-500">
              <tr>
                <th className="text-left">Hz</th>
                <th>rel dB</th>
                <th>harmonic</th>
              </tr>
            </thead>
            <tbody>
              {data.peaks.slice(0, 15).map((pk: any, i: number) => {
                const h = data.harmonics.find((x: any) => x.frequency === pk.frequency);
                return (
                  <tr key={i} className="border-t border-edge/40">
                    <td>{pk.frequency}</td>
                    <td className="text-center">{pk.relative_db}</td>
                    <td className="text-center">{h ? `×${h.harmonic_number}` : ""}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </Section>
    </div>
  );
}

function PcmTab({ fileId, info, onSaved }: any) {
  const [channels, setChannels] = useState<number[]>([0]);
  const [planes, setPlanes] = useState<number[]>([0]);
  const [mode, setMode] = useState("interleave");
  const [order, setOrder] = useState("msb");
  const [res, setRes] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const nch = info?.channels ?? 2;
  const width = info?.sample_width_bits ?? 16;
  const body = { file_id: fileId, channels, bit_planes: planes, channel_mode: mode, bit_order: order, max_bytes: 1 << 20 };

  async function run() {
    setBusy(true);
    setError(null);
    try {
      setRes(await api.pcmLsb(body));
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  async function save() {
    const r = await api.pcmLsbSave(body);
    onSaved();
    alert(`Saved payload → Results tab (${r.name})`);
  }

  return (
    <div className="grid lg:grid-cols-[320px,1fr] gap-4">
      <Section title="PCM sample LSB">
        {!info?.is_lossless_pcm && (
          <div className="bg-warn/10 border border-warn/40 rounded p-2 text-xs mb-3 text-warn">
            This source is not lossless PCM. Sample-LSB extraction is not meaningful on decoded lossy
            audio and the backend will refuse it.
          </div>
        )}
        <div className="space-y-3">
          <div>
            <div className="label mb-1">Channels</div>
            <div className="flex gap-2">
              {Array.from({ length: nch }, (_, i) => i).map((c) => (
                <label key={c} className="chip cursor-pointer">
                  <input
                    type="checkbox"
                    checked={channels.includes(c)}
                    onChange={(e) => setChannels((cs) => (e.target.checked ? [...cs, c] : cs.filter((x) => x !== c)))}
                  />
                  {c}
                </label>
              ))}
            </div>
          </div>
          <div>
            <div className="label mb-1">Bit positions (0 = LSB, up to {width - 1})</div>
            <div className="flex gap-1 flex-wrap">
              {Array.from({ length: Math.min(width, 16) }, (_, i) => i).map((b) => (
                <label key={b} className={`chip cursor-pointer ${planes.includes(b) ? "border-accent text-accent" : ""}`}>
                  <input type="checkbox" className="hidden" checked={planes.includes(b)} onChange={(e) => setPlanes((ps) => (e.target.checked ? [...ps, b].sort((a, z) => a - z) : ps.filter((x) => x !== b)))} />
                  {b}
                </label>
              ))}
            </div>
          </div>
          <Field label="Channel layout">
            <select className="input" value={mode} onChange={(e) => setMode(e.target.value)}>
              <option value="interleave">Interleave</option>
              <option value="sequential">Sequential</option>
            </select>
          </Field>
          <Field label="Bit order">
            <select className="input" value={order} onChange={(e) => setOrder(e.target.value)}>
              <option value="msb">MSB first</option>
              <option value="lsb">LSB first</option>
            </select>
          </Field>
          <div className="flex gap-2">
            <button className="btn btn-accent flex-1" onClick={run} disabled={busy || !channels.length}>
              {busy ? "Extracting…" : "Extract"}
            </button>
            <button className="btn" onClick={save} disabled={!res}>
              Save
            </button>
          </div>
        </div>
      </Section>
      <div>
        <ErrorBox error={error} />
        {res && <PcmResult res={res} />}
      </div>
    </div>
  );
}

function PcmResult({ res }: { res: any }) {
  return (
    <Section title={`Extracted ${res.extracted_bytes} bytes`}>
      {res.interesting?.flags?.length > 0 &&
        res.interesting.flags.map((f: string, i: number) => (
          <div key={i} className="mono text-good bg-good/10 rounded px-2 py-1 mb-1">
            {f}
          </div>
        ))}
      {res.signatures?.length > 0 && (
        <div className="text-xs text-warn mb-2">
          File signatures in payload: {res.signatures.map((s: any) => `${s.format}@${s.offset}`).join(", ")}
        </div>
      )}
      {["ascii", "utf-8", "latin-1"].map((enc) =>
        res.text[enc] ? (
          <div key={enc} className="mb-2">
            <div className="text-xs text-gray-500">{enc}</div>
            <div className="mono text-xs bg-base-700 rounded p-2 max-h-28 overflow-auto whitespace-pre-wrap break-all">
              {res.text[enc].text?.slice(0, 1500)}
            </div>
          </div>
        ) : null,
      )}
    </Section>
  );
}

function AdvancedTab({ fileId, range, info }: any) {
  return (
    <div className="grid lg:grid-cols-2 gap-4">
      <AdvCard title="Phase coding" run={() => api.phase(fileId, 0, range.start, range.end)} plot={(d: any) => ({ x: d.freqs, y: d.phase, name: "phase" })} note={(d: any) => `concentration ${d.phase_concentration}${d.suspicious ? " — suspicious" : ""}`} />
      <AdvCard title="Echo hiding (cepstrum)" run={() => api.echo(fileId, 0, range.start, range.end)} plot={(d: any) => ({ x: d.lags_ms, y: d.cepstrum, name: "cepstrum" })} note={(d: any) => `dominant echo ${d.dominant_echo_ms} ms`} />
      <AdvCard title="Zero-crossing rate" run={() => api.zeroCrossing(fileId, 0)} plot={(d: any) => ({ x: d.times, y: d.zcr, name: "zcr" })} />
      <SimpleAudio title="Stereo analysis" run={() => api.stereo(fileId, range.start, range.end)} />
      <SimpleAudio title="Repetition / pattern autocorrelation" run={() => api.pattern(fileId, 0)} />
    </div>
  );
}

function AdvCard({ title, run, plot, note }: any) {
  const [d, setD] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    setError(null);
    try {
      setD(await run());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  const tr = d && plot(d);
  return (
    <Section title={title}>
      <button className="btn btn-accent mb-2" onClick={go} disabled={busy}>
        {busy ? "…" : "Analyse"}
      </button>
      <ErrorBox error={error} />
      {d && (
        <>
          {note && <div className="text-xs text-gray-400 mb-1">{note(d)}</div>}
          {tr && <Plot data={[{ ...tr, type: "scattergl", mode: "lines", line: { color: "#4f9dff", width: 1 } }]} height={220} />}
          {d.note && <div className="text-xs text-gray-500 mt-1">{d.note}</div>}
        </>
      )}
    </Section>
  );
}

function SimpleAudio({ title, run }: any) {
  const [d, setD] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  async function go() {
    setError(null);
    try {
      setD(await run());
    } catch (e: any) {
      setError(e.message);
    }
  }
  return (
    <Section title={title}>
      <button className="btn btn-accent mb-2" onClick={go}>
        Analyse
      </button>
      <ErrorBox error={error} />
      {d && <Json data={d} />}
    </Section>
  );
}

function DecodersTab({ fileId, range }: any) {
  return (
    <div className="grid lg:grid-cols-3 gap-4">
      <DecoderCard title="DTMF" run={() => api.dtmf(fileId, range.start, range.end)} field="sequence" />
      <DecoderCard title="Morse" run={() => api.morse(fileId, range.start, range.end)} field="text" extra="morse" />
      <DecoderCard title="SSTV (VIS detect)" run={() => api.sstv(fileId)} field={null} />
    </div>
  );
}

function DecoderCard({ title, run, field, extra }: any) {
  const [d, setD] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  async function go() {
    setBusy(true);
    setError(null);
    try {
      setD(await run());
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Section title={title}>
      <button className="btn btn-accent mb-2" onClick={go} disabled={busy}>
        {busy ? "…" : "Decode"}
      </button>
      <ErrorBox error={error} />
      {d && (
        <div>
          {field && (
            <div className="mono text-good bg-good/10 rounded px-2 py-2 mb-2 break-all">
              {d[field] || <span className="text-gray-500">(nothing decoded)</span>}
            </div>
          )}
          {extra && d[extra] && <div className="mono text-xs text-gray-400 break-all mb-2">{d[extra]}</div>}
          <Json data={d} />
        </div>
      )}
    </Section>
  );
}
