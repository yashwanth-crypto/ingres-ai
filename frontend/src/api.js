// In dev, Vite proxies /api to the backend so there is no cross-origin
// request. In production this is the deployed backend URL.
const BASE = import.meta.env.VITE_API_URL || "/api";

function body(message, history) {
  return JSON.stringify({
    message,
    // The backend only reads role and content.
    history: history.map(({ role, content }) => ({ role, content })),
  });
}

export async function sendMessage(message, history = []) {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body(message, history),
  });

  if (!res.ok) {
    throw new Error(`Backend returned ${res.status}. Is the API running?`);
  }
  return res.json();
}

/**
 * The same answer, with the pipeline reporting each step as it reaches it.
 *
 * `onStage` is called for every stage; the finished answer is returned. Falls
 * back to the plain endpoint if the browser gives us no readable stream, so a
 * missing feature costs the progress display and not the answer.
 */
export async function streamMessage(message, history = [], onStage = () => {}) {
  const res = await fetch(`${BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: body(message, history),
  });

  if (!res.ok) {
    throw new Error(`Backend returned ${res.status}. Is the API running?`);
  }
  if (!res.body?.getReader) return sendMessage(message, history);

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let answer = null;

  const consume = (chunk) => {
    const line = chunk.split("\n").find((l) => l.startsWith("data: "));
    if (!line) return;
    const payload = JSON.parse(line.slice(6));
    if (payload.stage === "done") answer = payload.result;
    else onStage(payload);
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    // Events are separated by a blank line. A chunk can split one anywhere, so
    // only whole events are consumed and the remainder stays in the buffer.
    const events = buffer.split("\n\n");
    buffer = events.pop() ?? "";
    events.forEach(consume);
  }

  // Whatever is left when the stream closes. The server ends every event with
  // a blank line, so this is normally empty - but losing the answer because
  // the last chunk arrived without its terminator would be a miserable bug to
  // find, and the cost of not having it is one parse.
  buffer += decoder.decode();
  if (buffer.trim()) consume(buffer);

  if (!answer) throw new Error("The answer stream ended before the answer did.");
  return answer;
}

export async function getHealth() {
  const res = await fetch(`${BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed (${res.status})`);
  return res.json();
}
