"use client";

// A dependency-free "brain of moving points" — nodes twinkle and the cluster gently
// breathes, symbolizing an active AI engine. Pure SVG + CSS keyframes (see globals.css),
// disabled automatically under prefers-reduced-motion.

// Brain-ish node cluster (viewBox 0 0 24 24).
const NODES: [number, number][] = [
  [7, 7], [12, 5], [17, 8],
  [5, 12], [12, 11], [19, 13],
  [8, 17], [14, 17], [11, 20],
];
const LINKS: [number, number][] = [
  [0, 1], [1, 2], [0, 3], [1, 4], [2, 5],
  [3, 4], [4, 5], [3, 6], [4, 7], [5, 7],
  [6, 8], [7, 8],
];

export default function BrainPoints({
  size = 18,
  color = "currentColor",
  className = "",
}: {
  size?: number;
  color?: string;
  className?: string;
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      aria-hidden="true"
    >
      <g className="geo-brain-group" stroke={color} fill={color}>
        {LINKS.map(([a, b], i) => (
          <line
            key={`l${i}`}
            x1={NODES[a][0]}
            y1={NODES[a][1]}
            x2={NODES[b][0]}
            y2={NODES[b][1]}
            strokeWidth={0.6}
            className="geo-brain-link"
            style={{ animationDelay: `${(i % 6) * 0.25}s`, opacity: 0.5 }}
          />
        ))}
        {NODES.map(([x, y], i) => (
          <circle
            key={`n${i}`}
            cx={x}
            cy={y}
            r={1.5}
            className="geo-brain-node"
            style={{ animationDelay: `${(i % 5) * 0.3}s` }}
          />
        ))}
      </g>
    </svg>
  );
}
