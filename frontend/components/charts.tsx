"use client";

import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Scatter,
  ScatterChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { COMPONENT_LABEL } from "@/lib/format";
import type { TornadoBar, Uncertainty } from "@/lib/types";

const AXIS = { fill: "var(--muted)", fontSize: 11 };
const TOOLTIP_STYLE = {
  backgroundColor: "var(--panel)",
  border: "1px solid var(--border)",
  borderRadius: 6,
  fontSize: 12,
};

export function ComponentBars({
  components,
  excluded,
}: {
  components: Record<string, number | null>;
  excluded?: string[];
}) {
  const data = Object.entries(components)
    .filter(([, value]) => value !== null)
    .map(([key, value]) => ({
      name: COMPONENT_LABEL[key] ?? key,
      value: value as number,
      delta: (value as number) - 50,
    }));
  return (
    <div>
      <ResponsiveContainer width="100%" height={data.length * 34 + 30}>
        <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
          <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" horizontal={false} />
          <XAxis type="number" domain={[0, 100]} tick={AXIS} />
          <YAxis type="category" dataKey="name" width={110} tick={AXIS} />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            formatter={(v) => [`${Number(v).toFixed(1)} / 100`, "score"]}
          />
          <ReferenceLine x={50} stroke="var(--muted)" strokeDasharray="4 4" />
          <Bar dataKey="value" radius={[0, 4, 4, 0]} barSize={16}>
            {data.map((entry) => (
              <Cell
                key={entry.name}
                fill={entry.delta >= 0 ? "var(--pass)" : "var(--fail)"}
                fillOpacity={0.85}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {excluded && excluded.length > 0 && (
        <p className="mt-1 text-[11px] text-unavail">
          Excluded (data unavailable, weights renormalized): {excluded.join(", ")}
        </p>
      )}
    </div>
  );
}

export function TornadoChart({ bars }: { bars: TornadoBar[] }) {
  const data = bars.map((bar) => ({
    name: COMPONENT_LABEL[bar.component] ?? bar.component,
    range: [bar.utility_low, bar.utility_high],
    base: bar.base,
  }));
  if (data.length === 0) return null;
  const base = data[0].base;
  return (
    <ResponsiveContainer width="100%" height={data.length * 32 + 30}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" horizontal={false} />
        <XAxis type="number" domain={["auto", "auto"]} tick={AXIS} />
        <YAxis type="category" dataKey="name" width={110} tick={AXIS} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(v) =>
            Array.isArray(v) ? [`${v[0].toFixed(1)} – ${v[1].toFixed(1)}`, "utility range"] : [v, ""]
          }
        />
        <ReferenceLine x={base} stroke="var(--accent)" strokeDasharray="4 4" />
        <Bar dataKey="range" fill="var(--accent)" fillOpacity={0.6} radius={4} barSize={14} />
      </BarChart>
    </ResponsiveContainer>
  );
}

export function UncertaintyStrip({ u }: { u: Uncertainty }) {
  const min = Math.min(u.p10, -1);
  const max = Math.max(u.p90, 1);
  const span = max - min || 1;
  const toPct = (x: number) => ((x - min) / span) * 100;
  return (
    <div>
      <div className="relative h-6 rounded-full bg-panel2">
        <div
          className="absolute top-1 bottom-1 rounded-full bg-accent/30"
          style={{ left: `${toPct(u.p10)}%`, width: `${toPct(u.p90) - toPct(u.p10)}%` }}
        />
        <div
          className="absolute top-0 bottom-0 w-0.5 bg-accent"
          style={{ left: `${toPct(u.median)}%` }}
        />
        <div
          className="absolute top-0 bottom-0 w-px bg-muted/60"
          style={{ left: `${toPct(0)}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-muted">
        <span>
          p10 {u.p10 >= 0 ? "+" : ""}
          {u.p10.toFixed(1)} wins
        </span>
        <span className="text-foreground">
          median {u.median >= 0 ? "+" : ""}
          {u.median.toFixed(1)} wins · P(positive) {(u.prob_positive * 100).toFixed(0)}%
        </span>
        <span>
          p90 {u.p90 >= 0 ? "+" : ""}
          {u.p90.toFixed(1)} wins
        </span>
      </div>
    </div>
  );
}

export function ParetoScatter({
  points,
}: {
  points: {
    name: string;
    x: number;
    y: number;
    dominated: boolean;
  }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <ScatterChart margin={{ left: 8, right: 16, top: 10, bottom: 10 }}>
        <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
        <XAxis
          type="number"
          dataKey="x"
          name="Performance"
          tick={AXIS}
          label={{ value: "Performance score", position: "insideBottom", offset: -6, ...AXIS }}
        />
        <YAxis
          type="number"
          dataKey="y"
          name="Risk-adjusted"
          tick={AXIS}
          label={{ value: "Risk-adjusted score", angle: -90, position: "insideLeft", ...AXIS }}
        />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(value, name) => [Number(value).toFixed(1), name]}
          labelFormatter={() => ""}
        />
        <Scatter data={points}>
          {points.map((p) => (
            <Cell
              key={p.name}
              fill={p.dominated ? "var(--unavail)" : "var(--pass)"}
              fillOpacity={p.dominated ? 0.5 : 0.95}
            />
          ))}
        </Scatter>
      </ScatterChart>
    </ResponsiveContainer>
  );
}

export function FirstPlaceShareBars({
  share,
  names,
}: {
  share: Record<string, number>;
  names: Record<string, string>;
}) {
  const data = Object.entries(share)
    .map(([id, value]) => ({ name: names[id] ?? id.slice(0, 8), value: value * 100 }))
    .sort((a, b) => b.value - a.value);
  return (
    <ResponsiveContainer width="100%" height={data.length * 34 + 30}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16 }}>
        <XAxis type="number" domain={[0, 100]} tick={AXIS} unit="%" />
        <YAxis type="category" dataKey="name" width={140} tick={AXIS} />
        <Tooltip
          contentStyle={TOOLTIP_STYLE}
          formatter={(v) => [`${Number(v).toFixed(1)}%`, "ranks #1"]}
        />
        <Bar dataKey="value" fill="var(--accent)" fillOpacity={0.8} radius={[0, 4, 4, 0]} barSize={16} />
      </BarChart>
    </ResponsiveContainer>
  );
}
