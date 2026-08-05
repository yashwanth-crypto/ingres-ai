import { useEffect } from "react";
import {
  CircleMarker,
  MapContainer,
  Popup,
  TileLayer,
  useMap,
} from "react-leaflet";

/**
 * Leaflet measures its container once, at mount. Here the container is still
 * settling at that moment - the message list grows as the answer renders and
 * the view re-pins to the bottom - so the map computed its pixel origin from a
 * wrong size and drew Punjab's tiles as though they were somewhere else
 * entirely (Gujarat, in practice), with tiles spilling past the frame.
 *
 * Re-measuring after the layout settles fixes both, and fitting to the actual
 * points frames the districts properly instead of trusting a fixed zoom.
 */
function FitToPoints({ points }) {
  const map = useMap();

  useEffect(() => {
    const bounds = points.map((p) => [p.latitude, p.longitude]);
    const settle = () => {
      map.invalidateSize();
      if (bounds.length === 1) {
        map.setView(bounds[0], 9);
      } else if (bounds.length > 1) {
        map.fitBounds(bounds, { padding: [28, 28] });
      }
    };
    // Immediately, then after the message and its tiles have finished laying out.
    settle();
    const timers = [80, 350, 900].map((d) => setTimeout(settle, d));
    window.addEventListener("resize", settle);
    return () => {
      timers.forEach(clearTimeout);
      window.removeEventListener("resize", settle);
    };
  }, [map, points]);

  return null;
}

// CGWB assessment categories, worst to best.
const CATEGORY_COLOR = {
  "over-exploited": "#b91c1c",
  critical: "#ea580c",
  "semi-critical": "#d97706",
  safe: "#15803d",
};

export default function MapView({ data }) {
  const points = data?.points ?? [];
  if (!points.length) return null;

  // Centre on the points we actually have rather than a hardcoded coordinate.
  const centre = [
    points.reduce((s, p) => s + p.latitude, 0) / points.length,
    points.reduce((s, p) => s + p.longitude, 0) / points.length,
  ];

  const shown = [...new Set(points.map((p) => p.category))].filter(Boolean);

  return (
    <figure className="mt-3 overflow-hidden rounded-lg border border-stone-200 bg-white">
      <div className="border-b border-stone-200 px-4 py-3">
        <h3 className="text-sm font-semibold text-slate-800">
          {points.length} district{points.length > 1 ? "s" : ""}
        </h3>
        <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1">
          {shown.map((c) => (
            <span key={c} className="flex items-center gap-1.5 text-xs text-slate-600">
              <span
                className="inline-block h-2.5 w-2.5 rounded-full"
                style={{ background: CATEGORY_COLOR[c] ?? "#78716c" }}
              />
              {c}
            </span>
          ))}
        </div>
      </div>

      <MapContainer
        center={centre}
        zoom={7}
        scrollWheelZoom={false}
        style={{ height: 320, width: "100%" }}
      >
        <FitToPoints points={points} />
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        {points.map((p) => (
          <CircleMarker
            key={p.district}
            center={[p.latitude, p.longitude]}
            radius={9}
            pathOptions={{
              color: "#fff",
              weight: 2,
              fillColor: CATEGORY_COLOR[p.category] ?? "#78716c",
              fillOpacity: 0.85,
            }}
          >
            <Popup>
              <strong>{p.district}</strong>
              <br />
              {p.category ?? "no category"}
            </Popup>
          </CircleMarker>
        ))}
      </MapContainer>

      <p className="px-4 py-2 text-[11px] text-slate-400">
        Marker position is the mean of the district&rsquo;s monitoring stations.
        Categories from CGWB 2024.
        {data.not_plotted?.length > 0 && (
          <>
            {" "}
            <span className="text-slate-500">
              {data.not_plotted.join(", ")} {data.not_plotted.length > 1 ? "are" : "is"}{" "}
              categorised but not shown — no monitoring stations there.
            </span>
          </>
        )}
      </p>
    </figure>
  );
}
