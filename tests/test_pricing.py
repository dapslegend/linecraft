import json
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from linecraft.pricing import PriceError, analyse_market, shin_devig
from linecraft.server import make_server


class PricingTests(unittest.TestCase):
    def test_shin_removes_overround_and_shades_longshot(self) -> None:
        raw = [1 / 1.50, 1 / 3.40, 1 / 7.00]
        fair, z = shin_devig(raw)
        self.assertAlmostEqual(sum(fair), 1.0, places=9)
        self.assertGreater(z, 0.0)
        self.assertLess(fair[0], raw[0])
        self.assertLess(fair[-1] / raw[-1], fair[0] / raw[0])

    def test_analyse_reports_hold_not_a_wager(self) -> None:
        report = analyse_market(
            [
                {"name": "Home", "odds": 1.91},
                {"name": "Away", "odds": 1.91},
            ]
        )
        self.assertAlmostEqual(report["overround"], 1 / 1.91 * 2, places=5)
        self.assertGreater(report["hold"], 0)
        self.assertIn("not a wager", report["note"])
        self.assertEqual(report["method"], "shin")

    def test_rejects_incomplete_and_arbitrage(self) -> None:
        with self.assertRaises(PriceError):
            analyse_market([{"name": "Only", "odds": 1.5}])
        with self.assertRaises(PriceError):
            analyse_market(
                [
                    {"name": "Home", "odds": 2.2},
                    {"name": "Away", "odds": 2.2},
                ]
            )

    def test_http_analyse_and_unknown_route(self) -> None:
        server = make_server("127.0.0.1", 0)
        port = server.server_address[1]
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            health = json.loads(urlopen(f"http://127.0.0.1:{port}/health", timeout=2).read())
            self.assertEqual(health["status"], "ok")
            body = json.dumps(
                {"outcomes": [{"name": "Over", "odds": 1.87}, {"name": "Under", "odds": 1.95}]}
            ).encode()
            req = Request(
                f"http://127.0.0.1:{port}/v1/markets/analyse",
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            report = json.loads(urlopen(req, timeout=2).read())
            self.assertEqual(len(report["outcomes"]), 2)
            self.assertAlmostEqual(sum(row["fair"] for row in report["outcomes"]), 1.0, places=4)
            with self.assertRaises(HTTPError) as missing:
                urlopen(f"http://127.0.0.1:{port}/v1/bets", timeout=2)
            self.assertEqual(missing.exception.code, 404)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
