// The spec's demo script (Section 12), including the deliberately
// out-of-scope one so the fallback is one click away.
const SUGGESTIONS = [
  "What's the groundwater status in Bathinda?",
  "Which districts in Punjab are over-exploited?",
  "How many years until Ludhiana hits critical depth at the current rate?",
  "What's the groundwater status in Mumbai?",
];

export default function SuggestedQuestions({ onPick, disabled }) {
  return (
    <div className="flex flex-wrap gap-2">
      {SUGGESTIONS.map((q) => (
        <button
          key={q}
          type="button"
          onClick={() => onPick(q)}
          disabled={disabled}
          className="rounded-full border border-stone-300 bg-white px-3.5 py-1.5 text-sm text-slate-700
                     transition hover:border-depth-600 hover:text-depth-700
                     disabled:cursor-not-allowed disabled:opacity-50"
        >
          {q}
        </button>
      ))}
    </div>
  );
}
