import React, { useState } from "react";
export { humanSize } from "../lib/format";

export function Spinner({ label }: { label?: string }) {
  return (
    <span className="inline-flex items-center gap-2 text-gray-400">
      <span className="inline-block w-3 h-3 border-2 border-gray-500 border-t-accent rounded-full animate-spin" />
      {label}
    </span>
  );
}

export function Section({ title, right, children, defaultOpen = true }: {
  title: string; right?: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className="card mb-4">
      <div className="flex items-center justify-between px-4 py-2 border-b border-edge">
        <button className="flex items-center gap-2 text-sm font-medium" onClick={() => setOpen((o) => !o)}>
          <span className="text-gray-500 text-xs">{open ? "▼" : "▶"}</span>
          {title}
        </button>
        <div className="flex items-center gap-2">{right}</div>
      </div>
      {open && <div className="p-4">{children}</div>}
    </div>
  );
}

export function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="label">{label}</span>
      {children}
    </label>
  );
}

export function KeyVal({ data }: { data: Record<string, any> }) {
  return (
    <div className="grid grid-cols-[auto,1fr] gap-x-4 gap-y-1 text-sm">
      {Object.entries(data).map(([k, v]) => (
        <React.Fragment key={k}>
          <span className="text-gray-400">{k}</span>
          <span className="mono break-all">{typeof v === "object" ? JSON.stringify(v) : String(v)}</span>
        </React.Fragment>
      ))}
    </div>
  );
}

export function Json({ data }: { data: unknown }) {
  return (
    <pre className="mono text-xs bg-base-700 rounded p-3 overflow-auto max-h-96 whitespace-pre-wrap break-all">
      {JSON.stringify(data, null, 2)}
    </pre>
  );
}

export function ErrorBox({ error }: { error: string | null }) {
  if (!error) return null;
  return <div className="bg-bad/10 border border-bad/40 text-bad rounded px-3 py-2 text-sm my-2">{error}</div>;
}

export function Badge({ tone = "default", children }: { tone?: "default" | "good" | "warn" | "bad"; children: React.ReactNode }) {
  const toneClass = { default: "", good: "text-good border-good/40", warn: "text-warn border-warn/40", bad: "text-bad border-bad/40" }[tone];
  return <span className={`chip ${toneClass}`}>{children}</span>;
}

