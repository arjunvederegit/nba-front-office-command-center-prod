import type { Metadata } from "next";
import Link from "next/link";
import { PageHeader, Panel } from "@/components/ui";

export const metadata: Metadata = { title: "Methodology — Pivot" };

function Formula({ children }: { children: React.ReactNode }) {
  return (
    <pre className="scroll-thin my-2 overflow-x-auto rounded-md border border-hairline bg-panel2 p-3 font-mono text-xs leading-relaxed text-foreground">
      {children}
    </pre>
  );
}

function Tech({ children }: { children: React.ReactNode }) {
  return (
    <details className="group mt-3 rounded-md border border-hairline bg-panel2/50 p-3">
      <summary className="flex cursor-pointer select-none items-center justify-between gap-3">
        <span className="eyebrow">Technical detail</span>
        <span className="eyebrow text-signal">
          <span className="group-open:hidden">Show</span>
          <span className="hidden group-open:inline">Hide</span>
        </span>
      </summary>
      <div className="mt-2.5 space-y-2 text-sm leading-relaxed text-muted">{children}</div>
    </details>
  );
}

export default function MethodologyPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <PageHeader
        eyebrow="Documentation"
        title="How Pivot thinks"
        lede={
          <>
            Plain-language explanations first; the exact formulas and validation numbers are in the
            expandable technical sections and in{" "}
            <code className="data text-[13px] text-brand">docs/methodology.md</code>. Every number in
            the product traces to one of the calculations on this page.
          </>
        }
      />

      <Panel title="What the model evaluates — and what it can't know">
        <p className="text-sm leading-relaxed text-muted">
          Pivot evaluates a trade the way a front office frames it: does the deal make the team
          better on the court, does it fit the roster, is the money sensible, does it match the
          competitive window, what flexibility does it cost, and what&apos;s the downside? It does{" "}
          <em>not</em> know locker-room chemistry, medical files, private negotiations, or the
          future — which is why every projection ships with an uncertainty range and why missing
          data becomes an explicit &quot;unavailable&quot; instead of a guess.
        </p>
      </Panel>

      <Panel title="The decision score">
        <div id="utility" className="scroll-mt-24">
          <p className="text-sm leading-relaxed text-muted">
            Each team in a deal gets a <strong className="text-foreground">decision score out of
            100</strong> (50 = neutral). It&apos;s a weighted blend of six components — on-court
            impact, roster fit, contract value, competitive window, flexibility, and downside risk —
            where <em>you</em> control the weights through your strategy. It is deliberately not a
            single opaque &quot;winner&quot; score: every component and its raw calculation is shown
            alongside.
          </p>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            <strong className="text-foreground">When data is missing</strong> (for example contract
            value with no contract import), that component is dropped and the remaining weights are
            re-scaled. The score never contains an invented number — and the UI tells you what was
            excluded.
          </p>
          <Tech>
            <Formula>
              U = w_P·Performance + w_F·Fit + w_C·Contract + w_T·Window + w_A·Flexibility + w_R·Risk
              {"\n"}Σ w_k = 1 (user weights, renormalized over available components)
            </Formula>
            <p>
              Components are normalized to 0–100. Verdict labels are monotone in the score:
              ≥58 Clear win · 48–58 Roughly neutral · 40–48 Net negative · &lt;40 Clear loss ·
              low confidence ⇒ &quot;Cannot fully evaluate&quot;. A deal that fails a verified
              CBA rule receives no score at all — the failing rules are shown instead.
            </p>
          </Tech>
        </div>
      </Panel>

      <Panel title="Estimated player impact (TEI)">
        <div id="tei" className="scroll-mt-24">
          <p className="text-sm leading-relaxed text-muted">
            Every rostered player carries an <strong className="text-foreground">estimated
            impact</strong> number on Pivot&apos;s own index scale. It is deliberately{" "}
            <em>not</em> labelled &ldquo;points per 100 possessions&rdquo;: the index is a weighted
            z-score, and the fitted conversion from a team&apos;s minutes-weighted index to
            net-rating points is <strong className="text-foreground">≈15</strong>, not 1. Full name:
            Pivot Estimated Impact, TEI), built from three seasons of real box-score
            data, and it is <em>not</em> RAPTOR, EPM, LEBRON or BPM. Because it only sees box
            scores, defense is under-measured — treat small differences as noise; the uncertainty
            band on player pages is there for a reason.
          </p>
          <Tech>
            <p>Recency-weighted features (λ=0.7, minutes-weighted, seasons 2023-24 → 2025-26):</p>
            <Formula>X̄ᵢ = Σₛ λ^(s−1)·mᵢ,ₛ·Xᵢ,ₛ / Σₛ λ^(s−1)·mᵢ,ₛ</Formula>
            <p>
              A transparent weighted z-score index with documented fixed weights. A ridge
              challenger was served until R3-1 on a held-out player-level MAE of 0.637 against the
              index&apos;s 0.645 — a comparison on a next-season proxy, which is not the question
              the product asks. Measured at team level, where it was actually used, the ridge
              explained <strong>R² = 0.004</strong> of net rating against the index&apos;s{" "}
              <strong>0.751</strong>. It is retired.
            </p>
            <p>Uncertainty bands are per player, not constant:</p>
            <Formula>σ² = 0.0326 + 240.9 / total minutes</Formula>
            <p>
              estimated from 921 same-player consecutive-season pairs. σ runs 0.72 at 500 minutes
              to 0.36 at 2,500, replacing a single 2.462 taken from the retired model&apos;s
              residual spread. Most bands get narrower — which reads as overconfidence and is the
              opposite — while the thinnest-evidence players&apos; bands get wider. Scores ×2.5 to
              index points; elite ≈ +5. Model card: docs/model-card-player-impact.md.
            </p>
          </Tech>
        </div>
      </Panel>

      <Panel title="Projected wins and the rotation">
        <p className="text-sm leading-relaxed text-muted">
          A trade changes who plays, not just who&apos;s on the roster. Pivot reallocates the 240
          minutes in an NBA game across the post-trade roster (proportional to established roles,
          capped per player), discounts by each player&apos;s historical availability, and charges
          any minutes the roster cannot fill to a replacement-level player. The team-quality change
          converts to net-rating points through a coefficient fitted change-on-change on 60 team
          transitions (≈15, t = 9.8), then to wins through a conversion fit on real team-seasons.
          The same 2,000-draw simulation runs over that same reallocation, so the range you see and
          the number above it are one quantity rather than two.
        </p>
        <Tech>
          <Formula>
            ΔW = slope · ΔNetRating · (games/82) — slope 2.235 wins/point, fit on 90 team-seasons,
            R²=0.953, σ=2.9 wins
          </Formula>
          <p>
            Monte Carlo draws over player impact (validation residuals), availability (Beta around
            historical rate), minutes (±12%), and the conversion slope (±15%). Reported: median,
            10th–90th percentile, P(deal helps). Availability is historical games played — not a
            medical prediction.
          </p>
        </Tech>
      </Panel>

      <Panel title="Roster needs, strengths and fit">
        <div id="needs" className="scroll-mt-24">
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
      </Panel>

      <Panel title="Player skills — the nine Pivot measures, and the thirteen it does not">
        <div id="skills" className="scroll-mt-24">
          <p className="text-sm leading-relaxed text-muted">
            Pivot describes a player by what he does, not by where he stands. Nine capabilities are
            measured from ingested box-score data as{" "}
            <strong className="text-foreground">league percentiles</strong> — shooting volume and
            accuracy, shot creation, ball security, team defense, rim protection, rebounding,
            positional size and scoring. A skill whose inputs are missing is{" "}
            <em>omitted</em>, never filled with a league median: 0.5 is not a measurement.
          </p>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Pivot also declares{" "}
            <strong className="text-foreground">thirteen dimensions it cannot see</strong> —
            switchability, screen navigation, rim pressure, off-ball gravity and the rest — and shows
            them on every player page with the reason. They need player-tracking or matchup data,
            and no amount of modelling substitutes for it. Naming them is the point: a reader should
            learn that Pivot cannot see switchability, not conclude that switchability does not
            matter.
          </p>
          <Tech>
            <p>
              One dimension was <strong className="text-foreground">built and then withdrawn</strong>.
              A point-of-attack defense composite scored <em>worse</em> than the steals proxy it was
              meant to replace, on its own pre-registered class (0.630 against 0.611), because
              gambling for steals is what a box score records and staying in front of a ball handler
              is not. The team-side need is still measured and still shown; no player skill claims to
              fix it.
            </p>
            <p>
              Every value carries its evidence class —{" "}
              <code className="data text-[13px]">observed</code> (a provider reported it),{" "}
              <code className="data text-[13px]">derived</code> (arithmetic over observations), or{" "}
              <code className="data text-[13px]">inferred</code> (a basketball attribute asserted
              from them) — because an inference can be wrong in a way a derivation cannot.
            </p>
          </Tech>
        </div>
      </Panel>

      <Panel title="Archetypes — what kind of player, not what position">
        <div id="archetypes" className="scroll-mt-24">
          <p className="text-sm leading-relaxed text-muted">
            &quot;Power forward&quot; describes where a player once stood; &quot;stretch big&quot;
            describes what he does to a defense. Pivot places every player into one of{" "}
            <strong className="text-foreground">fourteen functional archetypes</strong> using a
            deterministic rule chain over league percentile cut points — nothing is fitted, nothing
            is random, and repeated runs are byte-identical.
          </p>
          <p className="mt-2 text-sm leading-relaxed text-muted">
            Size gates first, deliberately: a creation-first ordering — the intuitive one — labelled
            Victor Wembanyama a secondary creator.
          </p>
          <Tech>
            <p>
              The chain replaced k-means clustering in R4-3, which was not merely imprecise but
              degenerate: only 5 of its 10 label branches ever fired, 34.3 % of players carried a
              numeric suffix because clusters collided, and{" "}
              <strong className="text-foreground">
                dropping a random 10 % of players rewrote 65.7 % of the survivors&apos; labels
              </strong>
              . The replacement moves 1.78 % on the identical protocol, and all fourteen roles fire.
            </p>
            <p>
              An archetype is an <em>inference</em>, and Pivot never calls it validated: no
              ground-truth archetype set exists to check the labels against. A player holds exactly
              one today; the data model already allows several with weights, which is where a future
              engine will put a second claim.
            </p>
          </Tech>
        </div>
      </Panel>

      <Panel title="Strategy weights and sensitivity">
        <div id="weights" className="scroll-mt-24">
          <p className="text-sm leading-relaxed text-muted">
            Your strategy (contend, rebuild, re-tool…) sets how much each component matters. Because
            weights are a judgment call, Pivot stress-tests every comparison: it re-runs the
            ranking under hundreds of nearby weightings and reports how often each deal finishes
            first. A deal that only wins under one exact weighting isn&apos;t a robust
            recommendation — and the product says so.
          </p>
          <Tech>
            <p>
              500 Dirichlet samples centered on your weights (concentration 50) → first-place share,
              rank volatility, median rank; plus one-at-a-time ±50% tornado bars per component. The
              Strategy Lab&apos;s live sliders re-blend the <em>stored</em> component scores
              client-side with the same renormalization rule — exploratory, clearly labeled.
            </p>
          </Tech>
        </div>
      </Panel>

      <Panel title="Trade rules check">
        <div id="rules" className="scroll-mt-24">
          <p className="text-sm leading-relaxed text-muted">
            The rules engine verifies a documented subset of the 2023 CBA: salary matching bands,
            first/second-apron limits, aggregation restrictions, roster limits, recently-signed
            windows, no-trade clauses and two-way exclusions. Its four honest outcomes:{" "}
            <strong className="text-foreground">passes</strong>,{" "}
            <strong className="text-foreground">fails</strong>,{" "}
            <strong className="text-foreground">incomplete (data missing)</strong>, or{" "}
            <strong className="text-foreground">not checked</strong>. A deal is never called legal
            from partial data — without imported contracts, salary rules report
            &quot;unavailable&quot; and the best possible outcome is &quot;incomplete&quot;.
          </p>
          <Tech>
            <Formula>
              below 1st apron: max_in = 200%·out + $250K (≤$8.85M) | out + $9.10M (≤$35.4M) |
              125%·out + $250K
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
      </Panel>

      <Panel title="Data sources & honesty">
        <p className="text-sm leading-relaxed text-muted">
          Basketball data comes from NBA.com via the open-source <code className="data">nba_api</code>{" "}
          client; the 2025-26 totals table is a user-imported CSV keyed by official player IDs;
          historical bio data comes from a Kaggle research database (fills gaps only, never
          overwrites); contracts come from a user-downloaded Basketball-Reference snapshot; photos
          and logos are local assets matched to identities with recorded confidence. Every screen
          shows its source and freshness, and{" "}
          <Link className="text-signal underline" href="/data-health">
            Data Health
          </Link>{" "}
          shows exactly what&apos;s missing. Details: docs/data-sources.md and
          docs/identity-resolution.md.
        </p>
      </Panel>
    </div>
  );
}
