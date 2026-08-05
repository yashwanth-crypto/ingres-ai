import { useEffect, useState } from "react";

/**
 * Animated cross-section of the aquifer.
 *
 * The whole product is about depth below ground, and nothing else in the
 * interface shows that physically. The water table descends at Punjab's real
 * median rate and the wells chase it down, which is the story in one image.
 *
 * Pure inline SVG and CSS: no external assets, so it works with no internet.
 */

const STRATA = [
  { y: 96, h: 46, fill: "#c9b79a" },
  { y: 142, h: 58, fill: "#b8a184" },
  { y: 200, h: 64, fill: "#a08a6d" },
  { y: 264, h: 96, fill: "#8a755a" },
];

// Depth gridlines, in metres, mapped onto the section.
const MARKS = [
  { m: 0, y: 96 },
  { m: 15, y: 168 },
  { m: 30, y: 240 },
  { m: 45, y: 312 },
];

function useCountUp(target, duration = 1400) {
  const [value, setValue] = useState(0);

  useEffect(() => {
    const reduced = window.matchMedia?.(
      "(prefers-reduced-motion: reduce)",
    )?.matches;
    if (reduced) {
      setValue(target);
      return;
    }

    let frame;
    const start = performance.now();
    const tick = (now) => {
      const p = Math.min(1, (now - start) / duration);
      // Ease-out so the number settles rather than stopping dead.
      setValue(Math.round(target * (1 - Math.pow(1 - p, 3))));
      if (p < 1) frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);

    // requestAnimationFrame is paused in a hidden or backgrounded tab, which
    // would leave the headline figures stuck at zero. Snap to the real value
    // regardless - a timer keeps running when frames do not.
    const settle = setTimeout(() => setValue(target), duration + 150);

    return () => {
      cancelAnimationFrame(frame);
      clearTimeout(settle);
    };
  }, [target, duration]);

  return value;
}

function Stat({ value, label, suffix = "" }) {
  const shown = useCountUp(value);
  return (
    <div>
      <div className="font-display text-2xl leading-none text-depth-900 sm:text-3xl">
        {shown.toLocaleString()}
        {suffix}
      </div>
      <div className="mt-1 text-[11px] uppercase tracking-wider text-slate-500">
        {label}
      </div>
    </div>
  );
}

export default function AquiferHero({ onPick, disabled }) {
  const prompts = [
    { q: "What's the groundwater status in Bathinda?", tag: "Monitoring data" },
    { q: "Which districts in Punjab are over-exploited?", tag: "Map" },
    {
      q: "How many years until Ludhiana hits critical depth at the current rate?",
      tag: "Projection",
    },
    { q: "Is the water in Bathinda safe to drink?", tag: "CGWB report" },
  ];

  return (
    <div className="px-4 pb-4 pt-6 sm:px-6">
      <section className="overflow-hidden rounded-2xl border border-stone-200 bg-white shadow-sm">
        {/* ---------- cross-section ---------- */}
        <div className="relative">
          <svg
            viewBox="0 0 800 360"
            className="block h-44 w-full sm:h-56"
            preserveAspectRatio="xMidYMid slice"
            role="img"
            aria-label="Cross-section of an aquifer with a falling water table"
          >
            <defs>
              <linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#eef6f7" />
                <stop offset="100%" stopColor="#dbeaec" />
              </linearGradient>
              <linearGradient id="water" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#2b8fa3" stopOpacity="0.95" />
                <stop offset="100%" stopColor="#0b2c34" stopOpacity="0.9" />
              </linearGradient>
              <clipPath id="section">
                <rect x="0" y="96" width="800" height="264" />
              </clipPath>
            </defs>

            <rect x="0" y="0" width="800" height="96" fill="url(#sky)" />
            {STRATA.map((s) => (
              <rect key={s.y} x="0" y={s.y} width="800" height={s.h} fill={s.fill} />
            ))}

            {/* grain: a few scattered specks read as soil without a texture file */}
            <g opacity="0.18" clipPath="url(#section)">
              {Array.from({ length: 90 }).map((_, i) => (
                <circle
                  key={i}
                  cx={(i * 137) % 800}
                  cy={100 + ((i * 71) % 250)}
                  r={(i % 3) * 0.7 + 0.6}
                  fill="#4a3a26"
                />
              ))}
            </g>

            {/* saturated zone, sinking */}
            <g clipPath="url(#section)" className="water-table">
              <path
                d="M0,150 Q100,140 200,150 T400,150 T600,150 T800,150 L800,360 L0,360 Z"
                fill="url(#water)"
              />
              <path
                d="M0,150 Q100,140 200,150 T400,150 T600,150 T800,150"
                fill="none"
                stroke="#7fd3e3"
                strokeWidth="2"
              />
            </g>

            {/* wells */}
            {[160, 400, 640].map((x, i) => (
              <g key={x}>
                <rect x={x - 4} y="76" width="8" height="220" fill="#3f3a34" rx="2" />
                <rect x={x - 13} y="66" width="26" height="12" rx="2" fill="#57504733" />
                <rect x={x - 13} y="66" width="26" height="12" rx="2" fill="#4b443c" />
                <circle
                  cx={x}
                  cy="72"
                  r="3"
                  fill="#7fd3e3"
                  className="well-pulse"
                  style={{ animationDelay: `${i * 0.9}s` }}
                />
              </g>
            ))}

            {/* ground line */}
            <line x1="0" y1="96" x2="800" y2="96" stroke="#6b5b45" strokeWidth="2" />

            {/* depth scale */}
            <g className="text-[10px]" fill="#ffffff" opacity="0.75">
              {MARKS.map((m) => (
                <g key={m.m}>
                  <line
                    x1="0"
                    y1={m.y}
                    x2="46"
                    y2={m.y}
                    stroke="#ffffff"
                    strokeOpacity="0.35"
                    strokeDasharray="3 4"
                  />
                  <text x="8" y={m.y - 5} fontSize="11" fill="#ffffff" opacity="0.8">
                    {m.m} m
                  </text>
                </g>
              ))}
            </g>
          </svg>

          <div className="pointer-events-none absolute inset-x-0 bottom-0 flex items-end justify-between px-4 pb-3 sm:px-6">
            <p className="rounded bg-black/35 px-2 py-1 text-[11px] text-white backdrop-blur-sm">
              Water table falling ~0.5 m per year
            </p>
            <p className="hidden rounded bg-black/35 px-2 py-1 text-[11px] text-white backdrop-blur-sm sm:block">
              CGWB National Hydrograph Network
            </p>
          </div>
        </div>

        {/* ---------- copy + stats ---------- */}
        <div className="px-5 py-5 sm:px-6">
          <h2 className="font-display text-xl leading-snug text-depth-900 sm:text-2xl">
            Punjab is drawing down its groundwater faster than it refills.
          </h2>
          <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-600">
            Ask a question in plain English. Every figure is checked against CGWB
            monitoring data before you see it — and if it cannot be verified, you
            are told so rather than shown a confident guess.
          </p>

          <div className="mt-5 grid grid-cols-2 gap-4 border-t border-stone-100 pt-4 sm:grid-cols-4">
            <Stat value={1607} label="Stations" />
            <Stat value={36879} label="Readings" />
            <Stat value={28} label="Years" suffix="" />
            <Stat value={20} label="of 23 over-exploited" />
          </div>
        </div>
      </section>

      {/* ---------- prompts ---------- */}
      <div className="mt-4 grid gap-2 sm:grid-cols-2">
        {prompts.map((p, i) => (
          <button
            key={p.q}
            type="button"
            onClick={() => onPick(p.q)}
            disabled={disabled}
            style={{ animationDelay: `${120 + i * 70}ms` }}
            className="fade-up group flex items-start gap-3 rounded-xl border border-stone-200 bg-white px-4 py-3
                       text-left transition hover:-translate-y-0.5 hover:border-depth-600 hover:shadow-md
                       disabled:cursor-not-allowed disabled:opacity-50"
          >
            <span className="mt-0.5 text-slate-300 transition group-hover:text-depth-600">
              &rarr;
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-sm text-slate-800">{p.q}</span>
              <span className="mt-1 block text-[10px] uppercase tracking-wider text-slate-400">
                {p.tag}
              </span>
            </span>
          </button>
        ))}
      </div>
    </div>
  );
}
