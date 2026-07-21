import type { Metadata } from "next";
import { Card } from "@/components/ui";

export const metadata: Metadata = { title: "Methodology — TradeLab" };

function Formula({ children }: { children: React.ReactNode }) {
  return (
    <pre className="scroll-thin my-2 overflow-x-auto rounded-md border border-line bg-panel2 p-3 font-mono text-xs leading-relaxed">
      {children}
    </pre>
  );
}

export default function MethodologyPage() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="text-2xl font-bold">Methodology</h1>
        <p className="mt-1 text-sm text-muted">
          Every number in TradeLab traces to a documented calculation over real provider-backed
          data. The full write-up with validation results lives in{" "}
          <code className="text-accent">docs/methodology.md</code> in the repository.
        </p>
      </div>

      <Card title="Composite utility — never a magic score">
        <p className="text-sm leading-relaxed text-muted">
          Each trade is evaluated per team as a weighted sum of six components, each normalized to
          0–100 where 50 is neutral:
        </p>
        <Formula>
          U = w_P·Performance + w_F·Fit + w_C·Contract + w_T·Timeline + w_A·Assets + w_R·Risk
          {"\n"}Σ w_k = 1 (user-controlled, renormalized)
        </Formula>
        <p className="text-sm leading-relaxed text-muted">
          When a component cannot be computed (e.g. contract value with no contract provider), it
          is <em>excluded and the remaining weights renormalized</em> — the composite never
          contains an invented number, and the exclusion is shown in the UI.
        </p>
      </Card>

      <Card title="TEI — TradeLab Estimated Impact">
        <p className="text-sm leading-relaxed text-muted">
          TEI is this project&apos;s own per-100-possession impact estimate. It is <em>not</em>{" "}
          RAPTOR, EPM, LEBRON or BPM. Two candidates are trained and compared with time-aware
          validation (transitions only predict forward — no random row splits across seasons):
        </p>
        <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-muted">
          <li>a transparent weighted z-score index over scoring efficiency, creation, ball security, rebounding and stocks;</li>
          <li>a ridge regression predicting a next-season box-derived impact proxy (0.6·z(PIE) + 0.4·z(NET_RATING), minutes-weighted).</li>
        </ul>
        <Formula>
          X̄ᵢ = Σₛ λ^(s−1)·mᵢ,ₛ·Xᵢ,ₛ / Σₛ λ^(s−1)·mᵢ,ₛ (λ = 0.7, m = minutes; 3 seasons)
        </Formula>
        <p className="text-sm leading-relaxed text-muted">
          The production model is chosen on held-out MAE vs. a persistence baseline; validation
          metrics are stored with every model version and displayed on the Data Health page.
          Uncertainty bands come from validation residuals.
        </p>
      </Card>

      <Card title="Team projection & rotation">
        <p className="text-sm leading-relaxed text-muted">
          Post-trade projection reallocates the 240 regulation minutes per game (proportional to
          established minutes, capped per player, user-overridable) instead of naively summing
          player values. Availability discounts expected minutes with replacement-level fill-in.
          Net-rating changes convert to wins via a mapping fit on ingested team-seasons:
        </p>
        <Formula>
          ΔW ≈ slope · ΔNetRating · (games/82) — slope calibrated by regression on 90
          team-seasons (not a hard-coded constant); fit quality (R²) stored with the model.
        </Formula>
      </Card>

      <Card title="Roster fit & needs">
        <p className="text-sm leading-relaxed text-muted">
          Team needs are transparent percentile rules over real team statistics (e.g. bottom-third
          three-point volume ⇒ shooting need) plus roster composition (size, creator count).
          Proxies are labeled as proxies. Fit measures whether incoming players address needs
          without harmful redundancy:
        </p>
        <Formula>F = Σₖ nₖ·Δsₖ − γ·Σₖ max(0, rₖ) (γ = 0.35)</Formula>
      </Card>

      <Card title="Trade legality">
        <p className="text-sm leading-relaxed text-muted">
          A modular rules engine implements a documented subset of the 2023 CBA: expanded/standard
          traded-player-exception salary matching (200% + $250K / +$9.096M band / 125% + $250K,
          scaled by league year), first- and second-apron restrictions, aggregation prohibition,
          roster limits, recently-signed windows, no-trade clauses and two-way exclusions. Results
          are four-state honest: <strong>verified legal · verified illegal · conditionally valid ·
          not evaluated</strong>. Without a contract provider, salary rules report
          &quot;unavailable&quot; and nothing is certified. Full rule-by-rule coverage:{" "}
          <code className="text-accent">docs/cba-rule-coverage.md</code>.
        </p>
      </Card>

      <Card title="Uncertainty & sensitivity">
        <p className="text-sm leading-relaxed text-muted">
          Monte Carlo simulation (2,000 draws) samples player impact (validation residuals),
          availability (beta around the historical rate), minutes noise, and conversion
          uncertainty, reporting the median, 10th/90th percentiles and P(positive). Sensitivity
          analysis samples strategy weights from a Dirichlet centered on the user&apos;s weights and
          reports how often each alternative ranks first — a recommendation is only called robust
          if it survives reasonable weight perturbations.
        </p>
      </Card>

      <Card title="Known limitations (honest scope)">
        <ul className="list-disc space-y-1 pl-5 text-sm leading-relaxed text-muted">
          <li>No contract provider is bundled: salary matching, payroll and contract value are unavailable until one is configured — they are never estimated.</li>
          <li>Injury status is not modeled; availability is historical games played only.</li>
          <li>Draft-pick ownership is unverified; picks are hypothetical and Stepien compliance is not certified.</li>
          <li>TEI is a box-score-based estimate; it does not see defensive matchup data or tracking data.</li>
          <li>The CBA subset omits sign-and-trades, trade exceptions, cash, base-year compensation and hard-cap triggers (documented in the repo).</li>
        </ul>
      </Card>
    </div>
  );
}
