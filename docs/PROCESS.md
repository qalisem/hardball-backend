# Process — Sprint History

Hardball was built across four two-week-ish iterations from late March through the end of April 2026. Each sprint shipped to production and produced a retro entry below. Tracking lived in GitHub Projects; cadence was light-Agile (single contributor).

---

## Sprint 1 (Mar 23 – Apr 5, 2026) — MVP chat interface

**Shipped.** Single-file React artifact with a Bloomberg-terminal aesthetic. Direct integration with the Anthropic API from the browser. Hardcoded data for five teams (LAL, BOS, TOR, GSW, OKC) embedded in the JSX. Suggested-question chips for empty state. Cap-figure display in the header. Message rendering with `**bold**`, dollar-amount highlighting, and `→` follow-up arrows on their own line.

**Deferred.** Backend, persistence, more teams.

**Retro.** Direct API calls from the browser exposed the Anthropic key in the client bundle — anyone with devtools could rip it. Need a backend before any kind of public demo. Also flagged: hardcoded data scales poorly and forces a frontend rebuild for every roster change.

---

## Sprint 2 (Apr 6 – Apr 19, 2026) — Team detail drawer + cap visualizer

**Shipped.** Slide-in side drawer with the full roster, contract notes, and a cap-position visualizer (horizontal bar with CBA threshold markers for tax / apron 1 / apron 2). Three open paths: ticker click, team-grid card click, and inline team-name mention inside an AI response. Escape-key dismiss, body scroll lock, animated entry.

**Retro.** The cap-position bar took two attempts. The first version — single bar with vertical marker lines — was hard to read at a glance; you had to math out which threshold the team had crossed. The second version filled colored segments between thresholds (under-cap / under-tax / under-apron-1 / under-apron-2 / over) and made the apron tiers visceral. Inline team-name parsing in AI responses was harder than expected — the existing markdown pass already split on `**bold**` spans, and naively splitting again on team names would shred those bold runs. Resolved with a careful regex that walks bold spans and plain text separately.

---

## Sprint 3 (Apr 20 – Apr 26, 2026) — Backend extraction + AWS deploy

**Shipped.** Flask backend with `/api/chat`, `/api/teams`, `/api/teams/<abbr>`, `/api/health`. Team data extracted from JSX into `data/teams.json`. Pytest suite (8 tests) covering routes and `/api/chat` input validation. GitHub Actions CI on every PR. Deployed to Elastic Beanstalk. Static frontend deployed to S3 + CloudFront with HTTPS. Anthropic key stored via `eb setenv` (sourced from Secrets Manager). CloudFront `/api/*` behavior added so the frontend uses same-origin relative paths and the HTTP-only EB endpoint stops being a mixed-content problem.

**Retro — production debugging journey.** Everything that could go wrong did. In order:

1. **Initial deploy returned 502 on `/api/chat`.** EB logs showed Anthropic returning "model not found" for `claude-sonnet-4-20250514`, retired by Anthropic seven days before the first deploy. **Fix:** parameterize the model via env var (`ANTHROPIC_MODEL`).
2. **After `eb setenv ANTHROPIC_MODEL=...`, still 404.** SSH'd into the EC2 instance and grepped `/var/app/current/app/routes.py`. The deployed code was still the original — the model name was hardcoded, not env-driven, despite multiple "successful" `eb deploy` runs. **Root cause:** `eb deploy` only ships files committed to git; `sed` edits to the working tree were silently ignored. **Fix:** commit before deploying.
3. **Once `/api/chat` worked, deploying the frontend caused mixed-content errors.** The HTTPS S3/CloudFront page couldn't call the HTTP-only EB endpoint. **Fix:** added a CloudFront `/api/*` behavior pointing at the EB origin so the frontend uses relative same-origin paths, then set `VITE_API_BASE=` (empty) at build time.
4. **One more bug from the empty-string `VITE_API_BASE`.** JavaScript's `||` operator treats `""` as falsy, so the dev fallback `'http://localhost:5000'` kicked in even when the env var was set. **Fix:** changed the fallback to `''` so empty-string production builds work as intended.

---

## Sprint 4 (Apr 27 – Apr 30, 2026) — All 30 teams + 25-26 data

**Shipped.** Expanded `teams.json` to all 30 NBA teams with current 2025-26 season figures (cap $154.647M, tax $187.895M, apron 1 $195.945M, apron 2 $207.824M; data dated 2026-03-06 from the Sports Business Classroom apron tracker). Rewrote the system prompt with the current league situation: Cleveland leading payroll at $211.7M, post-Doncic-trade Lakers, Butler-Warriors, KAT-Knicks, Bane-Magic, Durant-Rockets. Refactored the frontend to fetch team data from the backend on mount instead of hardcoding it — future roster updates only need a backend redeploy and a CloudFront invalidation, no frontend rebuild.

**Retro.** Refactoring module-level constants (`TEAM_DATA`, `TICKER`) into component state required updating three subcomponents (Ticker, EmptyState, TeamDrawer) to receive the data as props. Caught all three only after blank-screen runtime errors at the live URL. **Lesson:** install ESLint with `no-undef` and `react-hooks` rules to catch these at edit time, not on production.

---

## Backlog (next sprint — not yet started)

- **Trade machine.** Drag-and-drop UI for building hypothetical trades; backend endpoint validating CBA legality (125% + $100K outgoing rule, apron impact, hard-cap implications).
- **Extension calculator.** Project max contracts based on player tier (25%/30%/35%), raise %, and Bird Rights status.
- **Real-time data integration.** Spotrac scraping or SportRadar API for daily payroll updates instead of a static snapshot.
- **ESLint** with `no-undef` and `react-hooks` plugins to catch the Sprint 4 class of bug at edit time.

---

## Definition of Done

A sprint item is done when:

1. PR merged to `main`.
2. CI passes (pytest on backend, build check on frontend).
3. Backend changes deployed via `eb deploy`.
4. Frontend changes synced to S3 (`aws s3 sync dist/ s3://hardball-web-qali --delete`) and CloudFront invalidated (`aws cloudfront create-invalidation --distribution-id E1AEOT2IV7WSET --paths "/*"`).
5. Manual smoke test in production: load https://dz3csw06yjedg.cloudfront.net, send a chat, open a team drawer, verify `/api/health` returns the current `team_count`.
6. Sprint log in this file updated with what shipped and what was learned.
