import { useState } from "react";
import { api, pollJob } from "../services/api";
import type { Job, ScanResult } from "../types";
import { ErrorBox, Spinner, Badge } from "./ui";

export function SmartScanPanel({ fileId }: { fileId: string }) {
  const [depth, setDepth] = useState("standard");
  const [job, setJob] = useState<Job | null>(null);
  const [result, setResult] = useState<ScanResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);

  async function run() {
    setRunning(true);
    setError(null);
    setResult(null);
    try {
      const { job_id } = await api.smartScan(fileId, depth);
      const res = await pollJob<ScanResult>(job_id, setJob);
      setResult(res);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setRunning(false);
    }
  }

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <select className="input" value={depth} onChange={(e) => setDepth(e.target.value)} disabled={running}>
          <option value="quick">Quick scan</option>
          <option value="standard">Standard scan</option>
          <option value="deep">Deep scan</option>
        </select>
        <button className="btn btn-accent" onClick={run} disabled={running}>
          {running ? "Scanning…" : "Run Smart Scan"}
        </button>
        {running && job && (
          <span className="text-xs text-gray-400">
            <Spinner /> {Math.round(job.progress * 100)}% — {job.message}
          </span>
        )}
      </div>
      <ErrorBox error={error} />
      {result && (
        <div>
          <div className="text-sm text-gray-400 mb-2">
            {result.finding_count} finding(s) · {result.stored_payloads.length} payload(s) recovered
          </div>
          <div className="space-y-2">
            {result.findings.map((f, i) => (
              <div key={i} className="card p-3">
                <div className="flex items-center gap-2">
                  <span className={`font-mono font-bold ${f.score >= 50 ? "text-good" : f.score >= 25 ? "text-warn" : "text-gray-400"}`}>
                    {f.score}
                  </span>
                  <span className="font-medium">{f.title}</span>
                  <Badge>{f.method}</Badge>
                  {f.file_id && <Badge tone="good">payload saved</Badge>}
                </div>
                <ul className="mt-1 text-xs text-gray-400 list-disc ml-5">
                  {f.reasons.map((r, j) => (
                    <li key={j}>{r}</li>
                  ))}
                </ul>
                {f.file_id && (
                  <div className="mt-1 flex gap-2 text-xs">
                    <a className="btn btn-xs" href={api.downloadUrl(f.file_id)} target="_blank" rel="noreferrer">
                      Download payload
                    </a>
                    <span className="text-gray-500 self-center">→ see Results tab to re-analyse</span>
                  </div>
                )}
              </div>
            ))}
            {result.finding_count === 0 && (
              <div className="text-gray-500 text-sm">
                No strong findings at this depth. Try a deeper scan or the manual tools.
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
