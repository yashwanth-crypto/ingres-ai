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
      <header className="flex items-center justify-between border-b border-stone-200 px-4 py-3 sm:px-6">
        <div>
          <h1 className="font-semibold tracking-tight text-depth-900">
            INGRES
          </h1>
          <p className="text-xs text-slate-500">
            Punjab groundwater, grounded in CGWB data
          </p>
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
