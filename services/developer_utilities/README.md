# Ottili Developer Utilities

Free utility APIs for everyday developer tasks.

## What this is

Ottili Developer Utilities is a small public utility API operated by Ottili ONE. It is intentionally narrow in scope: safe local-compute utilities plus weather with caching.

## Hosted instance

Official hosted instance: https://utils.ottili.one

## Limits

- No API key: 1,000 requests / day / IP
- Free API key: 100,000 requests / month

## Run locally

```bash
pip install -e .[dev]
uvicorn services.developer_utilities.app.main:app --reload
```

## Examples

```bash
curl http://127.0.0.1:8000/v1/time/now
curl -X POST http://127.0.0.1:8000/v1/json/validate -H 'content-type: application/json' -d '{"text":"{\"ok\":true}"}'
curl -X POST http://127.0.0.1:8000/v1/qr/create -H 'content-type: application/json' -d '{"text":"https://ottili.one"}'
```

## v0.1 scope

Included: time/date, calculators, unit conversion, text tools, encoding, hashing, UUID/random, JSON tools, QR codes, weather, and debug helpers.

Not included in v0.1: URL metadata, DNS lookup, SSL lookup, HTTP status checks, webhook testing, OpenGraph fetch, robots fetch, sitemap fetch, screenshots, security header scanners, or arbitrary URL fetching.

## Branding

Source code is licensed under Apache-2.0. Ottili name, logo, domains and branding are reserved and not licensed for modified distributions without permission.
