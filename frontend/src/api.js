// In dev, Vite proxies /api to the backend so there is no cross-origin
// request. In production this is the deployed backend URL.
const BASE = import.meta.env.VITE_API_URL || "/api";

export async function sendMessage(message, history = []) {
  const res = await fetch(`${BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      // The backend only reads role and content.
      history: history.map(({ role, content }) => ({ role, content })),
    }),
  });

  if (!res.ok) {
    throw new Error(`Backend returned ${res.status}. Is the API running?`);
  }
  return res.json();
}

export async function getHealth() {
  const res = await fetch(`${BASE}/health`);
  if (!res.ok) throw new Error(`Health check failed (${res.status})`);
  return res.json();
}
