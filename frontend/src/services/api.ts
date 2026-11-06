import type { FileInfo, Job, ScanResult, ToolInfo } from "../types";

const BASE = "/api";

async function jreq<T>(path: string, opts: RequestInit = {}): Promise<T> {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || JSON.stringify(body);
    } catch {
      /* ignore */
    }
    throw new ApiError(detail, res.status);
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

const get = <T,>(p: string) => jreq<T>(p);
const post = <T,>(p: string, body?: unknown) =>
  jreq<T>(p, { method: "POST", body: body ? JSON.stringify(body) : undefined });
const del = <T,>(p: string) => jreq<T>(p, { method: "DELETE" });

export const api = {
  // system
  tools: () => get<{ tools: ToolInfo[] }>("/system/tools"),
  health: () => get<{ status: string; version: string }>("/system/health"),

  // files
  async upload(file: File): Promise<FileInfo> {
    const fd = new FormData();
    fd.append("file", file);
    const res = await fetch(BASE + "/files/upload", { method: "POST", body: fd });
    if (!res.ok) throw new ApiError((await res.json()).detail || "upload failed", res.status);
    return res.json();
  },
  listFiles: () => get<FileInfo[]>("/files"),
  getFile: (id: string) => get<FileInfo>(`/files/${id}`),
  deleteFile: (id: string) => del<{ deleted: boolean }>(`/files/${id}`),
  hex: (id: string, offset = 0, length = 4096) =>
    get<{ offset: number; length: number; total: number; rows: any[]; base64: string }>(
      `/files/${id}/hex?offset=${offset}&length=${length}`,
    ),
  strings: (id: string, minLen = 4) =>
    get<{ strings: { offset: number; text: string }[] }>(`/files/${id}/strings?min_len=${minLen}`),
  rawUrl: (id: string) => `${BASE}/files/${id}/raw`,
  downloadUrl: (id: string) => `${BASE}/files/${id}/download`,

  // jobs
  job: (id: string) => get<Job>(`/jobs/${id}`),
  jobResult: <T,>(id: string) => get<T>(`/jobs/${id}/result`),
  cancelJob: (id: string) => post(`/jobs/${id}/cancel`),

  // image
  imageLsb: (body: any) => post<any>("/image/lsb", body),
  imageLsbSave: (body: any) => post<any>("/image/lsb/save", body),
  bitplaneOverview: (id: string) => get<any>(`/image/bitplanes/overview/${id}`),
  bitplane: (id: string, channel: string, bit: number, invert = false) =>
    get<any>(`/image/bitplanes/plane/${id}?channel=${channel}&bit=${bit}&invert=${invert}`),
  histograms: (id: string) => get<any>(`/image/channels/histograms/${id}`),
  imageStats: (id: string) => get<any>(`/image/channels/statistics/${id}`),
  channelIsolate: (id: string, channel: string, grayscale = true) =>
    get<any>(`/image/channels/isolate/${id}?channel=${channel}&grayscale=${grayscale}`),
  imageTransform: (body: any) => post<any>("/image/channels/transform", body),
  channelDiff: (id: string, a: string, b: string, amplify = 1) =>
    get<any>(`/image/channels/difference/${id}?channel_a=${a}&channel_b=${b}&amplify=${amplify}`),
  imageFormat: (id: string) => get<any>(`/image/format/${id}`),
  zsteg: (id: string, all = true) => post<any>(`/image/tools/zsteg?file_id=${id}&all_methods=${all}`),
  zstegExtract: (id: string, method: string) =>
    post<any>(`/image/tools/zsteg/extract?file_id=${id}&method=${encodeURIComponent(method)}`),
  steghide: (id: string, pass = "") =>
    post<any>(`/image/tools/steghide?file_id=${id}&passphrase=${encodeURIComponent(pass)}`),
  stegseek: (id: string) => post<any>(`/image/tools/stegseek?file_id=${id}`),
  outguess: (id: string, key = "") =>
    post<any>(`/image/tools/outguess?file_id=${id}&key=${encodeURIComponent(key)}`),
  exiftool: (id: string) => post<any>(`/image/tools/exiftool?file_id=${id}`),
  binwalk: (id: string) => post<any>(`/image/tools/binwalk?file_id=${id}`),
  ocr: (id: string) => post<any>(`/image/tools/ocr?file_id=${id}`),

  // audio
  audioInfo: (id: string) => get<any>(`/audio/info/${id}`),
  waveform: (id: string, buckets = 2000, start?: number, end?: number) =>
    get<any>(`/audio/waveform/${id}?buckets=${buckets}${rng(start, end)}`),
  audioStats: (id: string, start?: number, end?: number) =>
    get<any>(`/audio/statistics/${id}?silence_db=-50${rng(start, end)}`),
  spectrogram: (body: any) => post<any>("/audio/spectrogram", body),
  fft: (id: string, channel = 0, start?: number, end?: number) =>
    get<any>(`/audio/fft/${id}?channel=${channel}${rng(start, end)}`),
  pcmLsb: (body: any) => post<any>("/audio/pcm-lsb", body),
  pcmLsbSave: (body: any) => post<any>("/audio/pcm-lsb/save", body),
  phase: (id: string, channel = 0, start?: number, end?: number) =>
    get<any>(`/audio/phase/${id}?channel=${channel}${rng(start, end)}`),
  echo: (id: string, channel = 0, start?: number, end?: number) =>
    get<any>(`/audio/echo/${id}?channel=${channel}${rng(start, end)}`),
  stereo: (id: string, start?: number, end?: number) =>
    get<any>(`/audio/stereo/${id}?${rng(start, end).slice(1)}`),
  zeroCrossing: (id: string, channel = 0) => get<any>(`/audio/zero-crossing/${id}?channel=${channel}`),
  pattern: (id: string, channel = 0) => get<any>(`/audio/pattern/${id}?channel=${channel}`),
  dtmf: (id: string, start?: number, end?: number) => get<any>(`/audio/dtmf/${id}?${rng(start, end).slice(1)}`),
  morse: (id: string, start?: number, end?: number) => get<any>(`/audio/morse/${id}?${rng(start, end).slice(1)}`),
  sstv: (id: string) => get<any>(`/audio/sstv/${id}`),
  exportSegment: (id: string, start?: number, end?: number, channel?: number) =>
    post<any>(
      `/audio/segment/export?file_id=${id}${rng(start, end)}${channel != null ? `&channel=${channel}` : ""}`,
    ),
  audioSteghide: (id: string, pass = "") =>
    post<any>(`/audio/tools/steghide?file_id=${id}&passphrase=${encodeURIComponent(pass)}`),
  audioStegseek: (id: string) => post<any>(`/audio/tools/stegseek?file_id=${id}`),

  // video
  videoInfo: (id: string) => get<any>(`/video/info/${id}`),
  framesExtract: (body: any) => post<{ job_id: string }>("/video/frames/extract", body),
  listFrameset: (id: string, fs: string) => get<any>(`/video/frames/${id}/${fs}`),
  frameImage: (id: string, fs: string, name: string) =>
    get<any>(`/video/frames/${id}/${fs}/image/${name}`),
  sendFrameToImage: (body: any) => post<any>("/video/frames/send-to-image", body),
  framesetDiff: (id: string, fs: string) => get<any>(`/video/frames/${id}/${fs}/diff`),
  contactSheet: (id: string, cols = 5, rows = 5) =>
    get<any>(`/video/contact-sheet/${id}?cols=${cols}&rows=${rows}`),
  extractVideoAudio: (id: string, stream = 0) =>
    post<any>(`/video/audio/extract?file_id=${id}&stream=${stream}`),

  // extraction
  analyse: (id: string) => get<any>(`/extraction/analyse/${id}`),
  signaturesScan: (id: string) => get<any>(`/extraction/signatures/${id}`),
  trailing: (id: string) => get<any>(`/extraction/trailing/${id}`),
  carve: (body: any) => post<any>("/extraction/carve", body),
  carveAuto: (id: string) => post<any>(`/extraction/carve-auto/${id}`),
  archiveList: (id: string) => get<any>(`/extraction/archive/${id}`),
  archiveExtract: (body: any) => post<any>("/extraction/archive/extract", body),
  recursive: (id: string) => get<any>(`/extraction/recursive/${id}`),

  // smart scan
  smartScan: (id: string, depth: string) => post<{ job_id: string }>("/smart-scan", { file_id: id, depth }),
};

function rng(start?: number, end?: number): string {
  let s = "";
  if (start != null) s += `&start=${start}`;
  if (end != null) s += `&end=${end}`;
  return s;
}

// Poll a job to completion.
export async function pollJob<T>(jobId: string, onProgress?: (j: Job) => void, intervalMs = 600): Promise<T> {
  for (;;) {
    const j = await api.job(jobId);
    onProgress?.(j);
    if (j.status === "done") return api.jobResult<T>(jobId);
    if (j.status === "error") throw new ApiError(j.error || "job failed", 500);
    if (j.status === "cancelled") throw new ApiError("job cancelled", 499);
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}
