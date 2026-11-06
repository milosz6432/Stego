import { useEffect, useState } from "react";
import { api } from "../services/api";
import type { HexRow } from "../types";
import { Spinner, humanSize } from "./ui";

export function HexViewer({ fileId }: { fileId: string }) {
  const [rows, setRows] = useState<HexRow[]>([]);
  const [offset, setOffset] = useState(0);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const pageSize = 2048;

  useEffect(() => {
    let active = true;
    setLoading(true);
    api.hex(fileId, offset, pageSize).then((r) => {
      if (!active) return;
      setRows(r.rows);
      setTotal(r.total);
      setLoading(false);
    });
    return () => {
      active = false;
    };
  }, [fileId, offset]);

  return (
    <div>
      <div className="flex items-center gap-2 mb-2 text-xs">
        <button className="btn btn-xs" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - pageSize))}>
          ◀ Prev
        </button>
        <span className="text-gray-400">
          offset 0x{offset.toString(16)} / {humanSize(total)}
        </span>
        <button className="btn btn-xs" disabled={offset + pageSize >= total} onClick={() => setOffset(offset + pageSize)}>
          Next ▶
        </button>
        {loading && <Spinner />}
      </div>
      <div className="mono text-xs bg-base-700 rounded p-2 overflow-auto max-h-[28rem] leading-5">
        {rows.map((r) => (
          <div key={r.offset} className="flex gap-4 whitespace-pre">
            <span className="text-accent-dim">{r.offset.toString(16).padStart(8, "0")}</span>
            <span className="text-gray-200">{r.hex.padEnd(47, " ")}</span>
            <span className="text-gray-400">{r.ascii}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
