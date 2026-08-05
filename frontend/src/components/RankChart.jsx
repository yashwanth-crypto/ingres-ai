import { CATEGORY_ORDER, categoryColor } from "../categories.js";

/**
 * Districts side by side, worst first.
 *
 * Ranked and compared answers are about relative magnitude. Stated as prose
 * they make the reader hold eight numbers in their head and do the comparing;
 * as bars the comparison is the picture. Deliberately plain CSS rather than
 * Recharts: horizontal bars with a label, a value and a category colour are
 * laid out better by a grid than by a chart library, and the bundle is already
 * carrying Recharts and Leaflet.
 */
export default function RankChart({ data }) {
  const bars = data?.bars ?? [];
  if (!bars.length) return null;

  const max = Math.max(...bars.map((b) => Math.abs(b.value)));
  const unit = data.unit?.includes("/year") ? "m/yr" : "m";
  const shown = CATEGORY_ORDER.filter((c) => bars.some((b) => b.category === c));

  return (
    <figure className="mt-3 overflow-hidden rounded-lg border border-stone-200 bg-white">
      <figcaption className="border-b border-stone-100 px-4 pb-3 pt-4">
        <h3 className="font-display text-base leading-tight text-depth-900">
          {data.title}
        </h3>
        {data.note && (
          <p className="mt-0.5 text-xs text-slate-500">{data.note}</p>
        )}
        {shown.length > 0 && (
          <div className="mt-2.5 flex flex-wrap gap-x-4 gap-y-1.5">
            {shown.map((c) => (
              <span
                key={c}
                className="flex items-center gap-1.5 text-[11px] text-slate-600"
              >
                <span
                  className="inline-block h-2.5 w-2.5 rounded-sm"
                  style={{ background: categoryColor(c) }}
                />
                {c}
              </span>
            ))}
          </div>
        )}
      </figcaption>

      <ul className="px-4 py-3">
        {bars.map((bar) => {
          const isAnswer = data.highlight && bar.label === data.highlight;
          const width = max > 0 ? (Math.abs(bar.value) / max) * 100 : 0;
          return (
            <li
              key={bar.label}
              // Narrower label and value columns on a phone. At 375px the
              // full-width layout left the bar itself 70px against 192px of
              // text, which puts the least of the chart into the data.
              className="grid grid-cols-[4.5rem_1fr_auto] items-center gap-2.5 py-[3px] sm:grid-cols-[7rem_1fr_auto]"
            >
              {/* Wraps rather than truncates. Two of Punjab's districts are
                  "Sahibzada Ajit Singh Nagar" and "Shahid Bhagat Singh Nagar",
                  and clipping them mid-word in a chart about which district is
                  worst defeats the point of naming them. */}
              <span
                className={`text-right text-[11px] leading-tight ${
                  isAnswer ? "font-semibold text-depth-900" : "text-slate-600"
                }`}
              >
                {bar.label}
              </span>

              <span className="relative block h-5 rounded-sm bg-stone-100">
                <span
                  className="bar-grow absolute inset-y-0 left-0 rounded-sm"
                  style={{
                    width: `${width}%`,
                    background: categoryColor(bar.category),
                    // The answer to a superlative question is one bar among
                    // eight that look alike; without this it has to be found.
                    opacity: !data.highlight || isAnswer ? 1 : 0.55,
                  }}
                />
              </span>

              <span
                className={`w-14 text-right text-xs tabular-nums sm:w-20 ${
                  isAnswer ? "font-semibold text-depth-900" : "text-slate-500"
                }`}
              >
                {bar.value} {unit}
                {bar.stations ? (
                  // Supporting detail, not the figure. First thing to go when
                  // the row is competing for a phone's width.
                  <span className="ml-1 hidden text-[10px] text-slate-400 sm:inline">
                    ({bar.stations})
                  </span>
                ) : null}
              </span>
            </li>
          );
        })}
      </ul>

      <div className="border-t border-stone-100 bg-stone-50 px-4 py-2.5">
        <p className="text-[11px] leading-relaxed text-slate-500">
          {data.unit === "m/year"
            ? "Median of per-station trends. A larger value means a faster fall."
            : "Depth below ground at the latest reading. Larger means deeper."}
          {bars.some((b) => b.stations)
            ? " Bracketed figures are the stations behind each value."
            : ""}
          {data.unavailable?.length
            ? ` No monitoring data for ${data.unavailable.join(", ")}, so ${
                data.unavailable.length > 1 ? "they are" : "it is"
              } not plotted.`
            : ""}
        </p>
      </div>
    </figure>
  );
}
