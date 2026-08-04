import { useEffect, useRef, useState } from "react";
import { sendMessage } from "../api.js";
import MessageBubble from "./MessageBubble.jsx";
import SuggestedQuestions from "./SuggestedQuestions.jsx";

export default function ChatWindow() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const endRef = useRef(null);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, busy]);

  async function ask(text) {
    const question = text.trim();
    if (!question || busy) return;

    setError(null);
    setInput("");
    const history = messages;
    setMessages([...history, { role: "user", content: question }]);
    setBusy(true);

    try {
      const reply = await sendMessage(question, history);
      setMessages((m) => [
        ...m,
        {
          role: "assistant",
          content: reply.answer,
          citations: reply.citations,
          chart_data: reply.chart_data,
          map_data: reply.map_data,
          verified: reply.verified,
        },
      ]);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex-1 space-y-4 overflow-y-auto px-4 py-6 sm:px-6">
        {messages.length === 0 && (
          <div className="mx-auto max-w-xl pt-6 text-center">
            <h2 className="text-lg font-semibold text-slate-800">
              Ask about groundwater in Punjab
            </h2>
            <p className="mt-1.5 text-sm text-slate-500">
              Answers come from CGWB monitoring data — 1,607 stations, 36,879
              readings from 1996 to 2024 — and every figure is checked against
              that data before you see it.
            </p>
          </div>
        )}

        {messages.map((m, i) => (
          <MessageBubble key={i} message={m} />
        ))}

        {busy && (
          <div className="flex items-center gap-2 text-sm text-slate-500">
            <span className="h-2 w-2 animate-pulse rounded-full bg-depth-600" />
            Retrieving data and checking the answer&hellip;
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        )}

        <div ref={endRef} />
      </div>

      <div className="border-t border-stone-200 bg-stone-50 px-4 py-4 sm:px-6">
        {messages.length === 0 && (
          <div className="mb-3">
            <SuggestedQuestions onPick={ask} disabled={busy} />
          </div>
        )}

        <form
          onSubmit={(e) => {
            e.preventDefault();
            ask(input);
          }}
          className="flex gap-2"
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="e.g. How fast is the water table falling in Sangrur?"
            disabled={busy}
            className="flex-1 rounded-lg border border-stone-300 bg-white px-4 py-2.5 text-sm
                       outline-none focus:border-depth-600 focus:ring-1 focus:ring-depth-600
                       disabled:opacity-60"
          />
          <button
            type="submit"
            disabled={busy || !input.trim()}
            className="rounded-lg bg-depth-700 px-5 py-2.5 text-sm font-medium text-white
                       transition hover:bg-depth-900 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Ask
          </button>
        </form>
      </div>
    </div>
  );
}
