# Linecraft

Backend-only. Share-code booking is allowed. Staking, account storage, and secrets are not.

- Keep the HTTP server on the stdlib and loopback by default.
- A market must be a complete mutually exclusive set before de-vig.
- Hold is `1 - 1/overround`. Margin is `overround - 1`.
- Reject overround below 1 instead of treating it as a tradable edge.
- Do not import anything from sibling workspaces.
