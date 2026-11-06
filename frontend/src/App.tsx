import { useEffect } from "react";
import { NavLink, Navigate, Route, Routes } from "react-router-dom";
import { useStore } from "./store";
import Dashboard from "./pages/Dashboard";
import ImagePage from "./pages/ImagePage";
import AudioPage from "./pages/AudioPage";
import VideoPage from "./pages/VideoPage";
import ResultsPage from "./pages/ResultsPage";

const NAV = [
  { to: "/", label: "Dashboard", end: true },
  { to: "/image", label: "Image" },
  { to: "/audio", label: "Audio" },
  { to: "/video", label: "Video" },
  { to: "/results", label: "Results" },
];

export default function App() {
  const { refreshFiles, refreshTools, tools } = useStore();

  useEffect(() => {
    refreshFiles();
    refreshTools();
  }, [refreshFiles, refreshTools]);

  const missing = tools.filter((t) => !t.available);

  return (
    <div className="min-h-full flex flex-col">
      <header className="border-b border-edge bg-base-800 sticky top-0 z-10">
        <div className="flex items-center gap-6 px-4 h-12">
          <div className="font-semibold tracking-wide">
            <span className="text-accent">STEGO</span> LAB
          </div>
          <nav className="flex gap-1">
            {NAV.map((n) => (
              <NavLink
                key={n.to}
                to={n.to}
                end={n.end}
                className={({ isActive }) =>
                  `px-3 py-1.5 rounded text-sm ${isActive ? "bg-base-600 text-white" : "text-gray-400 hover:text-gray-200"}`
                }
              >
                {n.label}
              </NavLink>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3 text-xs text-gray-500">
            <span>
              tools: {tools.filter((t) => t.available).length}/{tools.length}
            </span>
            {missing.length > 0 && (
              <span className="text-warn" title={missing.map((m) => `${m.name}: ${m.install_hint}`).join("\n")}>
                {missing.length} missing
              </span>
            )}
          </div>
        </div>
      </header>
      <main className="flex-1 px-4 py-4 max-w-[1500px] w-full mx-auto">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/image" element={<ImagePage />} />
          <Route path="/audio" element={<AudioPage />} />
          <Route path="/video" element={<VideoPage />} />
          <Route path="/results" element={<ResultsPage />} />
          <Route path="*" element={<Navigate to="/" />} />
        </Routes>
      </main>
    </div>
  );
}
