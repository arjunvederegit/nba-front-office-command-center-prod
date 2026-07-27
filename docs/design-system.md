# RosterLab design system

The visual language is "arena at night": deep navy surfaces lit from above, chalk-white
type, and two accents doing two different jobs. Every token lives in
`frontend/app/globals.css`; nothing below should be re-declared in a page component.

## Color

| Token | Value | Job |
| --- | --- | --- |
| `--court-black` | `#060A12` | page ground |
| `--arena` / `--arena-raised` / `--arena-high` | `#0C1322` / `#131C30` / `#1A2540` | panel surfaces, in depth order |
| `--hairline` / `--hairline-soft` | `#1F2C46` / `#162036` | rules and borders |
| `--chalk` / `--chalk-dim` / `--chalk-faint` | `#E9F0FB` / `#93A6C4` / `#6A7C9C` | primary, secondary, tertiary text |
| `--signal` | `#22D3EE` | **the system's voice** — live state, active nav, focus rings, primary chart series |
| `--leather` | `#F97316` | **the ball** — brand mark and the single primary action, nothing else |
| `--legal` / `--illegal` / `--conditional` / `--unknown` | `#34D399` / `#FB7185` / `#FBBF24` / `#7E8DA8` | the four legality states |
| `--team-primary` / `--team-secondary` / `--team-bright` / `--team-contrast` | per team | scoped to a team subtree by `teamVars()` |

Splitting cyan and orange by *job* is what keeps the palette from reading as generic
dark-SaaS-plus-one-accent: orange appears only where a user acts or where the brand
signs its name, so it never competes with data.

**Team color rules.** Team colors come from `lib/teamIdentity.ts` — the single source
for abbreviation, full name, conference, the three color roles and the contrast color.
They are used for panel top edges, borders, badges, chart series and crest glows, and
never to recolor a whole page. `bright` is the on-dark-legible variant; use it for text
and strokes, `primary` for fills behind `contrast` text.

## Typography

Three roles, three faces:

| Role | Face | Used for | Class |
| --- | --- | --- | --- |
| Display | **Barlow Condensed** 600/700 | page titles, module names, team abbreviations, verdicts, section heads | `.display`, `.title-xl`, `.title-lg`, `.title-md` |
| Interface | **Archivo** 400–700 | body copy, controls, labels, descriptions | default `font-sans` |
| Data | **IBM Plex Mono** 400–600, tabular | table figures, salaries, stat lines | `.data` / `.tabular` |
| Scoreboard numerals | Barlow Condensed, tabular | records, scores, big metrics | `.numeral` |
| Eyebrow | Barlow Condensed, wide-tracked caps | small section labels, units | `.eyebrow` |

The condensed display face is doing structural work, not only stylistic: it fits module
names like "Salary-Cap Center" and eight nav destinations on one line at 1024px, which
is what makes the no-wrap requirement achievable without shrinking text.

`.title-xl` and `.title-lg` use `clamp()` so headlines scale with the viewport and never
fall below a readable size.

## Surfaces and structure

- **`.panel`** — the standard surface: a subtle vertical gradient, a hairline border and
  a **lit top edge** (`--edge`, defaulting to cyan, set per-team via the `accent` prop on
  `<Panel>`). Lighting the top edge instead of outlining four sides is what stops a dense
  page from reading as a grid of identical rectangles.
- **`.court-grid`** — thin technical grid, masked to a soft ellipse. Heroes and empty
  states only.
- **`.hardwood`** — 3.5%-opacity floor grain. One section per page at most.
- **`SourceRail`** — the hairline provenance strip that closes a data panel. It is the
  product's structural signature: the honesty standard made visible on every surface.

## Motion

`--dur-fast` 120ms and `--dur-base` 220ms on `--ease-out`. Three named animations:
`.lane-in` (an asset arriving in a trade slot), `.pulse-live` (the live-data dot) and the
skeleton shimmer. Everything collapses under `prefers-reduced-motion: reduce`.

## Basketball geometry

`components/court.tsx` holds the court furniture, all of it functional:

- `HalfCourt` — true-proportion half-court line art; the Overview hero stage.
- `TransactionLane` — the strip between two team workspaces, with a center circle and
  directional paths. Horizontal on wide screens, vertical when workspaces stack.
- `KeyFrame` — the free-throw key used as the container for a headline verdict.
- `BallGlyph`, `ShotChartMotif` — small marks for capability rows and tool art.

Direction and status are never carried by color or geometry alone: arrows are paired
with the words IN/OUT, and every status `Badge` renders a glyph (`✓ ✕ ~ —`) beside its
label.

## Components

`components/ui.tsx` is the primitive set: `Panel`, `PageHeader`, `Button` / `ButtonLink`,
`Badge`, `StatBlock`, `SourceRail`, `Tabs`, `SegmentedControl`, `EmptyState`,
`UnavailableNotice`, `ErrorState`, `Spinner`, `Skeleton` / `SkeletonRows`, `MeterBar`,
`Th` / `Td`. `components/charts.tsx` wraps every visualization in `ChartFrame`, which
requires a title, the unit measured, a one-line reason it matters, and an `sr-only` text
summary — charts themselves are `aria-hidden`, so the summary is the accessible path.

## Layout and wrapping

Awkward wrapping is treated as a defect, not a nitpick. Nav labels, page titles, card
titles, buttons, tabs, metric labels, status badges and team names carry
`whitespace-nowrap` and truncate rather than wrap; body copy wraps freely. Wide tables
live inside `overflow-x-auto` with a `min-w`. `scripts/visual_qa.mjs` screenshots every
route at seven viewports and reports any horizontal overflow or console error, so
regressions surface as a failing run rather than a subjective review.
