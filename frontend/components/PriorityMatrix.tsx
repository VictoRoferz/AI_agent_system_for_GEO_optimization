"use client";

import {
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
   ZAxis,
} from "recharts";
import type { Recommendation } from "@/lib/api";

const EFFORT_X: Record<string, number> = { low: 1, medium: 2, high: 3 };
const PRIORITY_FILL: Record<string, string> = {
  P0: "#b91c1c",
  P1: "#ea580c",
  P2: "#ca8a04",
  P3: "#0f766e",
};

export default function PriorityMatrix({ recs }: { recs: Recommendation[] }) {
  const data = recs.map((r) => ({
    x: EFFORT_X[r.effort] ?? 2,
    y: r.impact_score,
    z: 120,
    title: r.title,
    priority: r.priority,
    rank: r.priority_rank,
  }));

  return (
    <div className="card p-5">
      <h3 className="section-title mb-3">Impact vs. effort</h3>
      <ResponsiveContainer width="100%" height={300}>
        <ScatterChart margin={{ top: 10, right: 20, bottom: 30, left: 10 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#eef2f7" />
          <XAxis
            type="number"
            dataKey="x"
            name="Effort"
            domain={[0.5, 3.5]}
            ticks={[1, 2, 3]}
            tickFormatter={(v) => ({ 1: "Low", 2: "Medium", 3: "High" }[v as number] || "")}
            label={{ value: "Effort", position: "bottom", offset: 10, fill: "#94a3b8" }}
            stroke="#cbd5e1"
          />
          <YAxis
            type="number"
            dataKey="y"
            name="Impact"
            domain={[0, 5.5]}
            ticks={[1, 2, 3, 4, 5]}
            label={{ value: "Impact", angle: -90, position: "left", fill: "#94a3b8" }}
            stroke="#cbd5e1"
          />
          <ZAxis dataKey="z" range={[120, 121]} />
          <Tooltip
            cursor={{ strokeDasharray: "3 3" }}
            content={({ payload }) => {
              if (!payload?.length) return null;
              const d = payload[0].payload;
              return (
                <div className="rounded-md border border-slate-200 bg-white px-3 py-2 text-xs shadow">
                  <div className="font-semibold">#{d.rank} · {d.priority}</div>
                  <div className="max-w-[200px]">{d.title}</div>
                </div>
              );
            }}
          />
          <Scatter data={data}>
            {data.map((d, i) => (
              <Cell key={i} fill={PRIORITY_FILL[d.priority] || "#0f766e"} />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
      <p className="text-xs text-slate-400 text-center">
        Top-left = high impact, low effort (do first).
      </p>
    </div>
  );
}
