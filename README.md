# Linecraft

Public sports price analysis and share-only booking. Backend only.

Linecraft reads a complete market of decimal odds and returns de-vigged probabilities, hold, and margin. It can also pull a configured sportsbook feed, ask Grok to research the board, and post a share code.

It does not stake. It does not store accounts. It does not put secrets in the repo.

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

## Book a share

Copy `.env.example` to `.env` and set `GROK_API_KEY`. Copy `config.example.json` if you want a local config. Default provider is Sporty. Grok research is on. Booking posts a share code only.

```bash
set -a && source .env && set +a
PYTHONPATH=src python3 -m linecraft --config config.example.json --pull-only
PYTHONPATH=src python3 -m linecraft --config config.example.json --no-book
PYTHONPATH=src python3 -m linecraft --config config.example.json
```

`provider` may be `sporty`, `1xbet`, or `generic`. Sports, pages, markets, and the time window come from config. A 1xBet or generic feed is pulled, but a share is refused unless that book has a share-only URL. There is no stake field.

A researched keep is not booked unless it still matches a live grid outcome id. Share odds are always strings. An Under is dropped unless both teams are confirmed low scoring, well defended, or weak in attack. An Over is dropped unless both teams' sourced scoring rates clear that line. Grok decides Home, Away, Draw, or double chance. Expected goals are context, not the decision. A Draw, Home or Draw, Draw or Away, or Home or Away needs both teams at 2 or more draws in their last five finished games. A straight Home or Away does not need that count. Every keep also needs a sourced stake, such as table place, points gap, relegation, promotion, or a cup round. A friendly or a dead rubber is dropped. The default window is 01:00 to midnight in Africa/Lagos, and the share cap is 50 so the slip can be shuffled by hand. One miss kills a full accumulator. A share code is not a sure thing and is not 80%.

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

No stake placement. No user data. No secrets in the repo. A share code is a booking link, not a wager.
