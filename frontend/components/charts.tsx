"use client";

/**
 * Chart layer.
 *
 * Every chart ships inside a ChartFrame, which enforces the four things the
 * product requires of a visualization: a title, the unit being measured, a
 * one-line reason it matters, and a text summary that carries the same
 * information to screen readers (charts are `aria-hidden`; the summary is not).
 */

import clsx from "clsx";
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

const AXIS = { fill: "var(--chalk-dim)", fontSize: 11, fontFamily: "var(--font-plex-mono)" };
const GRID = "var(--hairline)";
const TOOLTIP_STYLE = {
  backgroundColor: "var(--arena-raised)",
  border: "1px solid var(--hairline)",
  borderRadius: 8,
  fontSize: 12,
  fontFamily: "var(--font-archivo)",
  color: "var(--chalk)",
};

export function ChartFrame({
  title,
  unit,
  why,
  summary,
  children,
  className,
}: {
  title: string;
  /** What the axis measures, e.g. "score, 0–100 (50 = neutral)". */
  unit: string;
  /** One line on why a decision-maker should care. */
  why?: string;
  /** Text equivalent of the chart, announced to assistive tech. */
  summary: string;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <figure className={clsx("min-w-0", className)}>
      <figcaption className="mb-1.5">
        <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5">
          <span className="title-md text-foreground">{title}</span>
          <span className="eyebrow text-[0.5625rem]">{unit}</span>
        </div>
        {why && <p className="mt-0.5 text-[11px] leading-snug text-muted">{why}</p>}
      </figcaption>
      <div aria-hidden>{children}</div>
      <p className="sr-only">{summary}</p>
    </figure>
  );
}

/* ------------------------------------------------------- component profile */

export function ComponentBars({
  components,
  excluded,
  accent = "var(--signal)",
}: {
  components: Record<string, number | null>;
  excluded?: string[];
  accent?: string;
}) {
  const data = Object.entries(components)
    .filter(([, value]) => value !== null)
    .map(([key, value]) => ({
      name: COMPONENT_LABEL[key] ?? key,
      value: value as number,
      delta: (value as number) - 50,
    }));

  const summary = data
    .map((d) => `${d.name} ${d.value.toFixed(0)} of 100`)
    .join("; ");

  return (
    <ChartFrame
      title="Component scores"
      unit="score 0–100 · 50 = neutral"
      why="Where the deal actually helps or hurts, before any weighting is applied."
      summary={`${summary}.${excluded?.length ? ` Not scored for missing data: ${excluded.join(", ")}.` : ""}`}
    >
      <ResponsiveContainer width="100%" height={data.length * 32 + 26}>
        <BarChart data={data} layout="vertical" margin={{ left: 4, right: 12, top: 2, bottom: 2 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="2 4" horizontal={false} />
          <XAxis type="number" domain={[0, 100]} tick={AXIS} tickLine={false} axisLine={false} />
          <YAxis
            type="category"
            dataKey="name"
            width={124}
            tick={{ ...AXIS, fontFamily: "var(--font-archivo)" }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: "var(--arena-high)", opacity: 0.5 }}
            formatter={(value) => [`${Number(value).toFixed(1)} / 100`, "score"]}
          />
          <ReferenceLine x={50} stroke="var(--chalk-faint)" strokeDasharray="3 3" />
          <Bar dataKey="value" radius={[0, 3, 3, 0]} barSize={13}>
            {data.map((entry) => (
              <Cell
                key={entry.name}
                fill={entry.delta >= 0 ? accent : "var(--illegal)"}
                fillOpacity={0.9}
              />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
      {excluded && excluded.length > 0 && (
        <p className="mt-1 text-[11px] text-unavail">
          Not scored — data unavailable: {excluded.map((c) => COMPONENT_LABEL[c] ?? c).join(", ")}.
          Remaining weights were rescaled.
        </p>
      )}
    </ChartFrame>
  );
}

/* ----------------------------------------------------------- before/after */

export function BeforeAfterBars({
  rows,
  unit = "score 0–100",
  title = "Before vs after",
  why,
}: {
  rows: { name: string; before: number; after: number }[];
  unit?: string;
  title?: string;
  why?: string;
}) {
  const data = rows.map((r) => ({ ...r, delta: r.after - r.before }));
  return (
    <ChartFrame
      title={title}
      unit={unit}
      why={why}
      summary={data
        .map(
          (d) =>
            `${d.name}: ${d.before.toFixed(1)} before, ${d.after.toFixed(1)} after (${
              d.delta >= 0 ? "+" : ""
            }${d.delta.toFixed(1)})`,
        )
        .join("; ")}
    >
      <ResponsiveContainer width="100%" height={data.length * 38 + 30}>
        <BarChart data={data} layout="vertical" margin={{ left: 4, right: 12 }} barGap={2}>
          <CartesianGrid stroke={GRID} strokeDasharray="2 4" horizontal={false} />
          <XAxis type="number" tick={AXIS} tickLine={false} axisLine={false} />
          <YAxis
            type="category"
            dataKey="name"
            width={124}
            tick={{ ...AXIS, fontFamily: "var(--font-archivo)" }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip contentStyle={TOOLTIP_STYLE} cursor={{ fill: "var(--arena-high)", opacity: 0.5 }} />
          <Bar dataKey="before" name="Before" fill="var(--chalk-faint)" barSize={9} radius={[0, 2, 2, 0]} />
          <Bar dataKey="after" name="After" fill="var(--signal)" barSize={9} radius={[0, 2, 2, 0]} />
        </BarChart>
      </ResponsiveContainer>
      <p className="mt-1 flex items-center gap-3 text-[11px] text-muted">
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-sm bg-faint" aria-hidden /> before
        </span>
        <span className="flex items-center gap-1">
          <span className="h-2 w-2 rounded-sm bg-signal" aria-hidden /> after
        </span>
      </p>
    </ChartFrame>
  );
}

/* -------------------------------------------------------------- sensitivity */

export function TornadoChart({ bars }: { bars: TornadoBar[] }) {
  const data = bars.map((bar) => ({
    name: COMPONENT_LABEL[bar.component] ?? bar.component,
    range: [bar.utility_low, bar.utility_high] as [number, number],
    base: bar.base,
  }));
  if (data.length === 0) return null;
  const base = data[0].base;

  return (
    <ChartFrame
      title="Sensitivity to your priorities"
      unit="decision score 0–100"
      why="A wide bar means the verdict depends on how you weight that priority."
      summary={data
        .map((d) => `${d.name}: score moves between ${d.range[0].toFixed(1)} and ${d.range[1].toFixed(1)}`)
        .join("; ")}
    >
      <ResponsiveContainer width="100%" height={data.length * 30 + 26}>
        <BarChart data={data} layout="vertical" margin={{ left: 4, right: 12 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="2 4" horizontal={false} />
          <XAxis type="number" domain={["auto", "auto"]} tick={AXIS} tickLine={false} axisLine={false} />
          <YAxis
            type="category"
            dataKey="name"
            width={124}
            tick={{ ...AXIS, fontFamily: "var(--font-archivo)" }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: "var(--arena-high)", opacity: 0.5 }}
            formatter={(value) =>
              Array.isArray(value)
                ? [`${value[0].toFixed(1)} – ${value[1].toFixed(1)}`, "score range"]
                : [value, ""]
            }
          />
          <ReferenceLine x={base} stroke="var(--signal)" strokeDasharray="3 3" />
          <Bar dataKey="range" fill="var(--signal)" fillOpacity={0.45} radius={3} barSize={12} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/* -------------------------------------------------------------- uncertainty */

export function UncertaintyStrip({ u, compact = false }: { u: Uncertainty; compact?: boolean }) {
  const min = Math.min(u.p10, -1);
  const max = Math.max(u.p90, 1);
  const span = max - min || 1;
  const toPct = (x: number) => ((x - min) / span) * 100;
  const sign = (x: number) => `${x >= 0 ? "+" : ""}${x.toFixed(1)}`;

  // No players move → every draw is exactly zero, so there is no distribution and no
  // "chance it helps". Say that rather than rendering a 0% that reads as a prediction.
  if (u.prob_positive === null || u.prob_positive === undefined) {
    const message =
      u.unavailable ?? "no players move, so there is no outcome distribution";
    if (compact) return <p className="text-[11px] text-muted">Projected wins: {message}.</p>;
    return (
      <ChartFrame
        title="Projected wins impact"
        unit="unavailable"
        why="An empty deal has no outcome distribution; a 0 % here would read as a prediction."
        summary={`Projected wins impact is unavailable — ${message}.`}
      >
        <p className="rounded-md border border-hairline bg-panel3 px-3 py-4 text-sm text-muted">
          Not applicable — {message}.
        </p>
      </ChartFrame>
    );
  }
  const probPositive = u.prob_positive;

  const strip = (
    <div>
      <div className="relative h-7 overflow-hidden rounded-md border border-hairline bg-panel3">
        {/* zero line: the honest reference point */}
        <div
          className="absolute inset-y-0 w-px bg-faint/70"
          style={{ left: `${toPct(0)}%` }}
          aria-hidden
        />
        <div
          className="absolute inset-y-1.5 rounded-sm"
          style={{
            left: `${toPct(u.p10)}%`,
            width: `${Math.max(1, toPct(u.p90) - toPct(u.p10))}%`,
            background:
              "linear-gradient(90deg, rgb(34 211 238 / 0.25), rgb(34 211 238 / 0.55))",
          }}
          aria-hidden
        />
        <div
          className="absolute inset-y-0 w-0.5 bg-signal"
          style={{ left: `${toPct(u.median)}%` }}
          aria-hidden
        />
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-muted">
        <span className="data">{sign(u.p10)}</span>
        <span className="text-foreground">
          median <span className="data text-signal">{sign(u.median)} wins</span> ·{" "}
          {(probPositive * 100).toFixed(0)}% chance it helps
        </span>
        <span className="data">{sign(u.p90)}</span>
      </div>
    </div>
  );

  if (compact) return strip;

  return (
    <ChartFrame
      title="Projected wins impact"
      unit={`wins vs today · ${u.n_draws.toLocaleString()} simulations`}
      why="The band is the honest answer; the midpoint alone would overstate what the model knows."
      summary={`Median ${sign(u.median)} wins, with a 10th-to-90th percentile range of ${sign(
        u.p10,
      )} to ${sign(u.p90)} wins, and a ${(probPositive * 100).toFixed(0)} percent chance the deal helps.`}
    >
      {strip}
    </ChartFrame>
  );
}

/* ------------------------------------------------------------ comparisons */

export function ParetoScatter({
  points,
}: {
  points: { name: string; x: number; y: number; dominated: boolean }[];
}) {
  return (
    <ChartFrame
      title="Trade-off frontier"
      unit="on-court impact vs downside risk · score 0–100"
      why="Deals on the frontier aren't beaten on both axes by anything else on the board."
      summary={points
        .map(
          (p) =>
            `${p.name}: impact ${p.x.toFixed(0)}, risk ${p.y.toFixed(0)}${
              p.dominated ? " (beaten on every axis by another deal)" : " (on the frontier)"
            }`,
        )
        .join("; ")}
    >
      <ResponsiveContainer width="100%" height={250}>
        <ScatterChart margin={{ left: 6, right: 14, top: 10, bottom: 16 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="2 4" />
          <XAxis
            type="number"
            dataKey="x"
            name="On-court impact"
            domain={[0, 100]}
            tick={AXIS}
            tickLine={false}
            label={{
              value: "On-court impact →",
              position: "insideBottom",
              offset: -8,
              fill: "var(--chalk-dim)",
              fontSize: 11,
            }}
          />
          <YAxis
            type="number"
            dataKey="y"
            name="Downside risk"
            domain={[0, 100]}
            tick={AXIS}
            tickLine={false}
            label={{
              value: "Downside risk →",
              angle: -90,
              position: "insideLeft",
              fill: "var(--chalk-dim)",
              fontSize: 11,
            }}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ stroke: "var(--hairline)" }}
            formatter={(value, name) => [Number(value).toFixed(1), String(name)]}
            labelFormatter={() => ""}
          />
          <Scatter data={points}>
            {points.map((p) => (
              <Cell
                key={p.name}
                fill={p.dominated ? "var(--unknown)" : "var(--signal)"}
                fillOpacity={p.dominated ? 0.45 : 1}
              />
            ))}
          </Scatter>
        </ScatterChart>
      </ResponsiveContainer>
    </ChartFrame>
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
    <ChartFrame
      title="How often each deal wins"
      unit="% of 500 sampled weightings"
      why="A deal that only leads under one exact set of priorities isn't a robust recommendation."
      summary={data.map((d) => `${d.name} ranks first in ${d.value.toFixed(0)}% of weightings`).join("; ")}
    >
      <ResponsiveContainer width="100%" height={data.length * 32 + 26}>
        <BarChart data={data} layout="vertical" margin={{ left: 4, right: 14 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="2 4" horizontal={false} />
          <XAxis type="number" domain={[0, 100]} tick={AXIS} unit="%" tickLine={false} axisLine={false} />
          <YAxis
            type="category"
            dataKey="name"
            width={140}
            tick={{ ...AXIS, fontFamily: "var(--font-archivo)" }}
            tickLine={false}
            axisLine={false}
          />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: "var(--arena-high)", opacity: 0.5 }}
            formatter={(value) => [`${Number(value).toFixed(1)}%`, "ranks first"]}
          />
          <Bar dataKey="value" fill="var(--signal)" fillOpacity={0.85} radius={[0, 3, 3, 0]} barSize={13} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}

/* --------------------------------------------------------- salary timeline */

export function SalaryTimeline({
  seasons,
  capLine,
  taxLine,
}: {
  seasons: { season: string; total: number; players?: number }[];
  capLine?: number;
  taxLine?: number;
}) {
  const data = seasons.map((s) => ({ ...s, millions: s.total / 1_000_000 }));
  return (
    <ChartFrame
      title="Committed payroll by season"
      unit="$ millions"
      why="Where the money is already spoken for — and when the books clear."
      summary={data
        .map((d) => `${d.season}: $${d.millions.toFixed(1)}M across ${d.players ?? "?"} players`)
        .join("; ")}
    >
      <ResponsiveContainer width="100%" height={220}>
        {/* right margin holds the cap/tax reference labels — without it they clip */}
        <BarChart data={data} margin={{ left: 4, right: 34, top: 8 }}>
          <CartesianGrid stroke={GRID} strokeDasharray="2 4" vertical={false} />
          <XAxis dataKey="season" tick={AXIS} tickLine={false} axisLine={false} />
          <YAxis tick={AXIS} tickLine={false} axisLine={false} unit="M" />
          <Tooltip
            contentStyle={TOOLTIP_STYLE}
            cursor={{ fill: "var(--arena-high)", opacity: 0.5 }}
            formatter={(value) => [`$${Number(value).toFixed(1)}M`, "committed"]}
          />
          {capLine && (
            <ReferenceLine
              y={capLine / 1_000_000}
              stroke="var(--signal)"
              strokeDasharray="4 4"
              label={{ value: "cap", fill: "var(--signal)", fontSize: 10, position: "right" }}
            />
          )}
          {taxLine && (
            <ReferenceLine
              y={taxLine / 1_000_000}
              stroke="var(--conditional)"
              strokeDasharray="4 4"
              label={{ value: "tax", fill: "var(--conditional)", fontSize: 10, position: "right" }}
            />
          )}
          <Bar dataKey="millions" fill="var(--leather)" fillOpacity={0.8} radius={[3, 3, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </ChartFrame>
  );
}
