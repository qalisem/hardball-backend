# Process — Sprint History

Hardball is built in two-week-ish iterations. Each sprint ships to production and produces a retro entry below. Tracking lives in GitHub Projects; cadence is light-Agile (single contributor).

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

## Backlog

- All 30 teams with current 25-26 figures.
- Updated system prompt covering current league situation (Doncic-Lakers, Butler-Warriors, KAT-Knicks, Bane-Magic, Durant-Rockets).
- Refactor frontend to fetch team data from backend on mount instead of hardcoding it.
