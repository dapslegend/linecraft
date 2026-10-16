# Linecraft

Public sports price analysis. Backend only.

Linecraft reads a complete market of decimal odds and returns de-vigged probabilities, hold, and margin. It does not place wagers, create betting slips, store accounts, or talk to a sportsbook.

Frontend deployment is intentionally not in this repository yet.

## Run

```bash
PYTHONPATH=src python3 -m linecraft.server
```

Default bind is `127.0.0.1:8787`. Non-loopback binds are refused.

```bash
curl -s http://127.0.0.1:8787/health
curl -s -X POST http://127.0.0.1:8787/v1/markets/analyse \
  -H 'content-type: application/json' \
  -d '{"outcomes":[{"name":"Home","odds":1.91},{"name":"Away","odds":1.91}]}'
```

`method` may be `shin` (default) or `proportional`.

## Test

```bash
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

## API

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/health` | Liveness |
| GET | `/v1` | Endpoint index |
| POST | `/v1/markets/analyse` | De-vig one complete market |

A market needs 2 to 24 mutually exclusive outcomes. Names must be unique. Odds must be finite and greater than 1. An overround below 1 is rejected.

Hold is `1 - 1/overround`. Margin is `overround - 1`.

## What this is not

No stake placement. No share codes. No user data. No secrets in the repo.
