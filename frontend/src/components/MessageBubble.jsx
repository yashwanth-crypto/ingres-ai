import MapView from "./MapView.jsx";
import RankChart from "./RankChart.jsx";
import TrendChart from "./TrendChart.jsx";

/**
 * One message.
 *
 * The footer carries the part that makes this different from a chatbot: what
 * the answer was checked against, and what it came from. Previously a verified
 * answer said nothing at all about being verified — the whole claim of the
 * system was invisible on every answer that upheld it, and only a failure was
 * ever announced.
 */
export default function MessageBubble({ message }) {
  if (message.role === "user") {
    return (
      <div className="message-in flex justify-end">
        <div className="max-w-[85%] rounded-2xl rounded-br-sm bg-depth-700 px-4 py-2.5 text-white shadow-sm">
          {message.content}
        </div>
      </div>
    );
  }

  const citations = message.citations ?? [];
  const checked = message.verified === true;
  const failed = message.verified === false;
  // Out-of-scope replies carry no verdict and nothing to cite; a footer there
  // would be an empty grey band under a one-line refusal.
  const hasFooter = checked || failed || citations.length > 0;

  return (
    <div className="message-in max-w-[92%]">
      <div className="overflow-hidden rounded-2xl rounded-bl-sm border border-stone-200 bg-white">
        <p className="whitespace-pre-wrap px-4 py-3 leading-relaxed">
          {message.content}
        </p>

        {hasFooter && (
          <footer className="border-t border-stone-100 bg-stone-50 px-4 py-2.5">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1.5">
              {checked && (
                <Pill tone="checked" icon={<CheckIcon />}>
                  Every figure checked against the source
                </Pill>
              )}
              {failed && (
                <Pill tone="failed" icon={<AlertIcon />}>
                  Could not be verified
                </Pill>
              )}
              {message.source && (
                <Pill tone="source">
                  {message.source === "report"
                    ? "CGWB report"
                    : "Monitoring database"}
                </Pill>
              )}
            </div>

            {failed && (
              <p className="mt-2 text-[11px] leading-relaxed text-amber-800">
                The figures above are shown raw rather than summarised, because
                the wording could not be checked against the source data.
              </p>
            )}

            {citations.length > 0 && (
              <ol className="mt-2 space-y-1">
                {citations.map((c, i) => (
                  <li
                    key={`${c.station}-${c.date}-${i}`}
                    className="flex flex-wrap items-baseline gap-x-2 text-[11px] leading-snug"
                  >
                    <span className="tabular-nums text-slate-400">
                      [{i + 1}]
                    </span>
                    <span className="text-slate-600">{c.station}</span>
                    {c.date && (
                      <span className="tabular-nums text-slate-400">
                        {c.date}
                      </span>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </footer>
        )}
      </div>

      {message.chart_data?.type === "bars" ? (
        <RankChart data={message.chart_data} />
      ) : (
        message.chart_data && <TrendChart data={message.chart_data} />
      )}
      {message.map_data && <MapView data={message.map_data} />}
    </div>
  );
}

const TONES = {
  checked: "bg-depth-100 text-depth-700",
  failed: "bg-amber-100 text-amber-900",
  source: "bg-stone-200 text-slate-600",
};

function Pill({ tone, icon, children }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium uppercase tracking-wide ${TONES[tone]}`}
    >
      {icon}
      {children}
    </span>
  );
}

/* Inline SVG, like everything else here: no icon font to fail to load. */
function CheckIcon() {
  return (
    <svg viewBox="0 0 12 12" className="h-2.5 w-2.5" aria-hidden="true">
      <path
        d="M1.5 6.5 4.5 9.5 10.5 2.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function AlertIcon() {
  return (
    <svg viewBox="0 0 12 12" className="h-2.5 w-2.5" aria-hidden="true">
      <path
        d="M6 1.5 11 10.5H1z"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <path
        d="M6 5v2.2"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
      />
      <circle cx="6" cy="9" r="0.6" fill="currentColor" />
    </svg>
  );
}
