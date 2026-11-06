import { Link } from "react-router-dom";
import { useStore } from "../store";
import { FileUpload } from "../components/FileUpload";
import { FileBar } from "../components/FileBar";
import { Section, KeyVal, Badge, humanSize } from "../components/ui";
import { SmartScanPanel } from "../components/SmartScanPanel";

const MODULE_LINK: Record<string, { to: string; label: string }> = {
  image_lsb: { to: "/image", label: "Image LSB" },
  image_bitplanes: { to: "/image", label: "Bitplanes" },
  image_channels: { to: "/image", label: "Channels" },
  image_format: { to: "/image", label: "Format parser" },
  image_tools: { to: "/image", label: "zsteg/steghide" },
  audio_waveform: { to: "/audio", label: "Waveform" },
  audio_spectrogram: { to: "/audio", label: "Spectrogram" },
  audio_fft: { to: "/audio", label: "FFT" },
  audio_pcm_lsb: { to: "/audio", label: "PCM LSB" },
  audio_advanced: { to: "/audio", label: "Advanced audio" },
  audio_decoders: { to: "/audio", label: "DTMF/Morse" },
  video_info: { to: "/video", label: "Video info" },
  video_frames: { to: "/video", label: "Frames" },
  video_audio: { to: "/video", label: "Video audio" },
  extraction: { to: "/results", label: "Extraction" },
};

export default function Dashboard() {
  const { files, current, tools } = useStore();
  const cur = current();

  if (!files.length) {
    return (
      <div className="max-w-2xl mx-auto mt-10">
        <h1 className="text-xl mb-1">Upload a file to begin</h1>
        <p className="text-gray-500 text-sm mb-6">
          STEGO LAB analyses images, audio and video for hidden data. All processing is local — nothing
          is uploaded to third-party services.
        </p>
        <FileUpload />
        <ToolStatus tools={tools} className="mt-6" />
      </div>
    );
  }

  return (
    <div>
      <FileBar />
      {cur && (
        <div className="grid lg:grid-cols-2 gap-4">
          <div>
            <Section title="File detection">
              <KeyVal
                data={{
                  "Detected format": `${cur.detection.format} (${(cur.detection.confidence * 100).toFixed(0)}% confidence)`,
                  "Media type": cur.media_type,
                  Description: cur.detection.description,
                  "Reported name": cur.name,
                  Size: humanSize(cur.size),
                  MIME: cur.mime,
                  SHA256: cur.sha256,
                }}
              />
              <div className="mt-3">
                <div className="label mb-1">Suggested analysis</div>
                <div className="flex gap-2 flex-wrap">
                  {cur.detection.applicable_modules.map((m) => {
                    const link = MODULE_LINK[m];
                    return link ? (
                      <Link key={m} to={link.to} className="chip border-accent-dim text-accent hover:bg-accent/10">
                        {link.label}
                      </Link>
                    ) : null;
                  })}
                </div>
              </div>
            </Section>
            <ToolStatus tools={tools} />
          </div>
          <Section title="Smart Scan">
            <p className="text-xs text-gray-500 mb-3">
              Runs the techniques that apply to this file, tests a bounded set of extraction
              configurations, and ranks findings with transparent, explained scores.
            </p>
            <SmartScanPanel fileId={cur.id} />
          </Section>
        </div>
      )}
    </div>
  );
}

function ToolStatus({ tools, className = "" }: { tools: any[]; className?: string }) {
  return (
    <div className={`card p-4 ${className}`}>
      <div className="label mb-2">External tools</div>
      <div className="grid sm:grid-cols-2 gap-x-6 gap-y-1 text-sm">
        {tools.map((t) => (
          <div key={t.name} className="flex items-center gap-2" title={t.available ? t.path : t.install_hint}>
            <span className={t.available ? "text-good" : "text-gray-600"}>{t.available ? "●" : "○"}</span>
            <span className={t.available ? "" : "text-gray-500"}>{t.name}</span>
            {!t.available && <span className="text-xs text-gray-600">— {t.install_hint}</span>}
          </div>
        ))}
      </div>
    </div>
  );
}
