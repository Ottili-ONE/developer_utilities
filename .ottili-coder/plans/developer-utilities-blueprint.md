# CodeHelm Blueprint: Ottili Developer Utilities v0.1

## Idea
Build `utils.ottili.one` as **Ottili Developer Utilities**: a small, free, public developer utility API operated by Ottili ONE.

## Targeted Questions

1. What is the product scope?
   - Answer: a lightweight public utility API, not a SaaS platform, not billing, not a dashboard-heavy product.

2. Which endpoints are in v0.1?
   - Answer: only safe local-compute utilities plus weather with caching.

3. What is explicitly out of scope?
   - Answer: all SSRF-prone or remote-fetch categories such as URL metadata, DNS, SSL, HTTP status checks, security headers, OpenGraph, sitemap/robots fetch, webhook testing, unshorten, screenshots, PDF processing, and public scraping.

4. How are limits handled?
   - Answer: IP-based limits for anonymous users, optional free API keys with higher monthly limits, Redis-backed counters.

5. How is weather implemented?
   - Answer: Open-Meteo or an equivalent free provider, cached aggressively, stale-if-error when possible.

6. What is the hosting and branding posture?
   - Answer: official hosted instance at `https://utils.ottili.one`, Apache-2.0 source, Ottili branding reserved.

## Blueprint

### Product shape
- Public name: `Ottili Developer Utilities`
- Tagline: `Free utility APIs for everyday developer tasks.`
- Hosted instance: `utils.ottili.one`
- Self-hostable: yes
- No paid plans in v0.1
- No login required for basic usage

### Service boundaries
- Build an isolated service under `services/developer_utilities/`
- Do not route public utility traffic into the full Ottili ONE Unified API
- Only expose explicitly implemented utility endpoints
- Use Redis for rate limiting and weather caching
- Store API keys hashed, not plaintext

### v0.1 endpoint set
- Time and date: `/v1/time/now`, `/v1/time/convert`, `/v1/timezones`
- Calculators: `/v1/calc`, `/v1/calc/vat`, `/v1/calc/margin`
- Units: `/v1/units/convert`
- IDs and random: `/v1/id/uuid`, `/v1/random/string`, `/v1/random/password`
- Hashing: `/v1/hash/sha256`
- Encoding: `/v1/base64/encode`, `/v1/base64/decode`, `/v1/url/encode`, `/v1/url/decode`
- Text: `/v1/text/slugify`, `/v1/text/count`
- JSON: `/v1/json/format`, `/v1/json/validate`
- QR: `/v1/qr/create`
- Debug: `/v1/ip`, `/v1/debug/headers`, `/v1/debug/echo`
- Weather: `/v1/weather/current`, `/v1/weather/forecast`

### Response contract
- Success:
  - `ok: true`
  - `data: {}`
  - `meta.request_id`
  - `meta.rate_limit` when applicable
- Error:
  - `ok: false`
  - `error.code`
  - `error.message`
  - `meta.request_id`

### Rate limiting
- Anonymous default: `1,000/day/IP` and `60/min/IP`
- Free API key: `100,000/month/key`, plus higher burst limits
- Heavier endpoints get stricter per-minute/day limits
- Rate limits should run before expensive work

### Weather
- Use Open-Meteo by default
- Current weather cache: 10-15 minutes
- Forecast cache: 30-60 minutes
- If provider fails, return stale cached data if available and mark it stale

### Documentation and UI
- Root landing page for the marketing/docs surface
- `/docs` for API docs/OpenAPI
- `/playground` only if cheap to implement
- `/status` for basic health/status
- Include README, LICENSE, SECURITY.md, and OpenAPI output

### Implementation shape
- FastAPI service in `services/developer_utilities/app/`
- Router-per-feature organization
- Config, response helpers, rate limiting, API keys, providers, and tests separated cleanly
- Dockerfile for local and hosted execution

## Approval Status
- Approval actor: pending explicit approval
- Approval time: pending explicit approval
- Dispatch status: not started

## Notes
- This blueprint intentionally stays within the safe v0.1 utility set.
- Any future SSRF-prone or network-fetching categories stay in v0.2+ only.
