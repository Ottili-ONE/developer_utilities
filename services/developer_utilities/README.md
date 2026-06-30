# Ottili Developer Utilities

Free utility APIs for everyday developer tasks.

Official instance: `https://utils.ottili.one`

## v0.1

- Time and date utilities
- Calculators
- Unit conversion
- Text utilities
- Encoding and decoding
- Hashing
- UUID and random generation
- JSON formatting and validation
- QR code generation
- Weather with caching
- Debug echo, IP, and headers

## Limits

- No API key: `1,000 requests/day/IP`
- Free API key: `100,000 requests/month`

## Examples

```bash
curl https://utils.ottili.one/v1/time/now
```

```bash
curl -X POST https://utils.ottili.one/v1/calc \
  -H 'content-type: application/json' \
  -d '{"expression":"(2 + 3) * 4"}'
```

```bash
curl -X POST https://utils.ottili.one/v1/json/validate \
  -H 'content-type: application/json' \
  -d '{"text":"{\"ok\":true}"}'
```

## Self-hosting

Run with Docker:

```bash
docker build -t developer-utilities -f services/developer_utilities/Dockerfile .
docker run -p 8000:8000 developer-utilities
```

## Branding

Ottili name, logo, domains, and official branding are reserved and are not licensed for modified distributions without permission.
