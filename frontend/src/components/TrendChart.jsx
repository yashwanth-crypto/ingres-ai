import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

/**
 * Depth to water over time. The Y axis is REVERSED: a larger depth means a
 * deeper water table, so plotting it downward makes a falling line read as a
 * falling water table, which is what people expect.
 */
export default function TrendChart({ data }) {
  if (!data?.series?.length) return null;

  const depths = data.series.map((d) => d.mean_depth_m);
  const pad = Math.max(1, (Math.max(...depths) - Math.min(...depths)) * 0.15);

  return (
    <figure className="mt-3 rounded-lg border border-stone-200 bg-white p-4">
      <figcaption className="mb-3">
        <h3 className="text-sm font-semibold text-slate-800">
          {data.district} — depth to water
        </h3>
        <p className="text-xs text-slate-500">{data.note}</p>
      </figcaption>

      <ResponsiveContainer width="100%" height={220}>
        <LineChart
          data={data.series}
          margin={{ top: 4, right: 8, bottom: 4, left: -8 }}
        >
          <CartesianGrid stroke="#e7e5e4" strokeDasharray="3 3" />
          <XAxis
            dataKey="year"
            tick={{ fontSize: 11, fill: "#78716c" }}
            tickLine={false}
          />
          <YAxis
            reversed
            // Whole metres: Recharts otherwise labels ticks 10.3995 / 22.9105.
            domain={[
              Math.max(0, Math.floor(Math.min(...depths) - pad)),
              Math.ceil(Math.max(...depths) + pad),
            ]}
            allowDecimals={false}
            tick={{ fontSize: 11, fill: "#78716c" }}
            tickLine={false}
            width={44}
            label={{
              value: "m below ground",
              angle: -90,
              position: "insideLeft",
              style: { fontSize: 10, fill: "#78716c" },
            }}
          />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 6 }}
            formatter={(v, _n, p) => [
              `${v} m below ground`,
              `${p.payload.readings} readings`,
            ]}
            labelFormatter={(y) => `Year ${y}`}
          />
          <Line
            type="monotone"
            dataKey="mean_depth_m"
            stroke="#164e5b"
            strokeWidth={2}
            dot={{ r: 2 }}
            activeDot={{ r: 4 }}
          />
        </LineChart>
      </ResponsiveContainer>

      <p className="mt-2 text-[11px] text-slate-400">
        Axis inverted so a falling line means a falling water table. Source:
        CGWB National Hydrograph Network.
      </p>
    </figure>
  );
}
