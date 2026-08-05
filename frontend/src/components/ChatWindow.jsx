import { useEffect, useRef, useState } from "react";
import { sendMessage } from "../api.js";
import AquiferHero from "./AquiferHero.jsx";
import MessageBubble from "./MessageBubble.jsx";

export default function ChatWindow() {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const endRef = useRef(null);
  const scrollerRef = useRef(null);

  useEffect(() => {
    // Setting scrollTop directly rather than scrollIntoView({behavior:"smooth"}):
    // smooth scrolling is animation-driven and does nothing in a backgrounded
    // tab, which would leave the newest answer below the fold.
    const toEnd = () => {
      const el = scrollerRef.current;
      if (el) el.scrollTop = el.scrollHeight;
    };
    toEnd();
    // Charts and map tiles lay out after this effect runs and grow the message,
    // so re-pin once they have settled.
    const again = [setTimeout(toEnd, 260), setTimeout(toEnd, 900)];
    return () => again.forEach(clearTimeout);
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
          source: reply.source,
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
      <div ref={scrollerRef} className="flex-1 overflow-y-auto scroll-smooth">
        {messages.length === 0 ? (
          <AquiferHero onPick={ask} disabled={busy} />
        ) : (
          // Anchored to the bottom so a short conversation sits just above the
          // input instead of stranding it at the top of an empty page.
          <div className="flex min-h-full flex-col justify-end space-y-4 px-4 py-6 sm:px-6">
            {messages.map((m, i) => (
              <MessageBubble key={i} message={m} />
            ))}

            {busy && (
              <div className="flex items-center gap-2.5 text-sm text-slate-500">
                <span className="flex gap-1">
                  {[0, 1, 2].map((i) => (
                    <span
                      key={i}
                      className="dot inline-block h-1.5 w-1.5 rounded-full bg-depth-600"
                      style={{ animationDelay: `${i * 0.15}s` }}
                    />
                  ))}
                </span>
                Retrieving data and checking every figure&hellip;
              </div>
            )}
          </div>
        )}

        {error && (
          <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800">
            {error}
          </div>
        )}

        <div ref={endRef} />
      </div>

      <div className="border-t border-stone-200 bg-stone-50/80 px-4 py-4 backdrop-blur sm:px-6">
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
