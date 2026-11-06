import { create } from "zustand";
import type { FileInfo, ToolInfo } from "./types";
import { api } from "./services/api";

interface State {
  files: FileInfo[];
  currentId: string | null;
  tools: ToolInfo[];
  loading: boolean;
  refreshFiles: () => Promise<void>;
  refreshTools: () => Promise<void>;
  setCurrent: (id: string | null) => void;
  current: () => FileInfo | undefined;
  addFile: (f: FileInfo) => void;
  removeFile: (id: string) => Promise<void>;
}

export const useStore = create<State>((set, get) => ({
  files: [],
  currentId: null,
  tools: [],
  loading: false,
  refreshFiles: async () => {
    const files = await api.listFiles();
    set({ files });
    if (!get().currentId && files.length) set({ currentId: files[0].id });
  },
  refreshTools: async () => {
    try {
      const { tools } = await api.tools();
      set({ tools });
    } catch {
      /* ignore */
    }
  },
  setCurrent: (id) => set({ currentId: id }),
  current: () => get().files.find((f) => f.id === get().currentId),
  addFile: (f) => set((s) => ({ files: [f, ...s.files.filter((x) => x.id !== f.id)], currentId: f.id })),
  removeFile: async (id) => {
    await api.deleteFile(id);
    set((s) => {
      const files = s.files.filter((f) => f.id !== id);
      const currentId = s.currentId === id ? files[0]?.id ?? null : s.currentId;
      return { files, currentId };
    });
  },
}));
