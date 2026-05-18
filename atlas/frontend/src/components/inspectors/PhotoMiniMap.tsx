import { type EdgePhoto } from "@/lib/api";

interface Props {
  photos: EdgePhoto[];
  /** Height in px. Defaults to 140 (matches the mockup). */
  height?: number;
}

/**
 * Tiny SVG preview of an edge's photo polyline. Plots GPS-bearing photos as
 * numbered dots in walk order, connected by a line — the same shape that
 * `acceptSuggestion` would write into the edge geometry on approve.
 *
 * SVG-only (no map tiles). Coordinates are scaled to fit the canvas with a
 * small margin, so the mini-map shows the relative path — not a geographically
 * accurate position. That matches the mockup at docs/30-editor-redesign-mockup.html
 * and avoids pulling in a leaflet instance for what is essentially decoration.
 */
export function PhotoMiniMap({ photos, height = 140 }: Props) {
  const gpsPoints = photos
    .map((p, i) => ({ p, i }))
    .filter(({ p }) => p.lat != null && p.lng != null) as { p: EdgePhoto; i: number }[];

  if (gpsPoints.length === 0) {
    return (
      <div
        className="flex items-center justify-center bg-paper-2 border border-hairline rounded-sm ff-mono text-[10.5px] text-slate-2 italic"
        style={{ height }}
      >
        No GPS points yet — upload phone photos to draw the path.
      </div>
    );
  }

  // Project lat/lng into SVG-local coords with a 14px margin. Single-point
  // case: center it without scaling.
  const PAD = 14;
  const W = 320;
  const H = height;
  const lats = gpsPoints.map(({ p }) => p.lat as number);
  const lngs = gpsPoints.map(({ p }) => p.lng as number);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);
  const latSpan = maxLat - minLat || 1;
  const lngSpan = maxLng - minLng || 1;
  const project = (lat: number, lng: number) => {
    const x = PAD + ((lng - minLng) / lngSpan) * (W - 2 * PAD);
    // Flip Y so north is up.
    const y = PAD + (1 - (lat - minLat) / latSpan) * (H - 2 * PAD);
    return { x, y };
  };

  const projected = gpsPoints.map(({ p, i }) => ({ ...project(p.lat as number, p.lng as number), i }));
  const linePath = projected
    .map((pt, idx) => `${idx === 0 ? "M" : "L"} ${pt.x.toFixed(1)} ${pt.y.toFixed(1)}`)
    .join(" ");

  return (
    <div
      className="relative bg-paper-2 border border-hairline rounded-sm overflow-hidden"
      style={{ height }}
    >
      <svg
        viewBox={`0 0 ${W} ${H}`}
        preserveAspectRatio="xMidYMid meet"
        className="w-full h-full block"
      >
        {/* faint grid for visual anchor */}
        <defs>
          <pattern id="mini-grid" width="24" height="24" patternUnits="userSpaceOnUse">
            <path d="M 24 0 L 0 0 0 24" fill="none" stroke="rgba(123,107,82,0.10)" strokeWidth="1" />
          </pattern>
        </defs>
        <rect width={W} height={H} fill="url(#mini-grid)" />

        {projected.length > 1 && (
          <path
            d={linePath}
            fill="none"
            stroke="#516B53"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        )}

        {projected.map((pt) => (
          <g key={pt.i}>
            <circle cx={pt.x} cy={pt.y} r="6" fill="#516B53" stroke="#F7F3EC" strokeWidth="2" />
            <text
              x={pt.x}
              y={pt.y - 10}
              textAnchor="middle"
              fontFamily="ui-monospace, Menlo, monospace"
              fontSize="9"
              fill="#516B53"
            >
              {pt.i + 1}
            </text>
          </g>
        ))}
      </svg>
      <span className="absolute bottom-1.5 right-2 ff-mono text-[9.5px] tracking-wide-2 text-slate-2 bg-paper/90 px-1.5 rounded">
        {projected.length} GPS · relative
      </span>
    </div>
  );
}
