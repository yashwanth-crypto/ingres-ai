/**
 * What the pipeline is doing, while it does it.
 *
 * Answering takes 3 to 15 seconds and the interface spent all of it showing
 * three bouncing dots. The work is the interesting part of this system —
 * retrieval, a projection, seven checks over every figure — and none of it was
 * visible. Each line is a real step with a real count attached.
 *
 * Stages arrive in pairs: an announcement, then its result. The result
 * replaces the announcement in place rather than adding a line, so the list
 * stays as short as the pipeline is deep.
 */

// Which in-progress line each arriving stage finishes off. Later entries in a
// list are older fallbacks, for the paths that skip a step.
const COMPLETES = {
  understood: ["understanding"],
  retrieved: ["retrieving"],
  calculated: ["calculating"],
  checking: ["drafting"],
  rewriting: ["checking"],
  verified: ["checking", "rewriting", "drafting"],
  rejected: ["checking", "rewriting", "drafting"],
  unusable: ["drafting"],
};

// Stages that are an outcome rather than an announcement.
const SETTLED = new Set([
  "understood",
  "retrieved",
  "calculated",
  "verified",
  "rejected",
  "unusable",
]);

const TROUBLE = new Set(["rejected", "unusable"]);

/** Fold one event into the list of steps. Pure, so it is testable. */
export function foldStage(steps, event) {
  const step = {
    key: event.stage,
    label: event.label,
    detail: event.detail || "",
    done: SETTLED.has(event.stage),
    trouble: TROUBLE.has(event.stage),
  };

  for (const key of COMPLETES[event.stage] ?? []) {
    const i = steps.findIndex((s) => s.key === key && !s.done);
    if (i !== -1) {
      const next = [...steps];
      next[i] = step;
      return next;
    }
  }
  return [...steps, step];
}

export default function PipelineProgress({ steps }) {
  if (!steps.length) return null;

  return (
    <ol className="space-y-1.5" aria-live="polite">
      {steps.map((s, i) => (
        <li key={`${s.key}-${i}`} className="flex items-start gap-2 text-sm">
          <span className="mt-[3px] flex h-3.5 w-3.5 shrink-0 items-center justify-center">
            {s.done ? (
              <CheckIcon trouble={s.trouble} />
            ) : (
              <span className="flex gap-[3px]">
                {[0, 1, 2].map((d) => (
                  <span
                    key={d}
                    className="dot inline-block h-1 w-1 rounded-full bg-depth-600"
                    style={{ animationDelay: `${d * 0.15}s` }}
                  />
                ))}
              </span>
            )}
          </span>
          <span className="leading-snug">
            <span className={s.trouble ? "text-amber-800" : "text-slate-600"}>
              {s.label}
            </span>
            {s.detail && (
              <span className="text-slate-400"> — {s.detail}</span>
            )}
          </span>
        </li>
      ))}
    </ol>
  );
}

function CheckIcon({ trouble }) {
  return (
    <svg
      viewBox="0 0 12 12"
      className={`h-3 w-3 ${trouble ? "text-amber-600" : "text-depth-600"}`}
      aria-hidden="true"
    >
      {trouble ? (
        <>
          <path
            d="M6 1.8 11 10.4H1z"
            fill="none"
            stroke="currentColor"
            strokeWidth="1.4"
            strokeLinejoin="round"
          />
          <path d="M6 5.2v2.1" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
        </>
      ) : (
        <path
          d="M1.5 6.5 4.5 9.5 10.5 2.5"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}
    </svg>
  );
}
