"""Regression tests copied with the market-family screener."""

from __future__ import annotations

import unittest

from market_picker import choose_market_family, rank_market_candidates


class MarketPickerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.event = {
            "eventId": "sr:match:test",
            "homeTeamName": "Home",
            "awayTeamName": "Away",
            "matchStatus": "Not start",
            "markets": [
                {
                    "id": "1",
                    "desc": "1X2",
                    "status": 0,
                    "outcomes": [
                        {"id": "1", "desc": "Home", "odds": "2.00", "isActive": 1},
                        {"id": "2", "desc": "Draw", "odds": "3.00", "isActive": 1},
                        {"id": "3", "desc": "Away", "odds": "4.00", "isActive": 1},
                    ],
                },
                {
                    "id": "18",
                    "desc": "Over/Under",
                    "specifier": "total=1.5",
                    "status": 0,
                    "outcomes": [
                        {"id": "12", "desc": "Over", "odds": "1.50", "isActive": 1},
                        {"id": "13", "desc": "Under", "odds": "2.50", "isActive": 1},
                    ],
                },
                {
                    "id": "166",
                    "desc": "Corners",
                    "specifier": "total=8.5",
                    "status": 0,
                    "outcomes": [
                        {"id": "12", "desc": "Over", "odds": "1.80", "isActive": 1},
                        {"id": "13", "desc": "Under", "odds": "2.00", "isActive": 1},
                    ],
                },
                {
                    "id": "29",
                    "desc": "GG/NG",
                    "status": 1,
                    "outcomes": [
                        {"id": "74", "desc": "Yes", "odds": "1.80", "isActive": 1},
                        {"id": "76", "desc": "No", "odds": "2.00", "isActive": 1},
                    ],
                },
            ],
        }

    def test_screens_common_families_and_complete_markets(self) -> None:
        rows = rank_market_candidates(self.event)
        families = {row.family for row in rows}
        self.assertEqual(families, {"match_result", "match_goals", "corners"})
        totals = [row for row in rows if row.family == "match_goals"]
        self.assertTrue(all(row.specifier == "total=1.5" for row in totals))

    def test_rejects_incomplete_three_way_result(self) -> None:
        result = next(market for market in self.event["markets"] if market["id"] == "1")
        result["outcomes"] = result["outcomes"][:2]
        rows = rank_market_candidates(self.event)
        self.assertNotIn("match_result", {row.family for row in rows})

    def test_probability_and_hold_are_explicit(self) -> None:
        rows = rank_market_candidates(self.event)
        over = next(row for row in rows if row.family == "match_goals" and row.outcome_id == "12")
        overround = (1 / 1.5) + (1 / 2.5)
        self.assertAlmostEqual(over.market_probability, (1 / 1.5) / overround)
        self.assertAlmostEqual(over.margin, overround - 1)
        self.assertAlmostEqual(over.hold, 1 - 1 / overround)
        self.assertLess(over.hold, over.margin)
        self.assertGreater(over.shin_probability, 0)
        self.assertLess(over.shin_probability, 1)

    def test_hold_limit_and_live_status_fail_closed(self) -> None:
        self.assertEqual(rank_market_candidates(self.event, max_hold=0.01), [])
        self.event["matchStatus"] = "live"
        self.assertEqual(rank_market_candidates(self.event), [])
        self.assertIsNone(choose_market_family(self.event))

    def test_family_choice_uses_tighter_complete_market(self) -> None:
        choice = choose_market_family(self.event)
        self.assertIsNotNone(choice)
        assert choice is not None
        self.assertEqual(choice.family, "corners")
        self.assertEqual(choice.specifier, "total=8.5")
        self.assertIn("tightest", choice.reason)
        self.assertLess(choice.hold, 0.06)

    def test_family_choice_refuses_a_tie(self) -> None:
        self.event["markets"] = [
            {
                "id": "18",
                "desc": "Over/Under",
                "specifier": "total=1.5",
                "status": 0,
                "outcomes": [
                    {"id": "12", "desc": "Over", "odds": "1.90", "isActive": 1},
                    {"id": "13", "desc": "Under", "odds": "1.90", "isActive": 1},
                ],
            },
            {
                "id": "18",
                "desc": "Over/Under",
                "specifier": "total=2.5",
                "status": 0,
                "outcomes": [
                    {"id": "12", "desc": "Over", "odds": "1.90", "isActive": 1},
                    {"id": "13", "desc": "Under", "odds": "1.90", "isActive": 1},
                ],
            },
        ]
        self.assertIsNone(choose_market_family(self.event))


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(MarketPickerTests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
