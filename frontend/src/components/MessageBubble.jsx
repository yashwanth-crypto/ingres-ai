import MapView from "./MapView.jsx";
import TrendChart from "./TrendChart.jsx";

export default function MessageBubble({ message }) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="message-in flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-depth-700 px-4 py-2.5 text-white shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  return (
    <div className="message-in max-w-[92%]">
      <div className="rounded-2xl rounded-bl-sm border border-stone-200 bg-white px-4 py-3">
        <p className="whitespace-pre-wrap leading-relaxed">{message.content}</p>

        {message.citations?.length > 0 && (
          <div className="mt-3 border-t border-stone-100 pt-2">
            {message.source && (
              <span
                className={`mb-1.5 inline-block rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${
                  message.source === "report"
                    ? "bg-amber-100 text-amber-800"
                    : "bg-depth-100 text-depth-700"
                }`}
                title={
                  message.source === "report"
                    ? "Answered from CGWB's published report"
                    : "Answered from the monitoring database"
                }
              >
                {message.source === "report" ? "CGWB report" : "Monitoring data"}
              </span>
            )}
            <ul>
              {message.citations.map((c, i) => (
                <li key={i} className="text-xs text-slate-500">
                  <span className="text-slate-400">[{i + 1}]</span> {c.station}
                  {c.date ? `, ${c.date}` : ""}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* An unverified answer is shown, but never presented as trustworthy. */}
        {message.verified === false && (
          <p className="mt-3 rounded border border-amber-200 bg-amber-50 px-2.5 py-1.5 text-xs text-amber-900">
            Could not be verified against the source data — the figures above
            are shown raw rather than summarised.
          </p>
        )}
      </div>

      {message.chart_data && <TrendChart data={message.chart_data} />}
      {message.map_data && <MapView data={message.map_data} />}
    </div>
  );
}
