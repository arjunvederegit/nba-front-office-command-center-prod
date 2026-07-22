import type { Metadata } from "next";
import { Card } from "@/components/ui";

export const metadata: Metadata = { title: "Methodology — RosterLab" };

function Formula({ children }: { children: React.ReactNode }) {
  return (
    <pre className="scroll-thin my-2 overflow-x-auto rounded-md border border-line bg-panel2 p-3 font-mono text-xs leading-relaxed">
      {children}
    </pre>
  );
}

function Tech({ children }: { children: React.ReactNode }) {
  return (
    <details className="mt-3 rounded-md border border-line bg-panel2/50 p-3">
      <summary className="cursor-pointer text-xs font-semibold text-muted hover:text-foreground">
        Technical detail
      </summary>
      <div className="mt-2 space-y-2 text-sm leading-relaxed text-muted">{children}</div>
    </details>
  );
}

export default function MethodologyPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold">How RosterLab thinks</h1>
        <p className="mt-1 text-sm text-muted">
          Plain-language explanations first; the exact formulas and validation numbers are in the
          expandable technical sections and in <code className="text-brand">docs/methodology.md</code>.
          Every number in the product traces to one of the calculations on this page.
        </p>
      </div>

      <Card title="What the model evaluates — and what it can't know">
        <p className="text-sm leading-relaxed text-muted">
          RosterLab evaluates a trade the way a front office frames it: does the deal make the team
          better on the court, does it fit the roster, is the money sensible, does it match the
          competitive window, what flexibility does it cost, and what&apos;s the downside? It does{" "}
          <em>not</em> know locker-room chemistry, medical files, private negotiations, or the
          future — which is why every projection ships with an uncertainty range and why missing
          data becomes an explicit &quot;unavailable&quot; instead of a guess.
        </p>
      </Card>

      <Card title="The decision score" >
        <div id="utility" className="scroll-mt-20">
          <p className="text-sm leading-relaxed text-muted">
            Each team in a deal gets a <strong>decision score out of 100</strong> (50 = neutral).
            It&apos;s a weighted blend of six components — on-court impact, roster fit, contract value,
            competitive window, flexibility, and downside risk — where <em>you</em> control the
            weights through your strategy. It is deliberately not a single opaque &quot;winner&quot;
            score: every component and its raw calculation is shown alongside.
          </p>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            <strong>When data is missing</strong> (for example contract value with no contract
            import), that component is dropped and the remaining weights are re-scaled. The score
            never contains an invented number — and the UI tells you what was excluded.
          </p>
          <Tech>
            <Formula>
              U = w_P·Performance + w_F·Fit + w_C·Contract + w_T·Window + w_A·Flexibility + w_R·Risk
              {"\n"}Σ w_k = 1 (user weights, renormalized over available components)
            </Formula>
            <p>
              Components are normalized to 0–100. Fan verdicts map from the score: ≥58 Strong fit ·
              48–58 Mixed · 40–48 High-risk upside · &lt;40 Poor fit · low confidence ⇒ &quot;Cannot
              fully evaluate&quot;.
            </p>
          </Tech>
        </div>
      </Card>

      <Card title="Estimated player impact (TEI)">
        <div id="tei" className="scroll-mt-20">
          <p className="text-sm leading-relaxed text-muted">
            Every rostered player carries an <strong>estimated impact</strong> number — roughly,
            points of team scoring margin per 100 possessions attributable to the player. It&apos;s
            RosterLab&apos;s own estimate (full name: TradeLab/RosterLab Estimated Impact, TEI), built
            from three seasons of real box-score data, and it is <em>not</em> RAPTOR, EPM, LEBRON
            or BPM. Because it only sees box scores, defense is under-measured — treat small
            differences as noise; the uncertainty band on player pages is there for a reason.
          </p>
          <Tech>
            <p>
              Recency-weighted features (λ=0.7, minutes-weighted, seasons 2023-24 → 2025-26):
            </p>
            <Formula>X̄ᵢ = Σₛ λ^(s−1)·mᵢ,ₛ·Xᵢ,ₛ / Σₛ λ^(s−1)·mᵢ,ₛ</Formula>
            <p>
              Ridge regression (α=10) predicting next-season 0.6·z(PIE)+0.4·z(NET_RATING), chosen
              by strictly time-aware validation: held-out MAE <strong>0.637</strong> vs 0.717
              persistence baseline and 0.645 transparent-index baseline (n=464 transitions).
              Uncertainty bands from validation residual σ (0.985 z-units). Scores ×2.5 to index
              points; elite ≈ +5. Model card: docs/model-card-player-impact.md.
            </p>
          </Tech>
        </div>
      </Card>

      <Card title="Projected wins and the rotation">
        <p className="text-sm leading-relaxed text-muted">
          A trade changes who plays, not just who&apos;s on the roster. RosterLab reallocates the 240
          minutes in an NBA game across the post-trade roster (proportional to established roles,
          capped per player), discounts by each player&apos;s historical availability, and converts the
          resulting team-quality change into wins using a conversion fit on real team-seasons —
          then runs 2,000 simulations to produce the wins range you see.
        </p>
        <Tech>
          <Formula>
            ΔW = slope · ΔNetRating · (games/82) — slope 2.235 wins/point, fit on 90 team-seasons,
            R²=0.953, σ=2.9 wins
          </Formula>
          <p>
            Monte Carlo draws over player impact (validation residuals), availability
            (Beta around historical rate), minutes (±12%), and the conversion slope (±15%).
            Reported: median, 10th–90th percentile, P(deal helps). Availability is historical games
            played — not a medical prediction.
          </p>
        </Tech>
      </Card>

      <Card title="Roster needs, strengths and fit">
        <div id="needs" className="scroll-mt-20">
          <p className="text-sm leading-relaxed text-muted">
            Team needs (&quot;3PT volume&quot;, &quot;rim protection&quot;…) come from transparent
            percentile rules over real league stats — a team in the bottom third for three-point
            attempts has a shooting need; no AI, no scouting opinions. Trade fit then asks: do the
            incoming players address those needs without duplicating what the roster already does
            well? Proxies are labeled (blocks ≈ rim protection, steals ≈ point-of-attack pressure).
          </p>
          <Tech>
            <Formula>F = Σₖ nₖ·Δsₖ − γ·Σₖ max(0, rₖ)   (γ = 0.35)</Formula>
            <p>
              n = need severity (0–1 from percentile shortfall), Δs = minutes-weighted change in
              skill percentile (incoming − outgoing), r = redundancy above the roster&apos;s 70th
              percentile skills.
            </p>
          </Tech>
        </div>
      </Card>

      <Card title="Strategy weights and sensitivity">
        <div id="weights" className="scroll-mt-20">
          <p className="text-sm leading-relaxed text-muted">
            Your strategy (contend, rebuild, re-tool…) sets how much each component matters. Because
            weights are a judgment call, RosterLab stress-tests every comparison: it re-runs the
            ranking under hundreds of nearby weightings and reports how often each deal finishes
            first. A deal that only wins under one exact weighting isn&apos;t a robust recommendation —
            and the product says so.
          </p>
          <Tech>
            <p>
              500 Dirichlet samples centered on your weights (concentration 50) → first-place
              share, rank volatility, median rank; plus one-at-a-time ±50% tornado bars per
              component. The Compare page&apos;s live sliders re-blend the <em>stored</em> component
              scores client-side with the same renormalization rule — exploratory, clearly labeled.
            </p>
          </Tech>
        </div>
      </Card>

      <Card title="Trade rules check">
        <div id="rules" className="scroll-mt-20">
          <p className="text-sm leading-relaxed text-muted">
            The rules engine verifies a documented subset of the 2023 CBA: salary matching bands,
            first/second-apron limits, aggregation restrictions, roster limits, recently-signed
            windows, no-trade clauses and two-way exclusions. Its four honest outcomes:{" "}
            <strong>passes</strong>, <strong>fails</strong>, <strong>incomplete (data
            missing)</strong>, or <strong>not checked</strong>. A deal is never called legal from
            partial data — without imported contracts, salary rules report &quot;unavailable&quot;
            and the best possible outcome is &quot;incomplete&quot;.
          </p>
          <Tech>
            <Formula>
              below 1st apron: max_in = 200%·out + $250K (≤$8.85M) | out + $9.10M (≤$35.4M) | 125%·out + $250K
              {"\n"}at/above 1st apron: max_in = out + $250K · 2nd apron: no aggregation
            </Formula>
            <p>
              2025-26 anchors scale with the cap per the CBA; verified cap figures for 2025-26 and
              2026-27 ship as sourced YAML. Full rule-by-rule coverage, sources and tests:
              docs/cba-rule-coverage.md. Not covered (and never faked): sign-and-trades, trade
              exceptions, cash, base-year compensation, hard-cap triggers.
            </p>
          </Tech>
        </div>
      </Card>

      <Card title="Data sources & honesty">
        <p className="text-sm leading-relaxed text-muted">
          Basketball data comes from NBA.com via the open-source <code>nba_api</code> client; the
          2025-26 totals table is a user-imported CSV keyed by official player IDs; historical bio
          data comes from a Kaggle research database (fills gaps only, never overwrites); contracts
          come from a user-downloaded Basketball-Reference snapshot; photos and logos are local
          assets matched to identities with recorded confidence. Every screen shows its source and
          freshness, and <a className="text-brand underline" href="/data-status">Data Status</a>{" "}
          shows exactly what&apos;s missing. Details: docs/data-sources.md and
          docs/identity-resolution.md.
        </p>
      </Card>
    </div>
  );
}
