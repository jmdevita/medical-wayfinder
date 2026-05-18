import type { FacilityMeta } from "@/lib/types";
import { TYPE_COLOR } from "@/lib/topology-meta";

export function MiniMap({ data, className }: { data: FacilityMeta["miniMap"]; className?: string }) {
  const { nodes, edges } = data;
  return (
    <svg viewBox="0 0 100 60" className={className} preserveAspectRatio="xMidYMid slice">
      <defs>
        <pattern id="dots-mini" width="4" height="4" patternUnits="userSpaceOnUse">
          <circle cx="0.5" cy="0.5" r="0.4" fill="#D9D2C2" />
        </pattern>
      </defs>
      <rect width="100" height="60" fill="#EDE6D2" />
      <rect width="100" height="60" fill="url(#dots-mini)" opacity="0.7" />

      <g transform="translate(88,8)" opacity="0.5">
        <line x1="0" y1="-3" x2="0" y2="3" stroke="#B8B2A4" strokeWidth="0.4" />
        <line x1="-3" y1="0" x2="3" y2="0" stroke="#B8B2A4" strokeWidth="0.4" />
        <text x="0" y="-3.5" fontSize="2.5" fill="#928D82" textAnchor="middle" fontFamily="Geist Mono">
          N
        </text>
      </g>

      <g opacity="0.5">
        <rect x="22" y="16" width="14" height="10" fill="#E5DCC4" stroke="#D9D2C2" strokeWidth="0.3" />
        <rect x="44" y="22" width="12" height="10" fill="#E5DCC4" stroke="#D9D2C2" strokeWidth="0.3" />
        <rect x="62" y="14" width="14" height="14" fill="#E5DCC4" stroke="#D9D2C2" strokeWidth="0.3" />
        <rect x="56" y="40" width="18" height="10" fill="#E5DCC4" stroke="#D9D2C2" strokeWidth="0.3" />
      </g>

      {edges.map(([a, b], i) => (
        <line
          key={i}
          x1={nodes[a].x}
          y1={nodes[a].y}
          x2={nodes[b].x}
          y2={nodes[b].y}
          stroke="#3A352E"
          strokeWidth="0.6"
          strokeLinecap="round"
          opacity="0.7"
        />
      ))}

      {nodes.map((n, i) => (
        <g key={i}>
          <circle cx={n.x} cy={n.y} r="2.4" fill="#F4EFE5" />
          <circle cx={n.x} cy={n.y} r="1.6" fill={TYPE_COLOR[n.t]} />
        </g>
      ))}
    </svg>
  );
}
