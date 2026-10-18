import json
import unittest
from unittest.mock import patch

from linecraft.book import BookError, assert_share_only, share_sporty
from linecraft.config import load_config
from linecraft.feeds import pull_games
from linecraft.__main__ import selections_from_keeps
from linecraft.grok import over_is_strict, under_is_strict


class BookTests(unittest.TestCase):
    def test_config_refuses_a_stake(self) -> None:
        with self.assertRaises(ValueError):
            with patch("linecraft.config.Path.exists", return_value=True), patch(
                "linecraft.config.Path.read_text",
                return_value=json.dumps({"book": {"stake": True, "mode": "share"}}),
            ):
                load_config("config.example.json")

    def test_default_config_is_share_only_and_grok_on(self) -> None:
        config = load_config(None)
        self.assertEqual(config["provider"], "sporty")
        self.assertTrue(config["grok"]["enabled"])
        self.assertEqual(config["grok"]["model"], "grok-4.7")
        self.assertFalse(config["book"]["stake"])
        assert_share_only(config)

    def test_share_payload_has_string_odds_and_no_stake(self) -> None:
        captured = {}

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return json.dumps({"bizCode": 10000, "data": {"shareCode": "TEST01"}}).encode()

        def fake_urlopen(req, timeout=0):
            captured["body"] = json.loads(req.data.decode())
            captured["url"] = req.full_url
            return FakeResp()

        with patch("linecraft.book.urllib.request.urlopen", fake_urlopen):
            result = share_sporty(
                [{
                    "eventId": "sr:match:1",
                    "marketId": "18",
                    "specifier": "total=2.5",
                    "outcomeId": "12",
                    "odds": 1.9,
                }]
            )
        self.assertEqual(result["data"]["shareCode"], "TEST01")
        selection = captured["body"]["selections"][0]
        self.assertEqual(selection["odds"], "1.90")
        self.assertNotIn("stake", captured["body"])
        self.assertNotIn("stake", selection)
        self.assertIn("/orders/share", captured["url"])

    def test_unknown_provider_is_refused(self) -> None:
        with self.assertRaises(Exception):
            pull_games({"provider": "stake-now", "sports": []})

    def test_research_without_outcome_id_is_not_booked(self) -> None:
        ready = selections_from_keeps([{"eventId": "1", "selection": "Home", "fact": "x" * 50}])
        self.assertEqual(ready, [])

    def test_assert_share_only_rejects_bet_mode(self) -> None:
        with self.assertRaises(BookError):
            assert_share_only({"book": {"enabled": True, "mode": "bet", "stake": False}})

    def test_default_window_is_1am_to_midnight_and_cap_50(self) -> None:
        config = load_config(None)
        self.assertEqual(config["window"]["start"], "01:00")
        self.assertEqual(config["window"]["end"], "24:00")
        self.assertEqual(config["max_legs"], 50)

    def test_text_pick_matches_live_grid_outcome(self) -> None:
        ready = selections_from_keeps(
            [{"eventId": "sr:match:9", "selection": "Over 2.5", "fact": "x" * 50}],
            [{
                "eventId": "sr:match:9",
                "markets": [{
                    "id": "18",
                    "specifier": "total=2.5",
                    "outcomes": [
                        {"id": "12", "desc": "Over", "odds": "1.91"},
                        {"id": "13", "desc": "Under", "odds": "1.91"},
                    ],
                }],
            }],
        )
        self.assertEqual(ready[0]["outcomeId"], "12")
        self.assertEqual(ready[0]["odds"], "1.91")
        self.assertIsInstance(ready[0]["odds"], str)

    def test_under_without_both_teams_is_rejected(self) -> None:
        self.assertFalse(under_is_strict("Home scored only 1 in last 5. Away was not confirmed."))
        self.assertTrue(under_is_strict(
            "Both teams are very low scoring. Home scored only 1 in last 5 and away failed to score in 3."
        ))

    def test_over_needs_both_teams_above_the_line(self) -> None:
        h2h = "Diriangen scored 37 goals in 9 meetings with Rancho Santana, 4.11 per game, and 8 of 9 finished over 2.5."
        self.assertFalse(over_is_strict(h2h, "Over 2.5"))
        one_side = "Home average 2.4 goals per game. Away was not confirmed."
        self.assertFalse(over_is_strict(one_side, "Over 2.5"))
        both = "Home average 1.8 goals per game and away average 1.6 goals per game this season."
        self.assertTrue(over_is_strict(both, "Over 2.5"))
        short = "Home average 1.1 goals per game and away average 1.0 goals per game."
        self.assertFalse(over_is_strict(short, "Over 2.5"))


if __name__ == "__main__":
    unittest.main()
