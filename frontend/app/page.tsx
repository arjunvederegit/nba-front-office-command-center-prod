"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { api } from "@/lib/api";
import { formatDate } from "@/lib/format";
import type { DataHealth } from "@/lib/types";
import { Badge } from "@/components/ui";

const CAPABILITIES = [
  {
    title: "Real provider-backed data",
    body: "Teams, players, rosters, standings and statistics from NBA.com via nba_api — with provenance and freshness on every screen. Nothing synthetic, nothing invented.",
  },
  {
    title: "CBA-aware legality",
    body: "A modular rules engine for salary matching, apron restrictions and roster limits that distinguishes verified, conditional, illegal and not-evaluated states.",
  },
  {
    title: "Explainable evaluation",
    body: "Six weighted components — performance, fit, contract, timeline, flexibility, risk — with raw calculations, never one opaque score.",
  },
  {
    title: "Uncertainty & sensitivity",
    body: "Monte Carlo win distributions, tornado analysis, and rank stability under sampled strategy weights: is the recommendation robust, or an artifact?",
  },
];

export default function LandingPage() {
  const { data: health } = useQuery({
    queryKey: ["data-health"],
    queryFn: () => api.get<DataHealth>("/data-health"),
  });

  return (
    <div className="space-y-10">
      <section className="mx-auto max-w-3xl pt-10 text-center">
        <h1 className="text-4xl font-bold tracking-tight">
          Structured decisions for an <span className="text-accent">unstructured</span> trade
          deadline.
        </h1>
        <p className="mx-auto mt-4 max-w-2xl text-muted">
          TradeLab turns “should we make this trade?” into a decision framework: current
          provider-backed NBA data, a CBA-aware legality engine, and multi-component evaluation
          with honest uncertainty — built as a decision-support system, not an oracle.
        </p>
        <div className="mt-6 flex justify-center gap-3">
          <Link
            href="/decision-room"
            className="rounded-md bg-accent px-5 py-2.5 text-sm font-semibold text-background transition hover:brightness-110"
          >
            Open the Decision Room
          </Link>
          <Link
            href="/methodology"
            className="rounded-md border border-line px-5 py-2.5 text-sm text-foreground transition hover:bg-panel"
          >
            Read the methodology
          </Link>
        </div>
        {health && (
          <div className="mt-6 flex flex-wrap items-center justify-center gap-2 text-xs text-muted">
            <Badge status={health.last_successful_sync ? "pass" : "unavailable"}>
              data synced {formatDate(health.last_successful_sync)}
            </Badge>
            <Badge status="info">season {health.current_season}</Badge>
            <Badge status={health.providers.contracts?.configured ? "pass" : "unavailable"}>
              contracts: {health.providers.contracts?.configured ? "configured" : "not configured"}
            </Badge>
            <Link href="/data-health" className="underline hover:text-foreground">
              full data health →
            </Link>
          </div>
        )}
      </section>

      <section className="grid gap-4 sm:grid-cols-2">
        {CAPABILITIES.map((c) => (
          <div key={c.title} className="rounded-lg border border-line bg-panel p-5">
            <h2 className="font-semibold">{c.title}</h2>
            <p className="mt-2 text-sm leading-relaxed text-muted">{c.body}</p>
          </div>
        ))}
      </section>

      <section className="rounded-lg border border-line bg-panel p-5">
        <h2 className="font-semibold">How a decision flows</h2>
        <ol className="mt-3 grid gap-3 text-sm text-muted md:grid-cols-5">
          {[
            "Pick a focal team & strategy",
            "Diagnose the roster's needs",
            "Construct 2–3 team trades",
            "Validate legality & evaluate impact",
            "Compare alternatives & export the memo",
          ].map((step, i) => (
            <li key={step} className="rounded-md border border-line bg-panel2 p-3">
              <span className="font-mono text-accent">{i + 1}.</span> {step}
            </li>
          ))}
        </ol>
      </section>
    </div>
  );
}
