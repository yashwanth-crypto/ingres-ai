import { useEffect, useState } from "react";
import { getHealth } from "./api.js";
import ChatWindow from "./components/ChatWindow.jsx";

export default function App() {
  const [health, setHealth] = useState(null);

  useEffect(() => {
    getHealth()
      .then(setHealth)
      .catch(() => setHealth({ status: "unreachable" }));
  }, []);

  const ok = health?.status === "ok";

  return (
    <div className="mx-auto flex h-screen max-w-3xl flex-col">
      <header className="flex items-center justify-between border-b border-stone-200 bg-white/70 px-4 py-3 backdrop-blur sm:px-6">
        <div className="flex items-center gap-2.5">
          {/* Wordmark: a wellhead over a water table. */}
          <svg viewBox="0 0 24 24" className="h-7 w-7 shrink-0" aria-hidden="true">
            <rect x="10.5" y="3" width="3" height="15" rx="1" fill="#164e5b" />
            <rect x="7.5" y="1.5" width="9" height="3" rx="1" fill="#0b2c34" />
            <path
              d="M1 15 Q5 13 9 15 T17 15 T23 15 L23 23 L1 23 Z"
              fill="#2b8fa3"
              opacity="0.85"
            />
            <path
              d="M1 15 Q5 13 9 15 T17 15 T23 15"
              fill="none"
              stroke="#7fd3e3"
              strokeWidth="1.2"
            />
          </svg>
          <div>
            <h1 className="font-display text-lg leading-none tracking-tight text-depth-900">
              INGRES
            </h1>
            <p className="mt-0.5 text-[11px] text-slate-500">
              Punjab groundwater, grounded in CGWB data
            </p>
          </div>
        </div>

        <div
          className="flex items-center gap-1.5 text-xs text-slate-500"
          title={
            health
              ? `database ${health.db_connected ? "connected" : "down"} · model ${health.llm_backend ?? "?"}`
              : "checking"
          }
        >
          <span
            className={`inline-block h-2 w-2 rounded-full ${
              ok ? "bg-emerald-500" : health ? "bg-red-500" : "bg-stone-300"
            }`}
          />
          {health?.llm_backend?.split(":")[0] ?? "connecting"}
        </div>
      </header>

      <main className="min-h-0 flex-1">
        <ChatWindow />
      </main>
    </div>
  );
}
