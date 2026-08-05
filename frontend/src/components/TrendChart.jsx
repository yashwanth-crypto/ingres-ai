import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ReferenceArea,
  ReferenceDot,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/**
 * Depth to water over time, drawn as a cross-section rather than a line chart.
 *
 * The Y axis is REVERSED: a larger depth means a deeper water table, so
 * plotting it downward makes a falling line read as a falling water table.
 * Everything above the line is then unsaturated ground, so it is filled with
 * the same earth tones AquiferHero uses — the chart and the landing page are
 * describing the same physical thing and should look like it.
 *
 * When the answer projected forward, the projection is drawn dashed into a
 * shaded future region, ending on a marked crossing of the reference depth.
 * The headline figure of a "how many years until…" answer is a point on a
 * chart, and stating it only in prose wasted it.
 */
export default function TrendChart({ data }) {
  if (!data?.series?.length) return null;

  const projection = data.projection ?? null;
  const forward = projection?.series ?? [];

  // One row per year carrying both keys, so the two lines meet at the anchor
  // instead of being drawn over separate, silently misaligned x-domains.
  const byYear = new Map();
  for (const d of data.series) {
    byYear.set(d.year, {
      year: d.year,
      mean_depth_m: d.mean_depth_m,
      readings: d.readings,
    });
  }
  for (const p of forward) {
    byYear.set(p.year, {
      ...(byYear.get(p.year) ?? { year: p.year }),
      projected_depth_m: p.projected_depth_m,
    });
  }
  const rows = [...byYear.values()].sort((a, b) => a.year - b.year);

  // The reference depth is included so its line is never off-canvas.
  const depths = [
    ...data.series.map((d) => d.mean_depth_m),
    ...forward.map((p) => p.projected_depth_m),
    ...(projection ? [projection.reference_depth_m] : []),
  ];
  const pad = Math.max(1, (Math.max(...depths) - Math.min(...depths)) * 0.15);
  const yMin = Math.max(0, Math.floor(Math.min(...depths) - pad));
  const yMax = Math.ceil(Math.max(...depths) + pad);

  // Recharts left to itself produced ticks at 13 / 21 / 34 — three of them, at
  // uneven intervals. Depths are read by comparison, so the steps must be even.
  const yStep = yMax - yMin > 40 ? 10 : 5;
  const yTicks = [];
  for (let v = Math.ceil(yMin / yStep) * yStep; v <= yMax; v += yStep) {
    yTicks.push(v);
  }

  const years = rows.map((r) => r.year);
  const xMin = Math.min(...years);
  const xMax = Math.ceil(Math.max(...years));
  const xTicks = [];
  for (let y = Math.ceil(xMin / 10) * 10; y <= xMax; y += 10) xTicks.push(y);

  const lastMeasured = data.series[data.series.length - 1].year;

  // Recharts animates in JavaScript, so the reduced-motion rule in index.css
  // does not reach it. Read the preference directly instead.
  const stillness =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;

  return (
    <figure className="mt-3 overflow-hidden rounded-lg border border-stone-200 bg-white">
      <figcaption className="border-b border-stone-100 px-4 pb-3 pt-4">
        <h3 className="font-display text-base leading-tight text-depth-900">
          {data.district} — depth to water
        </h3>
        <p className="mt-0.5 text-xs text-slate-500">{data.note}</p>

        <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1.5">
          <Key swatch={<span className="h-0.5 w-5 bg-depth-700" />}>
            Measured, {data.series[0].year}–{lastMeasured}
          </Key>
          {forward.length > 0 && (
            <Key
              swatch={
                <span
                  className="h-0 w-5 border-t-2 border-dashed"
                  style={{ borderColor: "#b45309" }}
                />
              }
            >
              Projected at current rate
            </Key>
          )}
        </div>
      </figcaption>

      <div className="px-2 pt-3">
        <ResponsiveContainer width="100%" height={260}>
          <ComposedChart
            data={rows}
            margin={{ top: 8, right: 14, bottom: 4, left: 4 }}
          >
            <defs>
              {/* Unsaturated ground above the water table, in AquiferHero's
                  strata tones. Kept translucent so gridlines stay readable. */}
              <linearGradient id="tc-earth" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#c9b79a" stopOpacity={0.30} />
                <stop offset="100%" stopColor="#a08a6d" stopOpacity={0.55} />
              </linearGradient>
            </defs>

            <CartesianGrid stroke="#e7e5e4" strokeDasharray="3 3" />

            {/* The future is shaded rather than left to the reader to infer
                from a dash pattern they have to hunt for in a caption. */}
            {forward.length > 0 && (
              <ReferenceArea
                x1={lastMeasured}
                x2={xMax}
                fill="#78716c"
                fillOpacity={0.06}
                label={{
                  value: "projected",
                  position: "insideTop",
                  style: {
                    fontSize: 10,
                    fill: "#a8a29e",
                    textTransform: "uppercase",
                    letterSpacing: "0.08em",
                  },
                }}
              />
            )}

            <XAxis
              dataKey="year"
              // Numeric, not categorical: the projection ends on a fractional
              // year, and a category axis would space it as one even step.
              type="number"
              domain={[xMin, xMax]}
              ticks={xTicks}
              allowDecimals={false}
              tick={{ fontSize: 11, fill: "#78716c" }}
              tickLine={false}
              stroke="#d6d3d1"
            />
            <YAxis
              reversed
              domain={[yMin, yMax]}
              ticks={yTicks}
              allowDecimals={false}
              tick={{ fontSize: 11, fill: "#78716c" }}
              tickLine={false}
              // 56px and a positive left margin: at width 44 the rotated label
              // was placed at x = -3 and rendered outside the SVG as a sliver.
              width={56}
              stroke="#d6d3d1"
              label={{
                value: "metres below ground",
                angle: -90,
                position: "insideLeft",
                style: { fontSize: 10, fill: "#78716c", textAnchor: "middle" },
              }}
            />

            <Tooltip
              cursor={{ stroke: "#a8a29e", strokeDasharray: "3 3" }}
              contentStyle={{
                fontSize: 12,
                borderRadius: 8,
                border: "1px solid #e7e5e4",
                boxShadow: "0 4px 12px rgb(0 0 0 / 0.06)",
              }}
              formatter={(v, name, p) =>
                name === "projected_depth_m"
                  ? [`${v} m — projected`, ""]
                  : [`${v} m`, `${p.payload.readings} readings`]
              }
              labelFormatter={(y) => `${Math.round(y)}`}
            />

            {projection && (
              <ReferenceLine
                y={projection.reference_depth_m}
                stroke="#b45309"
                strokeDasharray="4 4"
                label={{
                  value: `${projection.reference_depth_m} m reference depth`,
                  // Left-anchored: at insideBottomRight this label sat on top
                  // of the projection line's final approach.
                  position: "insideTopLeft",
                  style: { fontSize: 10, fill: "#b45309" },
                }}
              />
            )}

            {/* Ground above the water table. tooltipType none, or every hover
                reports the same depth twice. */}
            <Area
              type="monotone"
              dataKey="mean_depth_m"
              baseValue={yMin}
              stroke="none"
              fill="url(#tc-earth)"
              connectNulls={false}
              tooltipType="none"
              isAnimationActive={!stillness}
            />

            <Line
              type="monotone"
              dataKey="mean_depth_m"
              stroke="#164e5b"
              strokeWidth={2}
              dot={false}
              activeDot={{ r: 4, fill: "#164e5b" }}
              connectNulls={false}
              isAnimationActive={!stillness}
            />
            {forward.length > 0 && (
              <Line
                type="linear"
                dataKey="projected_depth_m"
                stroke="#b45309"
                strokeWidth={2}
                strokeDasharray="5 4"
                dot={false}
                activeDot={{ r: 4, fill: "#b45309" }}
                connectNulls
                // Never animated: Recharts drives stroke-dasharray to run its
                // draw-on effect, which would fight the dash that distinguishes
                // a projection from a measurement. The dash carries meaning
                // here, so it is not negotiable for the sake of an entrance.
                isAnimationActive={false}
              />
            )}

            {/* The answer's headline: where and when the line crosses. */}
            {projection?.reaches_year && (
              <ReferenceDot
                x={projection.reaches_year}
                y={projection.reference_depth_m}
                r={4}
                fill="#b45309"
                stroke="#fff"
                strokeWidth={2}
                isFront
                label={{
                  value: `~${Math.round(projection.reaches_year)}`,
                  position: "top",
                  style: { fontSize: 11, fontWeight: 600, fill: "#b45309" },
                }}
              />
            )}
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      <div className="border-t border-stone-100 bg-stone-50 px-4 py-2.5">
        <p className="text-[11px] leading-relaxed text-slate-500">
          Axis inverted so a falling line means a falling water table. Source:
          CGWB National Hydrograph Network.
          {projection?.caveat ? ` ${projection.caveat}` : ""}
        </p>
      </div>
    </figure>
  );
}

function Key({ swatch, children }) {
  return (
    <span className="flex items-center gap-1.5 text-[11px] text-slate-600">
      {swatch}
      {children}
    </span>
  );
}
