"""Stdlib HTTP API for Linecraft price analysis.

Bind is localhost by default. There is no stake, share, or account endpoint.
"""

from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from linecraft import __version__
from linecraft.pricing import PriceError, analyse_market

MAX_BODY = 64 * 1024
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8787


def health() -> dict[str, Any]:
    return {
        "service": "linecraft",
        "version": __version__,
        "status": "ok",
        "scope": "price-analysis-only",
    }


class Handler(BaseHTTPRequestHandler):
    server_version = f"Linecraft/{__version__}"

    def log_message(self, fmt: str, *args: Any) -> None:
        # Keep access logs free of request bodies.
        super().log_message("%s", self.path)

    def _send(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0 or length > MAX_BODY:
            raise PriceError(f"JSON body must be 1 to {MAX_BODY} bytes")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode())
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise PriceError("body must be JSON") from exc
        if not isinstance(payload, dict):
            raise PriceError("body must be a JSON object")
        return payload

    def do_GET(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path == "/health":
            self._send(200, health())
            return
        if path == "/v1":
            self._send(
                200,
                {
                    "service": "linecraft",
                    "endpoints": ["GET /health", "POST /v1/markets/analyse"],
                    "wagering": False,
                },
            )
            return
        self._send(404, {"error": "not_found"})

    def do_POST(self) -> None:  # noqa: N802
        path = urlparse(self.path).path
        if path != "/v1/markets/analyse":
            self._send(404, {"error": "not_found"})
            return
        try:
            payload = self._read_json()
            method = payload.get("method", "shin")
            if not isinstance(method, str):
                raise PriceError("method must be a string")
            outcomes = payload.get("outcomes")
            if not isinstance(outcomes, list):
                raise PriceError("outcomes must be a list")
            self._send(200, analyse_market(outcomes, method=method))
        except PriceError as exc:
            self._send(400, {"error": "invalid_market", "detail": str(exc)})


def make_server(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> ThreadingHTTPServer:
    if host not in ("127.0.0.1", "localhost", "::1"):
        raise PriceError("refusing non-loopback bind; set LINECRAFT_HOST only to localhost")
    return ThreadingHTTPServer((host, port), Handler)


def main() -> None:
    host = os.environ.get("LINECRAFT_HOST", DEFAULT_HOST)
    port = int(os.environ.get("LINECRAFT_PORT", str(DEFAULT_PORT)))
    server = make_server(host, port)
    print(f"linecraft {__version__} listening on http://{host}:{port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
